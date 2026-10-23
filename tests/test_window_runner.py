"""Runner boundary tests; source auditor is real, window post-audit is isolated.

Window mathematics and the independent 44-profile auditor have separate tests.
Most tests inject a known primal to target deadline/IO/serialization contracts.
"""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import numpy as np
import pytest
from test_joint_plan_audit import tiny
from scripts import run_window_plan as r
from scripts.audit_window_plan import expected_profiles
from test_window_plan_audit import window, saved_window


@pytest.fixture
def setup(tmp_path,monkeypatch,tiny):
    cert,data,health,baseline,published,hashes=tiny
    root=tmp_path;folder=root/'work/run';folder.mkdir(parents=True)
    seed=root/'source.json';seed.write_bytes(r.json_bytes(cert));manifest=root/'manifest.json';manifest.write_text('{}')
    codes={'test-code':'c'*64}
    matrices={x['id']:baseline[x['baseProfileId']].copy() for x in expected_profiles()}
    inputs=dict(data=data,health=health,matrices=matrices,published_reference=published,
        source_cost_certificate=cert,current_source_hashes=hashes,package_id='p',manifest={},manifest_sha256='a'*64,
        current_code_hashes=codes,baseline_matrices=baseline,indices_document={})
    monkeypatch.setattr(r,'ROOT',root);monkeypatch.setattr(r,'LOADED_CODES',codes)
    monkeypatch.setattr(r,'code_hashes',lambda:codes.copy())
    monkeypatch.setattr(r,'read_window_inputs',lambda *a:inputs)
    monkeypatch.setattr(r,'unchanged_window_inputs',lambda *a:None)
    def independent_gate(certificate,**kwargs):
        assert certificate['budget']['hardConstraint'] and len(certificate['plan']['profiles'])==44
        assert certificate['generation']['searchProvenOptimal'] is False
        return {'status':'synthetic_primal_gate_passed'}
    monkeypatch.setattr(r,'validate_window_plan',independent_gate)
    args=SimpleNamespace(manifest=str(manifest),resource_seed=str(seed),out=str(folder),pool='seed',
        seconds=3.,seed_seconds=1.,refine_seconds=1.,hard_seconds=34.)
    def vector(problem,source_plan,amount=.095):
        v=problem.fixed_resource_vector(source_plan)
        for name,(oi,sj) in problem.edges.items():
            for i,f in enumerate((amount,.19-amount)):
                v[problem.offsets[name]+np.flatnonzero((oi==i)&(sj==0))[0]]=f
        problem.validate(v);return v
    def complete(problem,source_plan,*a):
        return problem.serialize(vector(problem,source_plan)),{'status':'complete_window_seed_validated'}
    def solve(problem,seed,seconds,capture_vectors=None):
        v=problem.read_plan(seed)[0];capture_vectors['finalOriginalVector']=v.copy()
        result=problem.serialize(v);result.update(feasible=True,warmStart={'solverLog':'synthetic log'},costGap=.1)
        return result
    monkeypatch.setattr(r,'complete_fixed_resource_seed',complete);monkeypatch.setattr(r,'solve_window_cost',solve)
    return root,folder,args,inputs,vector,complete,solve


def test_complete_worker_outputs_certificate_last_and_source_unchanged(setup,monkeypatch):
    root,folder,args,inputs,vector,complete,solve=setup;source=Path(args.resource_seed).read_bytes();order=[];write=r.write_new
    def tracked(path,blob):order.append(path.name);write(path,blob)
    monkeypatch.setattr(r,'write_new',tracked);r.worker(args)
    assert order[-1]=='window-plan.json' and Path(args.resource_seed).read_bytes()==source
    report=json.loads((folder/'run-result.json').read_text());cert=json.loads((folder/'window-plan.json').read_text())
    assert len(cert['plan']['profiles'])==44 and cert['plan']['annualMaterialCostTRY']==950
    assert cert['generation']['runReportSHA256']==r.sha((folder/'run-result.json').read_bytes())
    assert report['vectorSHA256']==r.sha((folder/'vectors.npz').read_bytes())
    assert report['validatedProfiles']==list(inputs['matrices']) and report['candidateIndices']==[0]


def test_deadline_after_model_build_must_not_restart_seed_clock(setup,monkeypatch):
    root,folder,args,inputs,vector,complete,solve=setup;clock=[10.];old=r.formulate
    monkeypatch.setattr(r,'monotonic',lambda:clock[0])
    def slow(*a):value=old(*a);clock[0]=14.;return value
    monkeypatch.setattr(r,'formulate',slow)
    monkeypatch.setattr(r,'complete_fixed_resource_seed',lambda *a:pytest.fail('No seed native stage after search deadline'))
    with pytest.raises(TimeoutError):r.worker(args)
    assert not (folder/'window-plan.json').exists()


def test_no_refinement_serialization_rounding_keeps_valid_native_vector_separate(setup,monkeypatch):
    root,folder,args,inputs,vector,complete,solve=setup;calls=[0]
    def only_seed(*a):
        calls[0]+=1
        return complete(*a) if calls[0]==1 else (None,{'status':'fixed_resource_seed_unavailable'})
    def rounded(problem,seed,seconds,capture_vectors=None):
        amount=next(float(v) for v in np.random.default_rng(81).uniform(.08,.10,1000) if v*1000/1000!=v)
        v=vector(problem,seed,amount);plan=problem.serialize(v)
        assert not np.array_equal(problem.read_plan(plan)[0],v)
        capture_vectors['finalOriginalVector']=v.copy();capture_vectors['returnedRawVector']=v.copy()
        plan.update(feasible=True,warmStart={'solverLog':''});return plan
    monkeypatch.setattr(r,'complete_fixed_resource_seed',only_seed);monkeypatch.setattr(r,'solve_window_cost',rounded)
    r.worker(args)
    with np.load(folder/'vectors.npz') as z:
        report=json.loads((folder/'run-result.json').read_text())
        problem=r.formulate(inputs,[0]);published=problem.read_plan(report['result'])[0]
        assert np.array_equal(z['finalOriginalVector'],published)
        assert not np.array_equal(z['returnedRawVector'],published)


def test_worse_optional_refinement_preserves_validated_window_cost_plan(setup,monkeypatch):
    root,folder,args,inputs,vector,complete,solve=setup;calls=[0]
    def worse(problem,source_plan,*a):
        calls[0]+=1
        if calls[0]==1:return complete(problem,source_plan,*a)
        return problem.serialize(vector(problem,source_plan,.09)),{'status':'complete_window_seed_validated'}
    monkeypatch.setattr(r,'complete_fixed_resource_seed',worse);r.worker(args)
    report=json.loads((folder/'run-result.json').read_text());result=report['result']
    assert result['travelRefinement']['costStageAssignmentsRetained'] is True
    assert result['travelRefinementPerformed'] is False and result['travelRefinementChangedAssignments'] is False
    assert all(p['meanMinutes']==pytest.approx(15.) for p in result['profiles'])
    assert (folder/'window-plan.json').is_file()
    with np.load(folder/'vectors.npz') as z:
        assert np.array_equal(z['finalOriginalVector'],z['costStageOriginalVector'])


def test_accepted_refinement_has_separate_truthful_cost_and_travel_metadata(setup,monkeypatch):
    root,folder,args,inputs,vector,complete,solve=setup;calls=[0]
    def improve(problem,source_plan,*a):
        calls[0]+=1
        if calls[0]==1:return complete(problem,source_plan,*a)
        return problem.serialize(vector(problem,source_plan,.10)),{'status':'complete_window_seed_validated'}
    monkeypatch.setattr(r,'complete_fixed_resource_seed',improve);r.worker(args)
    report=json.loads((folder/'run-result.json').read_text());result=report['result']
    assert result['costStageProfileReassignmentPerformed'] is False
    assert 'profileReassignmentPerformed' not in result and 'secondTravelStageImplemented' not in result
    assert result['travelRefinementPerformed'] is True and result['travelRefinementChangedAssignments'] is True
    assert result['travelRefinement']['costStageAssignmentsRetained'] is False
    assert all(p['meanMinutes']<15 for p in result['profiles'])
    with np.load(folder/'vectors.npz') as z:
        problem=r.formulate(inputs,[0]);before=z['costStageOriginalVector'];after=z['finalOriginalVector']
        assert np.array_equal(before[:problem.nf],after[:problem.nf])
        assert not np.array_equal(before[problem.nf:],after[problem.nf:])


@pytest.mark.parametrize('error',[ValueError,RuntimeError,TimeoutError])
def test_optional_refinement_error_preserves_cost_plan_with_reason(setup,monkeypatch,error):
    root,folder,args,inputs,vector,complete,solve=setup;calls=[0]
    def broken(*a):
        calls[0]+=1
        if calls[0]==1:return complete(*a)
        raise error('Synthetic optional refinement failure')
    monkeypatch.setattr(r,'complete_fixed_resource_seed',broken);r.worker(args)
    report=json.loads((folder/'run-result.json').read_text());travel=report['result']['travelRefinement']
    assert travel['costStageAssignmentsRetained'] is True
    assert 'Synthetic optional refinement failure' in travel['reason']
    assert (folder/'window-plan.json').is_file()


def test_unknown_cost_never_writes_certificate_or_calls_refinement(setup,monkeypatch):
    root,folder,args,inputs,vector,complete,solve=setup;calls=[0]
    def no_seed(*a):calls[0]+=1;return None,{'status':'fixed_resource_seed_unavailable'}
    monkeypatch.setattr(r,'complete_fixed_resource_seed',no_seed)
    monkeypatch.setattr(r,'solve_window_cost',lambda *a,**k:dict(status='inconclusive_without_validated_incumbent',feasible=None))
    r.worker(args)
    assert calls[0]==1 and not (folder/'window-plan.json').exists() and (folder/'run-result.json').is_file()


@pytest.mark.parametrize('change',['seed','code','postgate'])
def test_exit_mutation_or_independent_rejection_prevents_certificate(setup,monkeypatch,change):
    root,folder,args,inputs,vector,complete,solve=setup
    def changed(*a,**k):
        value=solve(*a,**k)
        if change=='seed':Path(args.resource_seed).write_bytes(Path(args.resource_seed).read_bytes()+b' ')
        elif change=='code':monkeypatch.setattr(r,'code_hashes',lambda:{})
        return value
    monkeypatch.setattr(r,'solve_window_cost',changed)
    if change=='postgate':monkeypatch.setattr(r,'validate_window_plan',lambda *a,**k:(_ for _ in ()).throw(ValueError('Independent budget gate failed')))
    with pytest.raises(ValueError):r.worker(args)
    assert not (folder/'window-plan.json').exists()


def test_worker_direct_entry_cannot_write_under_processed(setup,monkeypatch):
    root,folder,args,inputs,vector,complete,solve=setup;target=root/'data/processed';target.mkdir(parents=True)
    args.out=str(target)
    with pytest.raises(ValueError):r.worker(args)
    assert not (target/'window-plan.json').exists()


def test_hard_timeout_partial_file_is_not_complete_certificate(setup,monkeypatch):
    root,folder,args,inputs,vector,complete,solve=setup;args.out=str(root/'work/outer')
    def timeout(*a,**k):
        (Path(args.out)/'window-plan.json').write_text('{"format":')
        raise subprocess.TimeoutExpired(a[0],args.hard_seconds)
    monkeypatch.setattr(r.subprocess,'run',timeout)
    with pytest.raises(SystemExit):r.run(args)
    status=json.loads((Path(args.out)/'process-status.json').read_text())
    assert status['status']=='hard_timeout'
    assert status.get('completeCertificateWritten',False) is False


@pytest.mark.parametrize('values',[(1801,1,1,2200),(3,3,1,40),(3,1,1,10),(True,1,1,40),(3,1,float('nan'),40),(1800,90,120,2401)])
def test_time_control_contract(values):
    with pytest.raises(ValueError):r.controls(*values)


def test_explicit_long_search_retains_bounded_outer_guard():
    r.controls(1800,90,120,2100)


@pytest.fixture
def adaptive_setup(setup,monkeypatch):
    """Real helper sidecars, synthetic subset cost/profile LP primitives."""
    from backend import window_seed
    root,folder,args,inputs,vector,complete,solve=setup
    args.seconds=180.;args.hard_seconds=220.;args.adaptive_seed_seconds=60.;args.seed_stage_seconds=10.
    monkeypatch.setattr(window_seed,'ROOT',root)
    monkeypatch.setattr(r,'complete_fixed_resource_seed',lambda *a:(None,{'status':'fixed_resource_seed_unavailable'}))
    def subset_cost(problem,seed,seconds,capture_vectors):
        v=vector(problem,inputs['source_cost_certificate']['plan']);plan=problem.serialize(v)
        capture_vectors['finalOriginalVector']=problem.read_plan(plan)[0]
        plan.update(feasible=True);return plan
    def lp(lp,seconds):
        f=np.zeros(len(lp['c']));f[lp['edgeOrigin']==0]=.095;f[lp['edgeOrigin']==1]=.095
        return SimpleNamespace(status=0,x=f)
    def prepare(*a,**kw):
        return window_seed.run_seed_search(*a,**kw,cost_search=subset_cost,
            warm_complete=lambda *a:(None,{'status':'none'}),lp_solve=lp)
    def final(problem,seed,seconds,capture_vectors):
        result=solve(problem,seed,seconds,capture_vectors)
        capture_vectors['suppliedOriginalVector']=problem.read_plan(seed)[0]
        result.update(nativeRunStarted=True,costStagePerformed=True)
        result['warmStart'].update(completeStartSupplied=True,solverAcceptedFeasibleStart=True)
        return result
    monkeypatch.setattr(r,'run_seed_search',prepare);monkeypatch.setattr(r,'solve_window_cost',final)
    return (*setup,prepare,final)


def test_adaptive_failure_skips_full_native_and_writes_no_certificate(adaptive_setup,monkeypatch):
    from backend import window_seed
    root,folder,args,inputs,vector,complete,solve,prepare,final=adaptive_setup
    def unknown(*a,**kw):
        return window_seed.run_seed_search(*a,**kw,cost_search=lambda *a,**kw:{'feasible':None,'status':'unknown'},
            warm_complete=lambda *a:(None,{'status':'none'}))
    monkeypatch.setattr(r,'run_seed_search',unknown)
    monkeypatch.setattr(r,'solve_window_cost',lambda *a,**kw:pytest.fail('No full native after failed adaptive seed'))
    r.worker(args)
    report=json.loads((folder/'run-result.json').read_text())
    assert report['result']['feasible'] is None and not report['result']['nativeRunStarted']
    assert report['optimizedProfiles']==report['validatedProfiles']==[]
    assert report['adaptiveSeedPreparationSHA256']==r.sha((folder/'seed-preparation/seed-preparation.json').read_bytes())
    assert not (folder/'window-plan.json').exists()


def test_adaptive_independent_gate_rejection_prevents_full_native(adaptive_setup,monkeypatch):
    root,folder,args,*_=adaptive_setup
    monkeypatch.setattr(r,'validate_window_plan',lambda *a,**kw:(_ for _ in ()).throw(ValueError('Independent Decimal budget rejected')))
    monkeypatch.setattr(r,'solve_window_cost',lambda *a,**kw:pytest.fail('No native call before independent budget acceptance'))
    with pytest.raises(ValueError,match='Decimal budget'):r.worker(args)
    assert not (folder/'window-plan.json').exists() and not (folder/'run-result.json').exists()


def test_adaptive_gate_really_rejects_a_sub_cent_decimal_overrun(window,monkeypatch):
    from scripts import audit_window_plan as auditor
    # This passes the numeric model's .01 TRY tolerance, but the independent
    # Decimal budget has no currency tolerance. No native solver is called.
    limit=6049.99999;window['published_reference']['capacity']['budgetLimitTRY']=limit
    monkeypatch.setattr(r,'ORIGINAL_ANNUAL_BUDGET_TRY',limit)
    monkeypatch.setattr(r,'validate_window_plan',auditor.validate_window_plan)
    problem=r.formulate(window,[0]);plan=problem.serialize(problem.read_plan(window['certificate']['plan'])[0])
    prep=dict(stages=[{'stage':1,'optimizedProfileIds':list(window['matrices'])[:12]}],
        artifacts={'stage-01-completion-vectors.npz':'a'*64},completeSeedPlan=plan)
    with pytest.raises(ValueError,match='Hard annual budget exceeded'):
        r.check_adaptive_seed(prep,window,problem,r.json_bytes(prep))


def test_adaptive_pre_native_fallback_cannot_be_a_performed_44_profile_search(adaptive_setup,monkeypatch):
    root,folder,args,inputs,vector,complete,solve,prepare,final=adaptive_setup
    def skipped(*a,**kw):
        result=final(*a,**kw);result['nativeRunStarted']=False;return result
    monkeypatch.setattr(r,'solve_window_cost',skipped)
    with pytest.raises(ValueError,match='relabelled'):r.worker(args)
    assert not (folder/'window-plan.json').exists()


@pytest.mark.parametrize('name',['seed-preparation.json','stage-01-cost.json','stage-01-completion-vectors.npz'])
def test_adaptive_artifact_mutation_during_final_search_prevents_publication(adaptive_setup,monkeypatch,name):
    root,folder,args,inputs,vector,complete,solve,prepare,final=adaptive_setup
    def changed(*a,**kw):
        result=final(*a,**kw);path=folder/'seed-preparation'/name;path.write_bytes(path.read_bytes()+b' ');return result
    monkeypatch.setattr(r,'solve_window_cost',changed)
    with pytest.raises(ValueError,match='Adaptive seed artifact changed'):r.worker(args)
    assert not (folder/'window-plan.json').exists()


@pytest.mark.parametrize('adaptive,stage',[(True,1),(-1,1),(1201,1),(float('nan'),1),(1,True),(1,0),(1,301),(1,float('inf'))])
def test_adaptive_control_types_and_caps(adaptive,stage):
    with pytest.raises(ValueError):r.controls(1500,90,120,1800,adaptive,stage)


def test_adaptive_controls_reserve_full_window_search_and_forward_to_child(setup,monkeypatch):
    root,folder,args,*_=setup
    r.controls(1500,90,120,1800,900,300)
    with pytest.raises(ValueError,match='Reserve'):r.controls(1050,90,120,1400,900,300)
    args.seconds=1500;args.seed_seconds=90;args.refine_seconds=120;args.hard_seconds=1800
    args.adaptive_seed_seconds=900;args.seed_stage_seconds=300;args.out=str(root/'work/outer-adaptive');commands=[]
    monkeypatch.setattr(r.subprocess,'run',lambda command,**kw:(commands.append((command,kw)) or SimpleNamespace(returncode=0)))
    r.run(args);command,options=commands[0]
    assert command[command.index('--adaptive-seed-seconds')+1]=='900'
    assert command[command.index('--seed-stage-seconds')+1]=='300' and options['timeout']==1800


@pytest.mark.parametrize('pool_mode',['seed','explicit'])
@pytest.mark.parametrize('adaptive',[False,True])
def test_complete_worker_independent_auditor_and_publisher_roundtrip_without_native(saved_window,window,monkeypatch,pool_mode,adaptive):
    """Exercise the real wire/file contracts, including the native-vector member.

    Only the synthetic package token and small origin sample come from the
    source fixture. No model/audit/serialization gate is stubbed out. A valid
    44-profile seed is injected and the native entry deliberately times out.
    """
    from scripts import audit_window_plan as auditor
    from scripts import publish_window_plan as publisher
    from scripts import manifest as release_manifest
    from backend import window_solver,window_seed
    root,manifest_path,_=saved_window
    folder=root/'work/complete-run';folder.mkdir()
    monkeypatch.setattr(r,'ROOT',root)
    monkeypatch.setattr(r,'ORIGINAL_ANNUAL_BUDGET_TRY',10000.)
    monkeypatch.setattr(r,'LOADED_CODES',auditor.code_hashes(root))
    monkeypatch.setattr(r,'code_hashes',lambda:auditor.code_hashes(root))
    reader=lambda path:auditor.read_window_inputs(path,root)
    exit_gate=lambda inputs:auditor.unchanged_window_inputs(inputs,root)
    monkeypatch.setattr(r,'read_window_inputs',reader)
    monkeypatch.setattr(r,'unchanged_window_inputs',exit_gate)
    calls=[0]
    def complete(problem,source_plan,*args):
        calls[0]+=1
        if adaptive:return None,{'status':'fixed_resource_seed_unavailable'}
        if calls[0]>1:return None,{'status':'fixed_resource_seed_unavailable'}
        # The fixture has an independently valid named 44-profile plan.
        vector=problem.read_plan(window['certificate']['plan'])[0]
        return problem.serialize(vector),{'status':'complete_window_seed_validated'}
    def timeout(*args,**kwargs):raise TimeoutError('Synthetic no-native preparation deadline')
    monkeypatch.setattr(r,'complete_fixed_resource_seed',complete)
    monkeypatch.setattr(window_solver,'native_window_optimize',timeout)
    if adaptive:
        monkeypatch.setattr(window_seed,'ROOT',root)
        def subset_cost(problem,seed,seconds,capture_vectors):
            plan=deepcopy(window['certificate']['plan'])
            plan['profiles']=[row for row in plan['profiles'] if row['profile'] in problem.times]
            v=problem.read_plan(plan)[0];result=problem.serialize(v)
            capture_vectors['finalOriginalVector']=problem.read_plan(result)[0];result['feasible']=True;return result
        def profile_flow(lp,seconds):
            f=np.zeros(len(lp['c']));f[lp['edgeOrigin']==0]=.09;f[lp['edgeOrigin']==1]=.1
            return SimpleNamespace(status=0,x=f)
        def actual_helper(*a,**kw):
            return window_seed.run_seed_search(*a,**kw,cost_search=subset_cost,
                warm_complete=lambda *a:(None,{'status':'none'}),lp_solve=profile_flow)
        def native_stub(problem,start,seconds,metadata,deadline,presolve):
            assert start is not None and len(problem.times)==44
            metadata.update(completeStartSupplied=True,solverAcceptedFeasibleStart=True,solverLog='Synthetic no-native accepted start')
            return SimpleNamespace(x=start.copy(),status=1,mip_dual_bound=np.nan,mip_gap=np.nan,runtime=0.,nodes=0,
                nativeModelStatus='kTimeLimit',message='Synthetic interface only; no native run',isTimeLimit=True)
        monkeypatch.setattr(r,'run_seed_search',actual_helper)
        monkeypatch.setattr(window_solver,'native_window_optimize',native_stub)
    pool_path=None;pool_bytes=None
    if pool_mode=='explicit':
        inputs=reader(manifest_path)
        pool_bytes=r.json_bytes(dict(format=1,candidateIndices=[0,1],method='Synthetic expanded optional site pool',
            sourceSHA256=inputs['current_source_hashes'],profileManifestSHA256=inputs['manifest_sha256']))
        pool_path=root/'work/explicit-pool.json';pool_path.write_bytes(pool_bytes)
    args=SimpleNamespace(manifest=str(manifest_path),resource_seed=str(root/'data/processed/joint-plan.json'),
        out=str(folder),pool=pool_mode,pool_file=None if pool_path is None else str(pool_path),
        seconds=3.,seed_seconds=1.,refine_seconds=1.,hard_seconds=34.)
    if adaptive:
        args.seconds=180.;args.hard_seconds=220.;args.adaptive_seed_seconds=60.;args.seed_stage_seconds=10.
    r.worker(args)
    (folder/'process-status.json').write_bytes(r.json_bytes(dict(status='completed',returnCode=0,certificateFilePresent=True)))
    independent=auditor.audit_saved_window_plan(folder/'window-plan.json',manifest_path,root)
    assert independent['allProfilesValidated'] and independent['withinHardBudget']
    assert independent['runArtifactAudit']['finalVectorExactlyMatchesJSON']
    assert independent['runArtifactAudit']['resourceSeedFourProfileValidated']
    assert independent['runArtifactAudit']['candidatePool']==pool_mode
    if adaptive:
        assert independent['runArtifactAudit']['adaptiveSeedAudit']['completeSeedIndependentlyValidated']
        assert independent['runArtifactAudit']['adaptiveSeedAudit']['profileCount']==44
        assert not independent['runArtifactAudit']['adaptiveSeedAudit']['partialStageBoundsTransferred']
    if pool_mode=='explicit':
        assert (folder/'candidate-pool.json').read_bytes()==pool_bytes
        report=json.loads((folder/'run-result.json').read_text())
        assert report['candidateIndices']==[0,1] and report['candidatePoolSHA256']==r.sha(pool_bytes)
    monkeypatch.setattr(publisher,'ROOT',root)
    monkeypatch.setattr(publisher,'read_window_inputs',reader)
    monkeypatch.setattr(publisher,'unchanged_window_inputs',exit_gate)
    monkeypatch.setattr(publisher,'audit_saved_window_plan',lambda certificate,manifest:auditor.audit_saved_window_plan(certificate,manifest,root))
    monkeypatch.setattr(release_manifest,'ROOT',root)
    monkeypatch.setattr(release_manifest,'OUT',root/'data/processed')
    monkeypatch.setattr(release_manifest,'RAW',root/'data/raw')
    process_path=folder/'process-status.json'; process_bytes=process_path.read_bytes()
    for invalid_code in (False,0.0,'0',None):
        process_path.write_bytes(r.json_bytes(dict(status='completed',returnCode=invalid_code,certificateFilePresent=True)))
        with pytest.raises(ValueError,match='completed'):
            publisher.validated_bundle(folder,manifest_path)
    process_path.write_bytes(process_bytes)
    publisher.publish(folder,manifest_path)
    published=root/'data/processed/departure-window-plan'
    assert (published/'solver.log').is_file()
    if adaptive:
        original=folder/'seed-preparation';copied=published/'seed-preparation'
        assert {p.name for p in original.iterdir()}=={p.name for p in copied.iterdir()}
        assert all((copied/p.name).read_bytes()==p.read_bytes() for p in original.iterdir())
    after=auditor.audit_saved_window_plan(published/'window-plan.json',root/'data/processed/departure-window/manifest.json',root)
    assert after==independent
    release_manifest.check()
    if pool_mode=='explicit':
        assert (published/'candidate-pool.json').read_bytes()==pool_bytes
        (published/'candidate-pool.json').write_bytes(pool_bytes+b' ')
        with pytest.raises(ValueError,match='pool'):
            auditor.audit_saved_window_plan(published/'window-plan.json',root/'data/processed/departure-window/manifest.json',root)
