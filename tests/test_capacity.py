import copy
import itertools
import numpy as np
import pytest
from scipy.optimize import linprog
from backend.capacity import solve_capacity


def planning(beds=20, doctors=1, visits=1., bed_days=.1):
    return {'version': 'test', 'rates': {'visitsPerResident': visits, 'bedDaysPerResident': bed_days,
                                        'admissionsPerResident': bed_days / 5},
            'templates': [{'id': 's', 'label': 'test', 'beds': beds, 'doctors': doctors,
                           'grossAreaM2': 100, 'constructionCostTRY': 100_000_000}]}


def solve(times, pop, plan, **kw):
    pop = np.array(pop)
    return solve_capacity(np.array(times, dtype=float), pop, np.array(['A'] * len(pop)),
            [{'id': 'A', 'name': 'A', 'population': int(pop.sum())}], int(pop.sum()), plan,
            coverage_target=1, district_floor=1, cost_tolerance=0, time_limit=3, **kw)


def test_doctor_capacity_splits_dense_neighborhood_across_two_hospitals():
    r = solve([[1, 3]], [8000], planning())
    assert r['hospitalCount'] == 2
    assert len(r['assignments'][0]['allocations']) == 2
    assert sum(a['population'] for a in r['assignments'][0]['allocations']) == pytest.approx(8000)
    assert r['metrics']['meanMinutes'] == pytest.approx(2)
    for c in r['capacitySites']:
        assert c['annualVisits'] <= c['visitCapacity'] + 1e-5
        assert c['annualBedDays'] <= c['bedDayCapacity'] + 1e-5


def test_bed_capacity_is_independent_of_generous_doctor_capacity():
    r = solve([[1, 3]], [500], planning(beds=1, doctors=10, bed_days=1))
    assert r['hospitalCount'] == 2
    assert r['capacity']['totalBeds'] == 2
    assert all(c['annualBedDays'] <= 292 + 1e-5 for c in r['capacitySites'])


def test_demand_multiplier_can_require_additional_facility():
    normal = solve([[1, 3]], [4000], planning())
    doubled = solve([[1, 3]], [4000], planning(), demand_multiplier=2)
    assert normal['hospitalCount'] == 1
    assert doubled['hospitalCount'] == 2
    assert doubled['capacity']['annualVisitsDemand'] == 8000


def test_unreachable_and_unknown_demand_cannot_be_filled_with_capacity():
    r = solve_capacity(np.array([[1., np.inf]]), np.array([80]), np.array(['A']),
                       [{'id': 'A', 'name': 'A', 'population': 100}], 100, planning(),
                       coverage_target=.95, district_floor=0, time_limit=2)
    assert r['status'] == 'infeasible'
    assert r['maximumCoveragePercent'] == 80


def test_insufficient_total_capacity_returns_infeasible_not_overloaded_solution():
    r = solve([[1]], [8000], planning())
    assert r['status'] == 'infeasible'
    assert 'assignments' not in r


def test_cost_matches_exhaustive_facility_enumeration_on_small_network():
    # Three possible sites, two capacities, 3**3 opening/size combinations.
    p = planning()
    large = copy.deepcopy(p['templates'][0])
    large.update(id='l', doctors=2, constructionCostTRY=170_000_000)
    p['templates'].append(large)
    times = np.array([[1., 5., np.inf], [np.inf, 5., 1.]])
    pop = np.array([3000., 3000.])
    best = np.inf
    for sizes in itertools.product(range(3), repeat=3):
        cap = np.array([0 if s == 0 else p['templates'][s-1]['doctors'] * 4000 for s in sizes])
        cost = sum(0 if s == 0 else p['templates'][s-1]['constructionCostTRY'] for s in sizes)
        bounds = [(0, None) if np.isfinite(t) else (0, 0) for t in times.ravel()]
        allocation = linprog(np.zeros(6), A_ub=np.tile(np.eye(3), (1,2)), b_ub=cap,
                            A_eq=np.kron(np.eye(2), np.ones((1,3))), b_eq=pop, bounds=bounds)
        if allocation.success:
            best = min(best, cost)
    r = solve(times, pop, p)
    assert r['capacity']['constructionCostTRY'] == pytest.approx(best)
    assert r['capacity']['referenceCostTRY'] == pytest.approx(best)


def test_extra_budget_preserves_served_demand_and_shortens_journey():
    p = planning()
    r = solve_capacity(np.array([[1., 10., 30.], [30., 10., 1.]]), np.array([1500, 1500]),
        np.array(['A','A']), [{'id':'A','name':'A','population':3000}], 3000, p,
        coverage_target=1, district_floor=1, cost_tolerance=1, time_limit=3)
    assert r['metrics']['coveredPopulation'] == pytest.approx(3000)
    assert r['capacity']['referenceCostTRY'] == pytest.approx(100_000_000)
    assert r['capacity']['constructionCostTRY'] <= r['capacity']['budgetLimitTRY'] + 1
    assert r['metrics']['meanMinutes'] <= r['capacity']['referenceMeanMinutes']
    assert r['metrics']['meanMinutes'] == pytest.approx(1)


def test_district_floor_is_preserved_with_split_capacity_assignments():
    r = solve_capacity(np.array([[1., 30.], [30., 1.]]), np.array([900,100]), np.array(['A','B']),
        [{'id':'A','name':'urban','population':900},{'id':'B','name':'rural','population':100}],
        1000, planning(), threshold=10, coverage_target=.9, district_floor=.8, time_limit=3)
    assert r['hospitalCount'] == 2
    assert all(d['coveragePercent'] >= 80 - 1e-6 for d in r['districts'])


def test_overlapping_sites_cannot_both_open():
    r = solve([[1, 2, 3]], [8000], planning(), conflicts=[(0,1)])
    assert not {0,1}.issubset(r['selectedIndices'])
    assert r['hospitalCount'] == 2
    assert r['metrics']['coveredPopulation'] == pytest.approx(8000)
