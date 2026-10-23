"""Tiny seed tests. No Ankara matrix or real-data solve is loaded."""
from copy import deepcopy
import json
from types import SimpleNamespace

import numpy as np
import pytest

from test_joint_model import fixture,independently_enumerated_cost
from backend.window_model import build_window_problem
from backend import window_seed as p


def tiny(budget=100):
    old,source,vector,args=fixture(scenario={'coverageTarget':95,'districtFloor':80})
    args=list(deepcopy(args));args[0]={f'clock-{i:02d}':np.ones((2,2)) for i in range(44)}
    # An unoptimized intermediate clock requires both sites; the first twelve
    # clocks can use one two-bed/two-doctor site. Four clocks are activated as
    # a block when the independent resource-assignment attempt fails here.
    args[0]['clock-12']=np.array([[1.,np.inf],[np.inf,1.]])
    full=build_window_problem(*args,annual_budget=budget)
    def subset(names):
        return build_window_problem({name:args[0][name] for name in names},*args[1:],annual_budget=budget)
    return full,subset,source,args


def fixed_plan(problem,source,both=True):
    v=problem.fixed_resource_vector(source)
    if not both:
        v[:problem.nf]=0
        x=next(x for x in problem.site_xs[0] if problem.xtype[x]==1)
        v[x]=1;v[problem.nx]=2
    for name,(oi,sj) in problem.edges.items():
        for i in range(2):
            j=i if both else 0
            positions=np.flatnonzero((oi==i)&(sj==j))
            if not len(positions):raise ValueError('Fixture resource selection cannot reach this origin')
            v[problem.offsets[name]+positions[0]]=.00095
    return problem.serialize(v)


def test_two_native_tiny_stages_add_failed_block_and_keep_final44_budget_material(tmp_path,monkeypatch):
    full,subset,source,args=tiny();monkeypatch.setattr(p,'ROOT',tmp_path);gates=[]
    out=tmp_path/'work/seed-only'
    result=p.run_seed_search(full,subset,source,overall_seconds=20,stage_seconds=3,completion_seconds=5,
        profile_seconds=1,max_stages=3,out=out,bindings={'synthetic':'only'},binding_gate=lambda:gates.append(True))
    assert result['feasible'] is True and len(result['completeSeedPlan']['profiles'])==44
    assert [len(s['optimizedProfileIds']) for s in result['stages']]==[12,16]
    assert result['stages'][0]['fullWindowCompletion']['failedProfileIds']==['clock-12']
    assert result['stages'][0]['nextProfileIds']==list(full.times)[:16]
    plan=result['completeSeedPlan'];full.read_plan(plan)
    assert plan['annualMaterialCostTRY']==9.5 and plan['annualEquivalentCostTRY']==25.5
    # Independent integer-resource enumeration at full demand has the same
    # forced resource choices; only the one annual material amount changes.
    assert plan['annualEquivalentCostTRY']==independently_enumerated_cost(args[0])-.5
    assert all(abs(x['coveredPopulation']-1.9)<1e-10 and min(d['coveragePercent'] for d in x['districts'])>=80 for x in plan['profiles'])
    assert plan['minimumAnnualCostLowerBoundTRY'] is None and not result['profileSubsetBoundsTransferred']
    assert result['independentFinalAuditRequired'] and result['outerHardTimeoutRequired']
    first=json.loads((out/'stage-01-cost.json').read_text())
    assert len(first['optimizedProfileIds'])==12 and 'Only this stage' in first['boundScope']
    with np.load(out/'stage-01-cost-vectors.npz') as a,np.load(out/'stage-02-completion-vectors.npz') as b:
        assert len(a['finalOriginalVector'])<len(b['complete44Vector'])
    for name,digest in result['artifacts'].items():assert p.sha((out/name).read_bytes())==digest
    assert len(gates)>=4
    with pytest.raises(ValueError,match='Fresh'):
        p.run_seed_search(full,subset,source,out=out,bindings={'synthetic':'only'},binding_gate=lambda:None)


def test_unknown_subset_cost_is_never_a_full_window_fallback():
    full,subset,source,args=tiny();calls=[]
    def no_cost(problem,seed,seconds,capture_vectors):
        calls.append(len(problem.times));return dict(feasible=None,status='inconclusive_without_validated_incumbent')
    result=p.run_seed_search(full,subset,source,cost_search=no_cost,
        warm_complete=lambda *a:(None,{'status':'none'}),lp_solve=lambda *a:pytest.fail('No completion after unknown cost'))
    assert calls==[12] and result['feasible'] is None and result['completeSeedPlan'] is None
    assert not result['globalInfeasibilityProven']


def test_failed_profiles_do_not_reuse_old_departure_flows():
    full,subset,source,args=tiny();small=subset(list(full.times)[:12]);plan=fixed_plan(small,source,both=False)
    complete,diagnostic,partial=p.complete_named_window(full,small,plan,10,1)
    assert complete is None and diagnostic['feasible'] is None
    assert diagnostic['failedProfileIds']==['clock-12'] and not diagnostic['oldProfilesRelabelled']
    start=full.offsets['clock-12'];assert not partial[start:start+len(full.edges['clock-12'][0])].any()
    assert diagnostic['sameNamedFlowsReused']==list(full.times)[:12]


def test_invalid_negative_return_is_unknown_without_clipping():
    full,subset,source,args=tiny();small=subset(list(full.times)[:12]);plan=fixed_plan(small,source)
    def negative(lp,seconds):return SimpleNamespace(status=0,x=np.full(len(lp['c']),-1e-15))
    complete,diagnostic,partial=p.complete_named_window(full,small,plan,10,1,lp_solve=negative)
    assert complete is None and len(diagnostic['failedProfileIds'])==32
    assert all(x['status']=='unknown_numerical_or_solver' for x in diagnostic['profiles'][12:])
    assert np.count_nonzero(partial[full.offsets['clock-12']:])==0


def test_deadline_after_formulation_starts_no_lp(monkeypatch):
    full,subset,source,args=tiny();small=subset(list(full.times)[:12]);plan=fixed_plan(small,source)
    clock=[10.];original=p.joint_travel.formulate_profile
    def slow(*args):value=original(*args);clock[0]=12.;return value
    monkeypatch.setattr(p.joint_travel,'formulate_profile',slow)
    complete,diagnostic,_=p.complete_named_window(full,small,plan,1,1,clock=lambda:clock[0],
        lp_solve=lambda *a:pytest.fail('No native LP may start after assembly deadline'))
    assert complete is None and all(r['status']=='unknown_deadline' for r in diagnostic['profiles'][12:])


def test_same_named_matrix_or_model_mutation_fails_closed(monkeypatch):
    full,subset,source,args=tiny();small=subset(list(full.times)[:12]);plan=fixed_plan(small,source)
    small.times['clock-00']=small.times['clock-00'].copy();small.times['clock-00'][0,0]=99
    with pytest.raises(ValueError,match='matrix changed'):p.complete_named_window(full,small,plan)
    small=subset(list(full.times)[:12])
    def mutate(lp,seconds):
        full.times['clock-13'][0,0]=99
        return SimpleNamespace(status=1,x=None)
    with pytest.raises(ValueError,match='model changed'):
        p.complete_named_window(full,small,plan,10,1,lp_solve=mutate)


def test_budget_and_profile_limits_not_relaxed_on_later_subset():
    full,subset,source,args=tiny()
    def changed(names):
        problem=subset(names);problem.annual_budget+=1;return problem
    with pytest.raises(ValueError,match='budget'):
        p.run_seed_search(full,changed,source)
    for invalid in (True,0,12):
        with pytest.raises(ValueError):p.run_seed_search(full,subset,source,max_stages=invalid)


def test_stage_limit_returns_no_partial_certificate_or_global_infeasibility():
    full,subset,source,args=tiny()
    def fixed_cost(problem,seed,seconds,capture_vectors):
        plan=fixed_plan(problem,source,both=False);plan['feasible']=True;return plan
    result=p.run_seed_search(full,subset,source,max_stages=1,cost_search=fixed_cost,
        warm_complete=lambda *a:(None,{'status':'none'}))
    assert result['feasible'] is None and result['completeSeedPlan'] is None
    assert result['stages'][0]['nextProfileIds']==list(full.times)[:16]
    assert not result['globalInfeasibilityProven'] and not result['globalOptimalityProven']


@pytest.mark.parametrize('mutation',[
    lambda q:q.edges.__setitem__('clock-12',(q.edges['clock-12'][0][::-1].copy(),q.edges['clock-12'][1])),
    lambda q:q.edges.__setitem__('clock-12',(q.edges['clock-12'][0],q.edges['clock-12'][1][::-1].copy())),
    lambda q:q.offsets.__setitem__('clock-12',q.offsets['clock-12']+1),
    lambda q:setattr(q,'n',q.n+1),lambda q:setattr(q,'m',q.m+1),
    lambda q:setattr(q,'nx',q.nx+1),lambda q:setattr(q,'nf',q.nf+1),
    lambda q:q.ids.reverse(),lambda q:q.local.__setitem__(q.ids[0],1),
    lambda q:setattr(q,'xsite',q.xsite[::-1].copy()),
    lambda q:setattr(q,'xtype',q.xtype[::-1].copy()),
    lambda q:q.site_xs.__setitem__(0,q.site_xs[0][::-1].copy()),
    lambda q:setattr(q,'q',q.q+1),lambda q:setattr(q,'target',q.target+.1),
    lambda q:setattr(q,'cost_scale',q.cost_scale+1),
    lambda q:setattr(q,'shared_row_indices',q.shared_row_indices[::-1].copy()),
])
def test_signature_binds_semantic_mappings_and_derived_coefficients(mutation):
    full,_,_,_=tiny();before=p.signature(full);mutation(full)
    assert p.signature(full)!=before


@pytest.mark.parametrize('mutation',[
    lambda q:q.offsets.__setitem__('clock-00',q.offsets['clock-00']+1),
    lambda q:setattr(q,'nf',q.nf+1),lambda q:setattr(q,'nx',q.nx+1),
    lambda q:setattr(q,'target',q.target+.1),lambda q:setattr(q,'cost_scale',q.cost_scale+1),
    lambda q:q.sites[0].__setitem__('footprintRadiusMeters',q.sites[0]['footprintRadiusMeters']+1),
    lambda q:setattr(q,'xtype',q.xtype[::-1].copy()),
    lambda q:q.site_xs.__setitem__(0,q.site_xs[0][::-1].copy()),
    lambda q:q.ids.reverse(),
])
def test_incompatible_resource_or_flow_layout_rejected_before_native(mutation):
    full,subset,source,_=tiny();small=deepcopy(subset(list(full.times)[:12]));plan=fixed_plan(small,source)
    mutation(small)
    with pytest.raises(ValueError):
        p.complete_named_window(full,small,plan,lp_solve=lambda *a:pytest.fail('Malformed layout must not reach LP'))


@pytest.mark.parametrize('kind',['edge','offset'])
def test_same_tampering_in_both_objects_does_not_bypass_canonical_layout(kind):
    full,subset,source,_=tiny();small=deepcopy(subset(list(full.times)[:12]));plan=fixed_plan(small,source)
    for problem in (full,small):
        if kind=='edge':
            oi,sj=problem.edges['clock-00'];problem.edges['clock-00']=(oi[::-1].copy(),sj)
        else:problem.offsets['clock-00']+=1
    with pytest.raises(ValueError,match='edge mapping|offset'):
        p.complete_named_window(full,small,plan,lp_solve=lambda *a:pytest.fail('Malformed shared mapping must not reach LP'))


@pytest.mark.parametrize('kind',['edge','offset','staff_coefficient'])
def test_mid_completion_semantic_mutation_cannot_publish_complete_seed(kind):
    full,subset,source,_=tiny();small=subset(list(full.times)[:12]);plan=fixed_plan(small,source);calls=[]
    def tamper(lp,seconds):
        if not calls:
            if kind=='edge':
                oi,sj=full.edges['clock-12'];full.edges['clock-12']=(oi[::-1].copy(),sj)
            elif kind=='offset':full.offsets['clock-12']+=1
            else:full.q+=1
        calls.append(True);return SimpleNamespace(status=1,x=None)
    with pytest.raises(ValueError,match='Full model changed'):
        p.complete_named_window(full,small,plan,10,1,lp_solve=tamper)


def test_subset_with_nonconsecutive_named_blocks_uses_its_own_offsets():
    full,subset,source,_=tiny();names=list(full.times)[:4]+list(full.times)[12:16]
    small=subset(names);p.compatible(full,small,names)
    assert full.offsets['clock-12']!=small.offsets['clock-12']
    plan=fixed_plan(small,source);vector,_=small.read_plan(plan)
    complete,diagnostic,partial=p.complete_named_window(full,small,plan,10,1,
        lp_solve=lambda *a:SimpleNamespace(status=1,x=None))
    assert complete is None and diagnostic['sameNamedFlowsReused']==names
    for name in names:
        length=len(full.edges[name][0])
        np.testing.assert_array_equal(partial[full.offsets[name]:full.offsets[name]+length],
            vector[small.offsets[name]:small.offsets[name]+length])


def test_subset_mutation_during_cost_call_is_not_hidden_by_unchanged_full_problem():
    full,subset,source,_=tiny()
    def mutate(problem,seed,seconds,capture_vectors):
        problem.offsets['clock-00']+=1
        return {'feasible':None,'status':'inconclusive_without_validated_incumbent'}
    with pytest.raises(ValueError,match='Subset model changed'):
        p.run_seed_search(full,subset,source,cost_search=mutate,warm_complete=lambda *a:(None,{'status':'none'}))


def test_production_artifact_and_code_identity_exclude_prototype_claims():
    full,subset,source,_=tiny()
    result=p.run_seed_search(full,subset,source,
        cost_search=lambda *a,**kw:{'feasible':None,'status':'no_incumbent'},
        warm_complete=lambda *a:(None,{'status':'none'}))
    assert result['artifactType']=='window-seed-preparation'
    assert result['helperCodeSHA256']==p.code_hash()==p.LOADED_CODE_LF_SHA256
    assert 'prototypeSHA256' not in result
    assert result['completeSeedPlan'] is None and result['independentFinalAuditRequired']


def test_loaded_code_mismatch_stops_before_any_stage(monkeypatch):
    full,subset,source,_=tiny();monkeypatch.setattr(p,'LOADED_CODE_LF_SHA256','0'*64)
    with pytest.raises(ValueError,match='Loaded seed helper'):
        p.run_seed_search(full,lambda *a:pytest.fail('No build after code mismatch'),source)


def test_code_change_during_stage_stops_before_result_is_saved(monkeypatch,tmp_path):
    full,subset,source,_=tiny();monkeypatch.setattr(p,'ROOT',tmp_path)
    def changed(*a,**kw):
        monkeypatch.setattr(p,'code_hash',lambda:'0'*64)
        return {'feasible':None,'status':'no_incumbent'}
    out=tmp_path/'work/run'
    with pytest.raises(ValueError,match='helper code changed'):
        p.run_seed_search(full,subset,source,cost_search=changed,warm_complete=lambda *a:(None,{'status':'none'}),
            out=out,bindings={'synthetic':'only'},binding_gate=lambda:None)
    assert not list(out.iterdir())


def test_progress_is_flushed_observational_json(monkeypatch):
    printed=[];monkeypatch.setattr('builtins.print',lambda message,**kw:printed.append((json.loads(message),kw)))
    full,subset,source,_=tiny()
    p.run_seed_search(full,subset,source,cost_search=lambda *a,**kw:{'feasible':None,'status':'no_incumbent'},
        warm_complete=lambda *a:(None,{'status':'none'}))
    assert [record['event'] for record,_ in printed]==['stage_started','subset_cost_started','subset_cost_finished','finished']
    assert all(options=={'flush':True} for _,options in printed)
    assert all(record['component']=='window_seed' for record,_ in printed)
    assert printed[-1][0]['status']=='seed_preparation_inconclusive'


def test_subset_resource_seed_mutation_is_rejected_before_cost_callback():
    full,subset,source,_=tiny()
    def mutate(problem,*args):
        problem.offsets['clock-00']+=1
        return None,{'status':'none'}
    with pytest.raises(ValueError,match='Subset model changed during resource seed'):
        p.run_seed_search(full,subset,source,warm_complete=mutate,
            cost_search=lambda *a,**kw:pytest.fail('No native cost on changed seed model'))


@pytest.mark.parametrize('limit,expected',[(1.,'during subset assembly'),(10.,'before subset cost search')])
def test_stage_and_overall_deadlines_do_not_restart_after_setup(limit,expected):
    full,subset,source,_=tiny();now=[0.]
    def slow(names):
        answer=subset(names);now[0]=2.;return answer
    def slow_seed(*args):now[0]=11.;return None,{'status':'none'}
    result=p.run_seed_search(full,slow,source,overall_seconds=limit,stage_seconds=limit,clock=lambda:now[0],
        warm_complete=slow_seed,cost_search=lambda *a,**kw:pytest.fail('No cost solve after absolute deadline'))
    assert expected in result['reason'] and result['feasible'] is None and not result['stages']


def test_completion_cannot_label_small_subset_as_complete44():
    full,subset,source,_=tiny();small=subset(list(full.times)[:12]);plan=fixed_plan(small,source)
    with pytest.raises(ValueError,match='exactly 44'):
        p.complete_named_window(small,small,plan,lp_solve=lambda *a:pytest.fail('No LP for wrongly named complete window'))
