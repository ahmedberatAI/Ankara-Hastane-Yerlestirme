import itertools
import numpy as np
from backend.optimizer import solve_cover, metrics, weighted_quantile, undominated_columns
from backend.geo import permissions, normalize

def test_minimum_count_matches_brute_force_and_respects_rural_floor():
    # A single central hospital reaches 90%, but leaves the rural district out.
    times = np.array([[2., 40., 10.], [3., 40., 15.], [90., 4., 60.]])
    pop = np.array([50, 40, 10])
    ids = np.array(['urban', 'urban', 'rural'])
    districts = [{'id':'urban','name':'Merkez','population':90}, {'id':'rural','name':'Kırsal','population':10}]
    result = solve_cover(times, pop, ids, districts, 100, threshold=20, coverage_target=.9, district_floor=.8, time_limit=3)
    feasible_counts = []
    for k in range(1, 4):
        for selected in itertools.combinations(range(3), k):
            covered = times[:, selected].min(axis=1) <= 20
            if pop[covered].sum() >= 90 and all(pop[covered & (ids == d['id'])].sum() >= .8*d['population'] for d in districts):
                feasible_counts.append(k)
    assert result['status'] == 'optimal'
    assert result['hospitalCount'] == min(feasible_counts) == 2
    assert result['metrics']['coveragePercent'] == 100
    assert all(d['coveragePercent'] >= 80 for d in result['districts'])

def test_unknown_population_does_not_disappear_from_denominator():
    result = solve_cover(np.array([[3.]]), np.array([80]), np.array(['A']),
                         [{'id':'A','name':'A','population':100}], 100,
                         coverage_target=.95, district_floor=0)
    assert result['status'] == 'infeasible'
    assert result['maximumCoveragePercent'] == 80

def test_unreachable_is_not_replaced_by_a_straight_line_time():
    result = metrics(np.array([5.,np.inf]), np.array([80,20]), 100, 30)
    assert result['coveragePercent'] == 80
    assert result['p90Minutes'] is None
    assert result['meanPopulationDenominator'] == 80

def test_local_refinement_cannot_break_coverage_or_count():
    times = np.array([[1, 20, 100], [20, 1, 100], [100, 100, 1]], dtype=float)
    result = solve_cover(times, np.array([30,30,40]), np.array(['A','A','B']),
                         [{'id':'A','name':'A','population':60},{'id':'B','name':'B','population':40}],
                         100, threshold=10, coverage_target=1, district_floor=1, time_limit=3)
    assert result['hospitalCount'] == 3
    assert result['metrics']['coveredPopulation'] == 100

def test_access_and_turkish_join_keys():
    assert permissions({'highway':'motorway'}) == (True, False)
    assert permissions({'highway':'residential','access':'private'}) == (False, False)
    assert permissions({'highway':'residential','access':'private','foot':'yes'}) == (False, True)
    assert permissions({'highway':'footway'}) == (False, True)
    assert normalize('İNCİRLİ Mahallesi') == normalize('incirli')

def test_weighted_quantile_accounts_for_unlocated_population():
    assert weighted_quantile([10,20,np.inf],[40,40,20],.9) is None
    assert weighted_quantile([10,20,np.inf],[45,50,5],.9) == 20

def test_primary_dominance_preserves_all_reachable_demand():
    cover = np.array([[1,1,0,1,0], [0,1,0,1,0], [0,0,1,0,0]], dtype=bool)
    keep = undominated_columns(cover)
    assert keep.tolist() == [1,2]
    assert np.array_equal(cover[:,keep].any(axis=1), cover.any(axis=1))
