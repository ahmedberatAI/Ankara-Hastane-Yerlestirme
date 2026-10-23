"""Small independent resource enumeration and explicit formulation invariants."""
from copy import deepcopy
from itertools import product
import math
import numpy as np
import pytest
from backend.joint_model import build_joint_problem,ModelInfeasible
from backend.joint_solver import solve_cost
from backend.joint_heuristic import batch_close

PROFILES=('weekday-0800','weekday-1000','saturday-1000','sunday-1000')


def fixture(matrices=None,pop=(1,1),sites_count=2,scenario=None):
    h={'version':'tiny','rates':{'contactsPerResident':1,'bedDaysPerResident':365},
        'templates':[{'id':'one','beds':1,'grossAreaM2':1},{'id':'two','beds':2,'grossAreaM2':2}],
        'design':{'areaPerDoctorM2':1,'maxFloors':1,'minimumDoctorsPerSite':1},
        'economics':{'realDiscountRate':0,'horizonYears':1,'buildingUnitCostTRY':1,'annualFixedSiteCostTRY':1,
            'annualDoctorCostTRY':3,'annualBedSupportCostTRY':2,'costPerContactTRY':5}}
    sites=[{'candidateIndex':j,'id':str(j),'footprintRadiusMeters':math.sqrt(8/math.pi)} for j in range(sites_count)]
    s={'mode':'transit','threshold':45,'coverageTarget':100,'districtFloor':100,'bedOccupancy':100,'demandMultiplier':1,
        'contactsPerDoctor':1,'costTolerance':10,'operatingCostMultiplier':1,'hospitalLimit':None}
    if scenario:s.update(scenario)
    matrices=matrices or {p:np.ones((2,sites_count)) for p in PROFILES}
    districts=[{'id':'a','population':pop[0]},{'id':'b','population':pop[1]}]
    args=(matrices,pop,['a','b'],districts,sum(pop),sites,h,s)
    problem=build_joint_problem(*args)
    v=np.zeros(len(problem.c))
    for j in range(2):
        x=next(x for x in problem.site_xs[j] if problem.xtype[x]==1);v[x]=1;v[problem.nx+j]=2 if problem.target else 1
    for p,(oi,sj) in problem.edges.items():
        for i in range(2):
            options=np.flatnonzero((oi==i)&(sj==i))
            if not len(options):options=np.flatnonzero((oi==i)&(sj==1-i))
            v[problem.offsets[p]+options[0]]=pop[i]*s['coverageTarget']/100/1000
    return problem,problem.serialize(v),v,args


def independently_enumerated_cost(matrices):
    # Per resident: one bed and one physician. Enumerate every relevant resource
    # assignment and all whole-person two-origin transportation possibilities.
    choices=[None]+[(beds,docs) for beds in (1,2) for docs in (1,2)]
    best=math.inf
    for chosen in product(choices,repeat=2):
        caps=[0 if x is None else min(x) for x in chosen]
        feasible=all(any(all(dest[j]<=caps[j] for j in range(2)) and all(np.isfinite(t[i,j]) for i,j in enumerate(destinations))
            for destinations in product(range(2),repeat=2) for dest in [[destinations.count(0),destinations.count(1)]]) for t in matrices.values())
        if feasible:
            # template area=beds; resource bill=3*beds+4*docs+fixed1.
            best=min(best,10+sum(3*x[0]+4*x[1]+1 for x in chosen if x is not None))
    return best


def test_explicit_builder_calls_no_native_solver(monkeypatch):
    import highspy
    monkeypatch.setattr(highspy.Highs,'run',lambda *a:pytest.fail('Pure formulation must never solve'))
    p,seed,v,args=fixture()
    assert p.dimensions['flowVariables']==16 and p.cost(v)==40
    assert p.read_plan(seed)[1]['maximumIntegralityViolation']==0


@pytest.mark.parametrize('swapped',[False,True])
def test_native_cost_matches_independent_complete_integer_enumeration(swapped):
    matrices={p:(np.array([[1,np.inf],[np.inf,1]]) if k%2==0 else np.array([[np.inf,1],[1,np.inf]])) if swapped else np.ones((2,2)) for k,p in enumerate(PROFILES)}
    p,seed,v,args=fixture(matrices)
    solved=solve_cost(p,seed,time_limit=3)
    assert solved['annualEquivalentCostTRY']==pytest.approx(independently_enumerated_cost(matrices))
    assert solved['warmStart']['solverAcceptedFeasibleStart'] is True
    assert solved['newJointAnnualBudgetTRY'] is None and solved['previousBudgetIsConstraint'] is False
    assert solved['boundScope']=='supplied_candidate_pool_all_profile_edges'
    p.read_plan(solved)


def test_four_lp_closure_uses_explicit_same_problem():
    p,seed,v,args=fixture();result=batch_close(p,seed,overall_seconds=5,trial_seconds=2,max_trials=10,batch_size=2)
    assert result['hospitalCount']==1 and result['annualEquivalentCostTRY']==pytest.approx(25)
    assert result['annualMaterialCostTRY']==10 and result['newJointAnnualBudgetTRY'] is None
    assert result['profileReassignmentPerformed'] is True
    p.read_plan(result)


@pytest.mark.parametrize('field,value',[('footprintRadiusMeters',float('nan')),('grossAreaM2',float('inf')),('doctors',True),('beds',1.5)])
def test_seed_metadata_finite_types_and_resource_identities(field,value):
    p,seed,v,args=fixture();bad=deepcopy(seed);bad['selected'][0][field]=value
    with pytest.raises(ValueError):p.read_plan(bad)


def test_closed_site_any_positive_flow_and_small_district_floor_rejected():
    p,seed,v,args=fixture(sites_count=3);bad=v.copy();oi,sj=p.edges[PROFILES[0]]
    bad[p.offsets[PROFILES[0]]+np.flatnonzero((oi==0)&(sj==2))[0]]=1e-12
    with pytest.raises(ValueError):p.validate(bad)
    # A .00005-person shortfall passes the scaled sparse row allowance but
    # violates the original percentage tolerance for a one-person district.
    mats,pop,dd,districts,total,sites,h,s=args;h=deepcopy(h);h['templates'].append({'id':'large','beds':20,'grossAreaM2':2})
    for site in sites:site['footprintRadiusMeters']=math.sqrt(100/math.pi)
    s=dict(s,coverageTarget=95,districtFloor=80)
    p=build_joint_problem(mats,[1,10],dd,[{'id':'a','population':1},{'id':'b','population':10}],11,sites,h,s)
    bad=np.zeros(len(p.c));x=next(x for x in p.site_xs[0] if p.xtype[x]==2);bad[x]=1;bad[p.nx]=11
    for name,(oi,sj) in p.edges.items():
        bad[p.offsets[name]+np.flatnonzero((oi==0)&(sj==0))[0]]=.00079995
        bad[p.offsets[name]+np.flatnonzero((oi==1)&(sj==0))[0]]=.00965005
    with pytest.raises(ValueError,match='district target'):p.validate(bad)


def test_sparse_candidate_ids_keep_profile_flow_identity():
    p,seed,v,args=fixture();mats,pop,dd,districts,total,sites,h,s=args
    ids=[17,100];sites=[dict(site,candidateIndex=ids[j]) for j,site in enumerate(sites)]
    new=build_joint_problem(mats,pop,dd,districts,total,sites,h,s)
    result=new.serialize(v);assert {x['candidateIndex'] for x in result['selected']}==set(ids)
    back,_=new.read_plan(result);assert np.array_equal(back,v)


@pytest.mark.parametrize('resource',['beds','physicians','area','hospital_limit','overlap'])
def test_resources_and_geometry_are_distinct_constraints(resource):
    p,seed,v,args=fixture();a=list(deepcopy(args));conflicts=[]
    if resource=='hospital_limit':a[-1]['hospitalLimit']=1
    if resource=='overlap':conflicts=[(0,1)]
    if resource=='area':
        a[5][0]['footprintRadiusMeters']=math.sqrt(3/math.pi)
    p=build_joint_problem(*a,conflicts=conflicts)
    if resource in ('beds','physicians'):
        v[:p.nf]=0
        x=next(x for x in p.site_xs[0] if p.xtype[x]==(0 if resource=='beds' else 1))
        v[x]=1;v[p.nx]=2 if resource=='beds' else 1
        for name,(oi,sj) in p.edges.items():
            v[p.offsets[name]:p.offsets[name]+len(oi)]=0
            for i in range(2):v[p.offsets[name]+np.flatnonzero((oi==i)&(sj==0))[0]]=.001
    with pytest.raises(ValueError):p.validate(v)


def test_empty_last_site_zero_target_closure_is_valid():
    p,seed,v,args=fixture(scenario={'coverageTarget':0,'districtFloor':0})
    result=batch_close(p,seed,overall_seconds=3,trial_seconds=1,max_trials=4,batch_size=2)
    assert result['hospitalCount']==0 and result['annualEquivalentCostTRY']==0


@pytest.mark.parametrize('mutation',['missing_profile','bad_denominator','bad_matrix','bad_limit'])
def test_builder_input_guards(mutation):
    p,seed,v,args=fixture();a=list(deepcopy(args))
    if mutation=='missing_profile':a[0].pop(PROFILES[0])
    elif mutation=='bad_denominator':a[4]+=1
    elif mutation=='bad_matrix':a[0][PROFILES[0]][0,0]=np.nan
    else:a[-1]['hospitalLimit']=True
    with pytest.raises(ValueError):build_joint_problem(*a)
