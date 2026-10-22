import copy
import itertools
import math
import numpy as np
import pytest
from scipy.optimize import linprog
from backend.capacity import solve_capacity, annualization
from backend.feasibility import geographic_bound


def planning(beds=10,bed_days=.1):
    return {'version':'test','rates':{'contactsPerResident':1.,'visitsPerResident':.9,
            'admissionsPerResident':.1,'bedDaysPerResident':bed_days},
        'templates':[{'id':'s','label':'small','beds':beds,'grossAreaM2':100}],
        'design':{'areaPerDoctorM2':10,'minimumDoctorsPerSite':1,'maxFloors':1},
        'economics':{'realDiscountRate':0,'horizonYears':10,'buildingUnitCostTRY':10000,
            'annualFixedSiteCostTRY':100000,'annualBedSupportCostTRY':100,
            'annualDoctorCostTRY':1000,'costPerContactTRY':1,'priceBase':'test'}}


def solve(times,pop,p,**kw):
    pop=np.asarray(pop); kw.setdefault('coverage_target',1);kw.setdefault('district_floor',1)
    kw.setdefault('cost_tolerance',0);kw.setdefault('neighbors',None)
    return solve_capacity(np.asarray(times,dtype=float),pop,np.array(['A']*len(pop)),
        [{'id':'A','name':'A','population':int(pop.sum())}],int(pop.sum()),p,
        contacts_per_doctor=1000,time_limit=3,**kw)


def test_staff_grows_without_forcing_extra_beds_or_sites():
    a=solve([[1]],[2000],planning())
    b=solve([[1]],[4000],planning())
    assert a['hospitalCount']==b['hospitalCount']==1
    assert a['capacity']['totalBeds']==b['capacity']['totalBeds']==10
    assert a['capacity']['totalDoctors']==2 and b['capacity']['totalDoctors']==4
    assert b['capacity']['annualOperatingCostTRY']>a['capacity']['annualOperatingCostTRY']


def test_bed_capacity_remains_binding_even_with_independent_staff():
    r=solve([[1,3]],[500],planning(beds=1,bed_days=1))
    assert r['hospitalCount']==2
    assert all(c['annualBedDays']<=292+1e-5 for c in r['capacitySites'])
    assert sum(c['annualBedDays'] for c in r['capacitySites'])==pytest.approx(500)


def test_large_bed_option_makes_one_site_feasible():
    p=planning(beds=1,bed_days=1)
    r=solve([[1]],[500],p,hospital_limit=1)
    assert r['status']=='infeasible'
    p['templates'].append({'id':'large','label':'large','beds':2,'grossAreaM2':150})
    r=solve([[1]],[500],p,hospital_limit=1)
    assert r['hospitalCount']==1 and r['capacity']['totalBeds']==2


def test_area_includes_independently_chosen_staff_space():
    # 100 m² bed module + one physician (10 m²) fits; two do not.
    radius=math.sqrt(115/math.pi)
    r=solve([[1]],[2000],planning(),plot_radii=[radius])
    assert r['status']=='infeasible'
    r=solve([[1]],[1000],planning(),plot_radii=[radius])
    assert r['capacitySites'][0]['grossAreaM2']==110


def test_site_limit_cannot_be_evaded_by_multiple_templates_at_one_location():
    p=planning(beds=1,bed_days=1)
    r=solve([[1,2]],[500],p,hospital_limit=1)
    assert r['status']=='infeasible'
    r=solve([[1,2]],[500],p,hospital_limit=2)
    assert r['hospitalCount']==2


def test_unknown_population_remains_in_target_denominator():
    r=solve_capacity(np.array([[1.]]),np.array([80]),np.array(['A']),
        [{'id':'A','name':'A','population':100}],100,planning(),coverage_target=.95,district_floor=0)
    assert r['status']=='infeasible' and r['maximumCoveragePercent']==80


def test_exhaustive_tiny_location_staff_and_flow_enumeration():
    p=planning(beds=3,bed_days=.5)
    times=np.array([[1.,5.,np.inf],[np.inf,5.,1.]])
    population=np.array([900.,900.]); best=np.inf
    # Enumerate independent staffing, not merely size choices. LP checks flows.
    for ds in itertools.product(range(3),repeat=3):
        opened=np.array(ds)>0
        caps=np.minimum(np.array(ds)*1000,opened*3*292/.5)
        alloc=linprog(np.zeros(6),A_ub=np.tile(np.eye(3),(1,2)),b_ub=caps,
            A_eq=np.kron(np.eye(2),np.ones((1,3))),b_eq=population,
            bounds=[(0,None) if np.isfinite(t) else (0,0) for t in times.ravel()])
        if not alloc.success: continue
        capex=(100*opened.sum()+10*sum(ds))*10000
        opex=opened.sum()*(100000+3*100)+sum(ds)*1000+population.sum()
        best=min(best,capex*annualization(p)+opex)
    result=solve(times,population,p)
    assert result['capacity']['annualEquivalentCostTRY']==pytest.approx(best)


def test_operating_cost_changes_location_decision_not_only_display():
    p=planning();p['economics']['annualFixedSiteCostTRY']=0
    # One centrally shared site is possible, but fixed operating charges must
    # make two sites strictly more costly in first stage.
    q=copy.deepcopy(p);q['economics']['annualFixedSiteCostTRY']=1000000
    a=solve([[1,10],[10,1]],[1000,1000],p)
    b=solve([[1,10],[10,1]],[1000,1000],q)
    assert a['capacity']['referenceCostTRY']+1000000==pytest.approx(b['capacity']['referenceCostTRY'])
    assert b['hospitalCount']==1


def test_extra_annual_budget_keeps_demand_and_can_reduce_travel():
    p=planning()
    r=solve([[1,10,30],[30,10,1]],[1000,1000],p,cost_tolerance=1)
    assert r['metrics']['coveredPopulation']==pytest.approx(2000)
    assert r['metrics']['meanMinutes']==pytest.approx(1)
    c=r['capacity'];assert c['annualEquivalentCostTRY']<=c['budgetLimitTRY']+1
    assert c['lifecyclePresentCostTRY']==pytest.approx(c['constructionCostTRY']+10*c['annualOperatingCostTRY'])


def test_plot_conflicts_are_preserved():
    r=solve([[1,2,3]],[500],planning(beds=1,bed_days=1),conflicts=[(0,1)])
    assert not {0,1}.issubset(r['selectedIndices'])


def test_restricted_infeasibility_does_not_claim_full_problem_impossible():
    r=solve([[1,2]],[500],planning(beds=1,bed_days=1),neighbors=1)
    assert r['status']=='inconclusive'
    assert solve([[1,2]],[500],planning(beds=1,bed_days=1))['hospitalCount']==2


def test_geo_bound_is_necessary_and_uses_all_candidate_edges():
    r=geographic_bound(np.array([[1,np.inf],[np.inf,1]]),np.array([100,100]),np.array(['A','B']),
        [{'id':'A','population':100},{'id':'B','population':100}],200,30,.95,.8,time_limit=3)
    assert r['minimumCountLowerBound']==pytest.approx(2)
    assert r['fullCandidateCount']==2
