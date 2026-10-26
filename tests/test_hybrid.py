"""Small independent hybrid resource/allocation and failure-scope checks."""
from copy import deepcopy
from itertools import product
from types import SimpleNamespace
import math
import numpy as np
import pytest

import backend.hybrid as h


def case(car=None, transit=None, *, scenario=None, pop=(1, 1), sites=2):
    health = {'version': 'tiny', 'rates': {'contactsPerResident': 1, 'bedDaysPerResident': 365},
        'templates': [{'id': 'one', 'beds': 1, 'grossAreaM2': 1}, {'id': 'two', 'beds': 2, 'grossAreaM2': 2}],
        'design': {'areaPerDoctorM2': 1, 'maxFloors': 1, 'minimumDoctorsPerSite': 1},
        'economics': {'realDiscountRate': 0, 'horizonYears': 1, 'buildingUnitCostTRY': 1,
            'annualFixedSiteCostTRY': 1, 'annualDoctorCostTRY': 3, 'annualBedSupportCostTRY': 2,
            'costPerContactTRY': 5}}
    s = {'threshold': 30, 'transitThreshold': 45, 'carWeight': 70, 'coverageTarget': 100,
        'districtFloor': 100, 'bedOccupancy': 100, 'demandMultiplier': 1,
        'contactsPerDoctor': 1, 'costTolerance': 10, 'operatingCostMultiplier': 1,
        'hospitalLimit': None, 'hybridNeighbors': None}
    s.update(scenario or {})
    candidates = [{'candidateIndex': 10 + j * 7, 'id': str(j), 'footprintRadiusMeters': math.sqrt(8 / math.pi)} for j in range(sites)]
    districts = [{'id': str(i), 'population': x} for i, x in enumerate(pop)]
    return (np.ones((len(pop), sites)) if car is None else np.asarray(car, dtype=float),
        np.ones((len(pop), sites)) if transit is None else np.asarray(transit, dtype=float),
        np.asarray(pop, dtype=float), np.array([str(i) for i in range(len(pop))]), districts,
        sum(pop), health, s, candidates)


def build(args, **kw):
    return h.build_hybrid_problem(*args, neighbors=args[7]['hybridNeighbors'], **kw)


def independent_cost(car, transit):
    # Enumerate all whole-person assignments and integer pairs. This tiny unit
    # model is a network flow with integral capacities, so integer flows suffice.
    best = math.inf
    for resources in product([None] + list(product((1, 2), (1, 2))), repeat=2):
        capacities = [0 if pair is None else min(pair) for pair in resources]
        possible = True
        for t, limit in ((car, 30), (transit, 45)):
            possible &= any(all(t[i, j] <= limit for i, j in enumerate(assign))
                and all(assign.count(j) <= capacities[j] for j in range(2))
                for assign in product(range(2), repeat=2))
        if possible:
            best = min(best, 10 + sum(3 * pair[0] + 4 * pair[1] + 1 for pair in resources if pair))
    return best


def test_pure_builder_keeps_two_complete_demands_and_one_material_bill(monkeypatch):
    import highspy
    monkeypatch.setattr(highspy.Highs, 'run', lambda *a: pytest.fail('No native call in builder'))
    p = build(case())
    assert list(p.times) == ['car', 'transit']
    assert p.dimensions['flowVariables'] == 8
    assert p.material == 10
    assert p.target == 2


@pytest.mark.parametrize('swapped', [False, True])
def test_cost_matches_independent_two_mode_enumeration(swapped):
    car = np.array([[1, np.inf], [np.inf, 1]]) if swapped else np.ones((2, 2))
    transit = np.array([[np.inf, 1], [1, np.inf]]) if swapped else car
    args = case(car, transit, scenario={'costTolerance': 0})
    result = h.solve_hybrid(*args, time_limit=4)
    assert result['status'] == 'feasible'
    assert result['capacity']['annualEquivalentCostTRY'] == pytest.approx(independent_cost(car, transit))
    assert result['capacity']['annualMaterialCostTRY'] == 10
    assert result['capacity']['totalDoctors'] == 2
    assert result['capacity']['totalBeds'] == 2
    assert result['hybridSummary']['annualDemandCountedOnce']
    for mode in h.MODES:
        assert result['modalResults'][mode]['metrics']['coveredPopulation'] == pytest.approx(2)
    assert sum(x['operatingBreakdown']['materialsTRY'] for x in result['capacitySites']) == pytest.approx(10)


@pytest.mark.parametrize('weight', [0, 70, 100])
def test_unreachable_transit_cannot_be_hidden_by_weight_or_car(weight):
    args = case(transit=[[np.inf, np.inf], [1, 1]], scenario={'carWeight': weight})
    result = h.solve_hybrid(*args, time_limit=2)
    assert result['status'] == 'infeasible'
    assert 'transit' in result['reason']
    assert not result['incumbentValidated']


def test_distinct_hard_limits_even_if_internal_threshold_is_larger():
    p = build(case(car=[[30, 31], [31, 30]], transit=[[45, 46], [46, 45]]))
    assert np.isinf(p.times['car'][0, 1])
    assert np.isinf(p.times['transit'][0, 1])
    assert len(p.edges['car'][0]) == len(p.edges['transit'][0]) == 2


@pytest.mark.parametrize('weight,site', [(90, 10), (10, 17)])
def test_weight_affects_travel_choice_but_not_demand(weight, site):
    args = case(car=[[1, 20], [1, 20]], transit=[[20, 1], [20, 1]],
        scenario={'carWeight': weight, 'hospitalLimit': 1, 'costTolerance': 0})
    result = h.solve_hybrid(*args, time_limit=4)
    assert result['selectedIndices'] == [site]
    assert result['capacity']['annualEquivalentCostTRY'] == 25
    assert result['hybridSummary']['weightedMeanMinutes'] == pytest.approx(2.9)
    assert all(m['metrics']['coveragePercent'] == pytest.approx(100) for m in result['modalResults'].values())


def test_travel_budget_cost_and_modal_material_partition():
    args = case(car=[[0, 8], [8, 0]], transit=[[8, 0], [0, 8]])
    result = h.solve_hybrid(*args, time_limit=4)
    assert result['capacity']['referenceCostTRY'] == pytest.approx(25)
    assert result['capacity']['budgetLimitTRY'] == pytest.approx(27.5)
    assert result['capacity']['annualEquivalentCostTRY'] <= 27.5 + 1e-8
    assert result['capacity']['annualEquivalentCostTRY'] == pytest.approx(sum(x['annualEquivalentCostTRY'] for x in result['capacitySites']))
    # Max per-site mode loads can sum to more than the covered population.
    # Materials must still sum to one annual bill.
    assert sum(x['operatingBreakdown']['materialsTRY'] for x in result['capacitySites']) == pytest.approx(10)


def test_unlocated_population_and_small_district_denominators_retained():
    args = list(case())
    args[4] = [{'id': '0', 'population': 2}, {'id': '1', 'population': 1}]
    args[5] = 3
    args[7].update(coverageTarget=66.66666666666667, districtFloor=60)
    result = h.solve_hybrid(*args, time_limit=1)
    assert result['status'] == 'infeasible'  # first district has only 50% located


def test_conflicts_prevent_two_modes_opening_overlapping_sites():
    args = case(car=[[1, np.inf], [1, np.inf]], transit=[[np.inf, 1], [np.inf, 1]])
    result = h.solve_hybrid(*args, conflicts=[(10, 17)], time_limit=3)
    assert result['status'] == 'infeasible'
    assert result['nativeReportedInfeasible']
    assert result['independentlyProvenInfeasible'] is False


def test_nearest_pruning_per_radius_class_and_mode():
    args = list(case(car=[[1, 2, 3, 4], [4, 3, 2, 1]], transit=[[4, 3, 2, 1], [1, 2, 3, 4]], sites=4))
    args[8][2]['footprintRadiusMeters'] *= 2
    args[8][3]['footprintRadiusMeters'] *= 2
    args[7]['hybridNeighbors'] = 1
    p = build(args)
    assert p.search_scope['restricted']
    assert p.search_scope['retainedEdgesByMode'] == {'car': 4, 'transit': 4}
    for mode in h.MODES:
        oi, sj = p.edges[mode]
        for i in (0, 1):
            radii = {p.sites[j]['footprintRadiusMeters'] for j in sj[oi == i]}
            assert len(radii) == 2


def test_restricted_native_infeasible_is_inconclusive(monkeypatch):
    args = case(car=[[1, 2], [1, 2]], transit=[[1, 2], [1, 2]], scenario={'hybridNeighbors': 1})
    monkeypatch.setattr(h, '_greedy_seed', lambda *a: None)
    monkeypatch.setattr(h, '_native', lambda *a, **kw: SimpleNamespace(x=None, status=2, message='kInfeasible'))
    result = h.solve_hybrid(*args, time_limit=2)
    assert result['status'] == 'inconclusive'
    assert result['nativeReportedInfeasible']
    assert not result['incumbentValidated']


def test_no_incumbent_timeout_does_not_invent_hospital_count(monkeypatch):
    monkeypatch.setattr(h, '_greedy_seed', lambda *a: None)
    monkeypatch.setattr(h, '_native', lambda *a, **kw: SimpleNamespace(x=None, status=1, message='kTimeLimit'))
    result = h.solve_hybrid(*case(), time_limit=2)
    assert result['status'] == 'inconclusive'
    assert result['hospitalCount'] is None


def test_pre_native_timeout_preserves_only_checked_greedy_seed(monkeypatch):
    def timeout(*a, **kw):
        raise TimeoutError('preparation exhausted deadline')
    monkeypatch.setattr(h, '_native', timeout)
    result = h.solve_hybrid(*case(), time_limit=2)
    assert result['status'] == 'feasible'
    assert result['solver']['costStagePerformed'] is False
    assert result['capacity']['costStageGap'] is None
    assert result['capacity']['travelStageGap'] is None


@pytest.mark.parametrize('field,value', [('carWeight', -1), ('carWeight', 101), ('carWeight', True),
    ('transitThreshold', float('nan')), ('threshold', 0), ('hybridNeighbors', 0), ('hybridNeighbors', True)])
def test_bad_scenario_rejected(field, value):
    with pytest.raises(ValueError):
        build(case(scenario={field: value}))


@pytest.mark.parametrize('bad', [float('nan'), -1, -float('inf')])
def test_bad_travel_matrix_rejected(bad):
    with pytest.raises(ValueError):
        build(case(car=[[bad, 1], [1, 1]]))


def test_zero_target_is_valid_empty_plan_with_null_means():
    result = h.solve_hybrid(*case(scenario={'coverageTarget': 0, 'districtFloor': 0}), time_limit=2)
    assert result['status'] == 'feasible'
    assert result['hospitalCount'] == 0
    assert result['hybridSummary']['weightedMeanMinutes'] is None
    assert result['capacity']['annualEquivalentCostTRY'] == 0


def test_any_negative_native_flow_and_closed_site_flow_rejected():
    p = build(case())
    seed = h._greedy_seed(p, h.monotonic() + 2)
    assert seed is not None
    bad = seed.copy(); bad[p.nf] = -1e-14
    v, reason = h._candidate(p, bad, seed)
    assert np.array_equal(v, seed) and reason
    bad = seed.copy()
    opened = p.resources(seed)[0]
    mode = 'car'; oi, sj = p.edges[mode]
    index = np.flatnonzero(~opened[sj])[0]
    bad[p.offsets[mode] + index] = 1e-12
    v, reason = h._candidate(p, bad, seed)
    assert np.array_equal(v, seed) and reason


def test_contradictory_cost_and_travel_bounds_are_not_clamped():
    with pytest.raises(RuntimeError):
        h._bound_gap(25, 26, .01)
    with pytest.raises(RuntimeError):
        h._bound_gap(2., 2.1, 1e-7)


def test_modal_quotas_and_cost_are_invariant_under_weights():
    a = build(case(scenario={'carWeight': 0}))
    b = build(case(scenario={'carWeight': 100}))
    assert np.array_equal(a.c, b.c)
    assert np.array_equal(a.model[4].toarray(), b.model[4].toarray())
    assert all(np.array_equal(x, y) for x, y in zip(a.model[5:], b.model[5:]))
    assert not np.array_equal(h._travel_objective(a), h._travel_objective(b))


def test_weighted_means_use_resident_amounts_not_origin_counts():
    args = list(case(car=[[1, np.inf], [np.inf, 9]], transit=[[5, np.inf], [np.inf, 1]], pop=(1, 3)))
    args[6]['templates'].append({'id': 'four', 'beds': 4, 'grossAreaM2': 4})
    result = h.solve_hybrid(*args, time_limit=3)
    assert result['status'] == 'feasible'
    assert result['modalResults']['car']['metrics']['meanMinutes'] == pytest.approx(7)
    assert result['modalResults']['transit']['metrics']['meanMinutes'] == pytest.approx(2)
    assert result['hybridSummary']['weightedMeanMinutes'] == pytest.approx(5.5)


def test_modes_may_serve_different_origins_but_materials_are_once():
    args = case(car=[[1], [np.inf]], transit=[[np.inf], [1]], sites=1,
        scenario={'coverageTarget': 50, 'districtFloor': 0})
    result = h.solve_hybrid(*args, time_limit=3)
    assert result['status'] == 'feasible'
    assert result['capacity']['annualMaterialCostTRY'] == 5
    assert result['capacity']['totalBeds'] == result['capacity']['totalDoctors'] == 1
    assert result['modalResults']['car']['assignments'][0]['servedFraction'] == 1
    assert result['modalResults']['transit']['assignments'][0]['servedFraction'] == 0
    assert result['hybridSummary']['sameIndividualsAcrossModesConstrained'] is False


def test_independent_bed_and_physician_resources_do_not_force_fixed_ratio():
    result = h.solve_hybrid(*case(scenario={'contactsPerDoctor': 2, 'costTolerance': 0}), time_limit=3)
    assert result['status'] == 'feasible'
    assert result['capacity']['totalBeds'] == 2
    assert result['capacity']['totalDoctors'] == 1
    assert result['capacity']['annualEquivalentCostTRY'] == pytest.approx(21)


def test_conflicts_generator_is_not_consumed_before_model_construction():
    args = case(car=[[1, np.inf], [1, np.inf]], transit=[[np.inf, 1], [np.inf, 1]])
    p = build(args, conflicts=((10, 17) for _ in range(1)))
    assert p.conflicts == ((10, 17),)
    assert p.dimensions['conflicts'] == 1


def test_native_cold_deadline_checks_immediately_before_run(monkeypatch):
    import highspy
    p = build(case())
    monkeypatch.setattr(highspy.Highs, 'run', lambda *a: pytest.fail('Expired native deadline'))
    with pytest.raises(TimeoutError):
        h._native(p.model, 1, deadline=h.monotonic() - 1)


def test_two_profile_copy_retains_frozen_builder_resource_and_modal_rows():
    from backend.joint_model import build_joint_problem
    args = case(car=[[1, np.inf], [1, 1]], transit=[[2, 1], [np.inf, 1]])
    p = build(args)
    times = {'a': p.times['car'], 'b': p.times['transit'], 'c': p.times['car'], 'd': p.times['transit']}
    q = build_joint_problem(times, p.pop, p.dd, p.districts, p.total, p.sites, p.h, p.s)
    assert p.nf == q.nf and np.array_equal(p.c[:p.nf], q.c[:q.nf])
    assert p.material == q.material
    # The shared resource rows and first two complete modal row blocks/columns
    # are bit-for-bit equal to the independently reviewed four-profile model.
    rows = p.model[4].shape[0]
    assert np.array_equal(p.model[4].toarray(), q.model[4][:rows, :len(p.c)].toarray())
    assert np.array_equal(p.model[5], q.model[5][:rows])
    assert np.array_equal(p.model[6], q.model[6][:rows])
    assert all(np.array_equal(a, b[:len(a)]) for a, b in zip(p.model[1:4], q.model[1:4]))
