"""Independent tiny enumeration and invariants for the fixed-site prototype."""
from copy import deepcopy
from itertools import product
from types import SimpleNamespace
import math
import numpy as np
import pytest
import backend.shared_capacity as shared


def fixture():
    planning = {'version': 'test', 'rates': {'contactsPerResident': 1, 'bedDaysPerResident': 365},
        'templates': [{'id': 'one', 'beds': 1, 'grossAreaM2': 1},
                      {'id': 'two', 'beds': 2, 'grossAreaM2': 2}],
        'design': {'areaPerDoctorM2': 1, 'maxFloors': 1, 'minimumDoctorsPerSite': 1},
        'economics': {'realDiscountRate': 0, 'horizonYears': 1, 'buildingUnitCostTRY': 1,
            'annualFixedSiteCostTRY': 1, 'annualBedSupportCostTRY': 2,
            'annualDoctorCostTRY': 3, 'costPerContactTRY': 5}}
    sites = [{'candidateIndex': i + 20, 'id': str(i), 'footprintRadiusMeters': math.sqrt(5 / math.pi)} for i in range(2)]
    scenario = {'threshold': 45, 'coverageTarget': 100, 'districtFloor': 100,
        'bedOccupancy': 100, 'demandMultiplier': 1, 'contactsPerDoctor': 1,
        'operatingCostMultiplier': 1}
    return planning, sites, scenario


def solve(profiles=None, pop=(2, 2), budget=None, **changes):
    planning, sites, scenario = fixture()
    planning = changes.pop('planning', planning)
    sites = changes.pop('sites', sites)
    scenario.update(changes)
    return shared.repair_shared_capacity(profiles or {'one': np.ones((2, 2))}, pop,
        np.array(['a', 'b']), [{'id': 'a', 'population': pop[0]}, {'id': 'b', 'population': pop[1]}],
        sum(pop), sites, planning, scenario, original_annual_budget=budget, time_limit=3)


def enumerate_cost(profiles, pop):
    """No MILP/LP: enumerate resource choices and integral bipartite flows.

    Tiny populations are integers; the fixed-resource transportation network has
    an integral optimum, so this enumeration also checks continuous feasibility.
    """
    best = math.inf
    options = [(beds, doctors) for beds in (1, 2) for doctors in range(1, 6 - beds)]
    for resources in product(options, repeat=2):
        capacities = [min(b, d) for b, d in resources]
        for t in profiles.values():
            possible = False
            for to_first in product(*(range(p + 1) for p in pop)):
                flow = np.array([[to_first[i], pop[i] - to_first[i]] for i in range(2)])
                if np.any((flow > 0) & (t > 45)) or np.any(flow.sum(axis=0) > capacities):
                    continue
                possible = True
                break
            if not possible:
                break
        else:
            cost = sum((b + docs) + 1 + b * 2 + docs * 3 for b, docs in resources) + sum(pop) * 5
            best = min(best, cost)
    return best


def test_swapped_profiles_share_resources_but_not_flows():
    profiles = {'first': np.array([[1, np.inf], [np.inf, 1]]),
                'second': np.array([[np.inf, 1], [1, np.inf]])}
    assert np.isinf(np.maximum(*profiles.values())).all()
    result = solve(profiles, pop=(1, 2))
    assert result['status'] == 'feasible'
    assert result['totalBeds'] == result['totalDoctors'] == 4
    assert result['annualEquivalentCostTRY'] == pytest.approx(enumerate_cost(profiles, (1, 2)))
    assert result['profiles'][0]['siteLoads'] == [1, 2]
    assert result['profiles'][1]['siteLoads'] == [2, 1]
    assert result['provenOptimal']


def test_small_random_problems_match_independent_enumeration():
    rng = np.random.default_rng(928)
    for _ in range(24):
        profiles = {str(p): np.where(rng.random((2, 2)) < .75, 10, np.inf) for p in range(3)}
        pop = tuple(int(v) for v in rng.integers(1, 3, 2))
        expected = enumerate_cost(profiles, pop)
        result = solve(profiles, pop=pop)
        if math.isinf(expected):
            assert result['status'] == 'infeasible'
        else:
            assert result['status'] == 'feasible'
            assert result['annualEquivalentCostTRY'] == pytest.approx(expected)
            assert result['minimumAnnualCostLowerBoundTRY'] == pytest.approx(expected)


def test_materials_are_once_and_all_edges_retained():
    result = solve({str(i): np.ones((2, 2)) for i in range(4)})
    single = solve()
    assert result['annualMaterialCostTRY'] == 20
    assert result['annualEquivalentCostTRY'] == single['annualEquivalentCostTRY'] == 50
    assert result['allocationEdgesByProfile'] == {str(i): 4 for i in range(4)}
    assert result['allSitesMandatoryOpen'] and result['annualDemandCountedOnce']


def test_bed_physician_and_physical_area_limits_are_distinct():
    p, sites, _ = fixture()
    p['templates'] = p['templates'][:1]
    assert solve(planning=p)['status'] == 'infeasible'  # at most two beds, demand four
    p, sites, _ = fixture()
    for s in sites:
        s['footprintRadiusMeters'] = math.sqrt(3 / math.pi)
    assert solve(sites=sites)['status'] == 'infeasible'  # two beds leave only one physician
    for s in sites:
        s['footprintRadiusMeters'] = math.sqrt(1.5 / math.pi)
    assert 'cannot fit' in solve(sites=sites)['reason']
    assert solve(demandMultiplier=2)['status'] == 'infeasible'
    assert solve(bedOccupancy=50)['status'] == 'infeasible'


def test_budget_is_reported_without_reducing_coverage():
    within = solve(budget=50)
    over = solve(budget=40)
    assert within['meetsOriginalBudget'] is True
    assert over['budgetStatus'] == 'proven_over_original_budget_for_fixed_sites'
    assert over['status'] == 'feasible' and over['meetsOriginalBudget'] is False
    assert all(p['coveredPopulation'] == pytest.approx(4) for p in over['profiles'])
    assert not over['budgetIsOptimizationConstraint']


def test_time_limit_valid_incumbent_and_unresolved_budget(monkeypatch):
    original = shared.optimize
    def limited(*args, **kwargs):
        r = original(*args, **kwargs)
        r.status = 1
        r.mip_dual_bound = 0
        return r
    monkeypatch.setattr(shared, 'optimize', limited)
    result = solve(budget=40)
    assert result['status'] == 'feasible' and result['timeLimitedFeasible']
    assert result['budgetStatus'] == 'incumbent_over_budget_unresolved'
    assert result['provenOptimal'] is False


def test_no_incumbent_timeout_is_not_infeasibility(monkeypatch):
    monkeypatch.setattr(shared, 'optimize', lambda *a, **k: SimpleNamespace(
        status=1, x=None, mip_dual_bound=0., mip_gap=np.inf))
    result = solve(budget=100)
    assert result['status'] == 'inconclusive'
    assert result['meetsOriginalBudget'] is None and not result['selected']


@pytest.mark.parametrize('corruption', ['integer', 'resource', 'negative_flow', 'cost_bound'])
def test_invalid_numeric_incumbent_or_bound_is_not_accepted(monkeypatch, corruption):
    original = shared.optimize
    def corrupt(*args, **kwargs):
        r = original(*args, **kwargs)
        if corruption == 'integer':
            r.x[4] = 1.2
        elif corruption == 'resource':
            r.x[4] = 1  # insufficient physician capacity for four people
        elif corruption == 'negative_flow':
            r.x[-1] = -1
        else:
            r.mip_dual_bound += 100
        return r
    monkeypatch.setattr(shared, 'optimize', corrupt)
    if corruption == 'cost_bound':
        with pytest.raises(RuntimeError, match='lower bound'):
            solve()
    else:
        assert solve()['status'] == 'inconclusive'


def test_exact_provincial_target_and_district_floors_cannot_conflict():
    result = solve(coverageTarget=50, districtFloor=80)
    assert result['status'] == 'infeasible'
    result = solve(coverageTarget=50, districtFloor=50)
    assert result['status'] == 'feasible'
    assert all(x['coveredPopulation'] == pytest.approx(2) for x in result['profiles'])


@pytest.mark.parametrize('change', [
    {'bedOccupancy': 0}, {'contactsPerDoctor': 0}, {'coverageTarget': 101},
    {'districtFloor': -1}, {'demandMultiplier': np.nan}, {'threshold': -1},
    {'operatingCostMultiplier': 0},
])
def test_scenario_guards(change):
    with pytest.raises(ValueError):
        solve(**change)


def test_matrix_population_and_site_guards():
    with pytest.raises(ValueError):
        solve({'p': [[-1, 1], [1, 1]]})
    with pytest.raises(ValueError):
        solve({'p': [[np.nan, 1], [1, 1]]})
    with pytest.raises(ValueError):
        solve({'p': [[1, 1]]})
    _, sites, _ = fixture()
    sites[1]['candidateIndex'] = sites[0]['candidateIndex']
    with pytest.raises(ValueError):
        solve(sites=sites)
    p, sites, s = fixture()
    with pytest.raises(ValueError, match='denominators'):
        shared.repair_shared_capacity({'a': np.ones((2, 2))}, [2, 2], ['a', 'b'],
            [{'id': 'a', 'population': 2}, {'id': 'b', 'population': 2}], 5, sites, p, s)
    # Missing population remains in the total: 100% cannot cover it.
    result = shared.repair_shared_capacity({'a': np.ones((2, 2))}, [1, 2], ['a', 'b'],
        [{'id': 'a', 'population': 2}, {'id': 'b', 'population': 2}], 4, sites, p, s)
    assert result['status'] == 'infeasible'
