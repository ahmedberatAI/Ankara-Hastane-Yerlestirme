from copy import deepcopy
from fractions import Fraction
from itertools import product
from pathlib import Path
import sys
from types import SimpleNamespace
import numpy as np
import pytest
from scipy.sparse import csc_matrix

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from test_joint_model import fixture,PROFILES
from backend import joint_travel as t
from backend.joint_model import build_joint_problem


def example():
    matrices={p:np.array([[30.,1.],[2.,35.]]) if k%2 else np.array([[40.,3.],[1.,40.]]) for k,p in enumerate(PROFILES)}
    return fixture(matrices)


def test_four_profile_integer_enumeration_and_resource_bill_unchanged():
    p,seed,v,_=example();capture={};result=t.improve_travel(p,seed,capture=capture)
    assert result['fixedResourceTravel']['allProfilesAccepted']
    assert 'secondTravelStageImplemented' not in result
    assert result['hospitalCount']==seed['hospitalCount'] and result['totalDoctors']==seed['totalDoctors']
    assert result['totalBeds']==seed['totalBeds'] and result['annualEquivalentCostTRY']==seed['annualEquivalentCostTRY']
    assert np.array_equal(capture['sourceVector'][:p.nf],capture['finalVector'][:p.nf])
    for profile,record in zip(result['profiles'],result['fixedResourceTravel']['profiles']):
        matrix=p.times[profile['profile']]
        expected=min(sum(matrix[i,j] for i,j in enumerate(dest))/2 for dest in product(range(2),repeat=2))
        assert profile['meanMinutes']==pytest.approx(expected)
        assert record['lowerBoundMinutes']<=expected+1e-12 and record['gapMinutes']<=1e-12
        assert record['certificate']['certifiedForRepresentedFixedResourceLP']
        assert record['sourceMeanMinutes']>profile['meanMinutes']
    p.read_plan(result)


def test_zero_load_open_site_is_preserved_without_cleanup():
    p,seed,v,_=fixture({name:np.array([[1.,30.],[1.,30.]]) for name in PROFILES})
    result=t.improve_travel(p,seed)
    assert result['hospitalCount']==2 and result['selected'][1]['maximumAssignedPopulationAcrossProfiles']==0
    assert result['selected'][1]['doctors']==seed['selected'][1]['doctors']
    assert result['annualEquivalentCostTRY']==seed['annualEquivalentCostTRY']
    assert result['resourceCleanup'] is None and not result['fixedResourceTravel']['resourceCleanupPerformed']


def test_unequal_origins_use_resident_weights_and_thousand_person_units():
    _,_,_,args=fixture();args=list(deepcopy(args));args[1]=[1,3];args[3][1]['population']=3;args[4]=4
    args[-2]['templates'].append({'id':'four','beds':4,'grossAreaM2':4})
    args[0]={p:np.array([[1.+k,1.+k],[9.+k,9.+k]]) for k,p in enumerate(PROFILES)}
    p=build_joint_problem(*args);v=np.zeros(len(p.c))
    for j in range(2):v[next(x for x in p.site_xs[j] if p.xtype[x]==2)]=1;v[p.nx+j]=4
    for name,(oi,sj) in p.edges.items():
        for i,pop in enumerate((1,3)):v[p.offsets[name]+np.flatnonzero((oi==i)&(sj==i))[0]]=pop/1000
    result=t.improve_travel(p,p.serialize(v))
    assert [x['meanMinutes'] for x in result['profiles']]==pytest.approx([7,8,9,10])
    assert [x['meanMinutes'] for x in result['profiles']]!=[5,6,7,8]


def test_mixed_accepted_and_unknown_profiles_do_not_mean_all_optimal(monkeypatch):
    p,seed,v,_=example();original=t._solve;calls=[0]
    def mixed(*args):
        calls[0]+=1
        return SimpleNamespace(status=1,x=None) if calls[0]==1 else original(*args)
    monkeypatch.setattr(t,'_solve',mixed)
    result=t.improve_travel(p,seed)
    records=result['fixedResourceTravel']['profiles']
    assert [x['accepted'] for x in records]==[False,True,True,True]
    assert not result['fixedResourceTravel']['allProfilesAccepted']
    assert result['profiles'][0]['allocations']==seed['profiles'][0]['allocations']


def test_bed_and_physician_capacity_both_limit_assignment():
    p,seed,v,_=fixture({name:np.array([[1.,30.],[1.,30.]]) for name in PROFILES})
    # Site 0: one bed, two doctors; site 1: two beds, one doctor.
    v[p.site_xs[0]]=0;v[next(x for x in p.site_xs[0] if p.xtype[x]==0)]=1;v[p.nx+1]=1
    seed=p.serialize(v);result=t.improve_travel(p,seed)
    assert all(x['meanMinutes']==pytest.approx(15.5) for x in result['profiles'])
    assert result['totalBeds']==3 and result['totalDoctors']==3


@pytest.mark.parametrize('case',['negative','nan','badshape','origin','unknown','infeasible','no_dual','worse'])
def test_bad_or_unknown_lp_preserves_each_original_profile(monkeypatch,case):
    p,seed,v,_=example()
    def fake(lp,seconds):
        f=np.zeros(len(lp['c']));f[0]=.001;f[-1]=.001
        status=0;kwargs={'ineqlin':SimpleNamespace(marginals=np.zeros(len(lp['b']))),'eqlin':SimpleNamespace(marginals=np.zeros(1))}
        if case=='negative':f[1]=-1e-12
        if case=='nan':f[0]=np.nan
        if case=='badshape':f=f[:-1]
        if case=='origin':f[0]=.002;f[-1]=0
        if case=='unknown':status=1
        if case=='infeasible':status=2
        if case=='no_dual':kwargs={}
        if case=='worse':
            # A valid but worse assignment for the low-cost source below.
            pass
        return SimpleNamespace(status=status,x=f,message='adverse synthetic LP',**kwargs)
    if case=='worse':
        solved=t.improve_travel(p,seed);seed=solved;v=p.read_plan(seed)[0]
    monkeypatch.setattr(t,'_solve',fake)
    result=t.improve_travel(p,seed);back,_=p.read_plan(result)
    assert np.array_equal(back,v)
    assert all(not x['accepted'] and x['sourceFallback'] for x in result['fixedResourceTravel']['profiles'])
    assert not result['fixedResourceTravel']['allProfilesAccepted']


def test_deadline_during_assembly_or_after_native_never_accepts(monkeypatch):
    p,seed,v,_=example();now=[0.];original=t.formulate_profile
    def slow(*a):
        lp=original(*a);now[0]=2.;return lp
    monkeypatch.setattr(t,'formulate_profile',slow)
    monkeypatch.setattr(t,'_solve',lambda *a:pytest.fail('No native LP after deadline'))
    record,back=t.one_profile(p,v,PROFILES[0],1.,clock=lambda:now[0])
    assert not record['accepted'] and np.array_equal(back,v)
    monkeypatch.setattr(t,'formulate_profile',original);now[0]=0.
    def late(*a):now[0]=2.;return SimpleNamespace(status=0,x=None)
    monkeypatch.setattr(t,'_solve',late)
    record,back=t.one_profile(p,v,PROFILES[0],1.,clock=lambda:now[0])
    assert not record['accepted'] and np.array_equal(back,v)


def test_finite_box_dual_bound_against_all_corners_and_sign_clipping():
    rng=np.random.default_rng(817)
    for _ in range(100):
        A=rng.integers(-2,3,(2,3)).astype(float);upper=rng.integers(1,4,3).astype(float)
        b=rng.integers(0,5,2).astype(float);c=rng.integers(-3,4,3).astype(float)
        y=rng.normal(size=2);E=np.zeros((0,3));d=np.zeros(0);z=np.zeros(0)
        bound=t.exact_box_dual(c,csc_matrix(A),b,csc_matrix(E),d,upper,y,z)
        exact=Fraction(int(bound['exactNumerator']),int(bound['exactDenominator']))
        # Exact weak duality against every feasible corner, independent of
        # solver output or marginal stationarity; arbitrary signs are repaired.
        for bits in product((0,1),repeat=3):
            x=np.array(bits)*upper
            if np.all(A@x<=b):assert exact<=Fraction.from_float(float(c@x))
        assert Fraction.from_float(bound['lowerBoundMinutes'])<=exact
    # A box residual term is essential when a negative reduced cost exists.
    bound=t.exact_box_dual(np.array([-2.]),csc_matrix((0,1)),np.zeros(0),csc_matrix((0,1)),np.zeros(0),np.array([3.]),np.zeros(0),np.zeros(0))
    assert bound['lowerBoundMinutes']==-6


def test_downward_rounding_cannot_certify_infinite_lower_bound():
    c=np.array([-np.finfo(float).max,-1e290])
    with pytest.raises(ValueError,match='after downward rounding'):
        t.exact_box_dual(c,csc_matrix((0,2)),np.zeros(0),csc_matrix((0,2)),np.zeros(0),np.ones(2),np.zeros(0),np.zeros(0))


@pytest.mark.parametrize('kwargs',[{'overall_seconds':61},{'profile_seconds':16},{'overall_seconds':float('nan')}])
def test_control_limits(kwargs):
    p,seed,v,_=example()
    with pytest.raises(ValueError):t.improve_travel(p,seed,**kwargs)


@pytest.mark.parametrize('error',[ValueError('numerical solver failure'),RuntimeError('native solver unavailable')])
def test_native_failure_preserves_exact_source_profile_json(monkeypatch,error):
    p,seed,v,_=example()
    def fail(*args):raise error
    monkeypatch.setattr(t,'_solve',fail)
    result=t.improve_travel(p,seed)
    assert result['profiles']==seed['profiles']
    assert all(x['sourceFallback'] for x in result['fixedResourceTravel']['profiles'])
    assert not result['profileReassignmentPerformed']


@pytest.mark.parametrize('mutation',['missing','duplicate','unknown','order'])
def test_profile_identity_invalid_before_any_native_call(monkeypatch,mutation):
    p,seed,v,_=example();seed=deepcopy(seed)
    if mutation=='missing':seed['profiles'].pop()
    elif mutation=='duplicate':seed['profiles'][-1]=deepcopy(seed['profiles'][0])
    elif mutation=='unknown':seed['profiles'][0]['profile']='weekday-1700'
    else:seed['profiles'].reverse()
    monkeypatch.setattr(t,'_solve',lambda *a:pytest.fail('Must validate source identities first'))
    with pytest.raises(ValueError):t.improve_travel(p,seed)
