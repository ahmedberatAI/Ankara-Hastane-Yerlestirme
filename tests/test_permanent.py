"""Permanent five-demand formulation, seed, accounting and failure contracts."""
from copy import deepcopy
from itertools import product
from types import SimpleNamespace
import math
import numpy as np
import pytest

import backend.permanent as p


def case(matrices=None, *, pop=(1, 1), sites=2):
    health = {'version': 'tiny-permanent',
        'rates': {'contactsPerResident': 2140, 'bedDaysPerResident': 292},
        'templates': [{'id': 'one', 'beds': 1, 'grossAreaM2': 1},
                      {'id': 'two', 'beds': 2, 'grossAreaM2': 2}],
        'design': {'areaPerDoctorM2': 1, 'maxFloors': 1, 'minimumDoctorsPerSite': 1},
        'economics': {'realDiscountRate': 0, 'horizonYears': 1, 'buildingUnitCostTRY': 1,
            'annualFixedSiteCostTRY': 1, 'annualDoctorCostTRY': 3,
            'annualBedSupportCostTRY': 2, 'costPerContactTRY': 5 / 2140}}
    times = {name: np.ones((len(pop), sites)) for name in p.PROFILES}
    if matrices:
        for name, value in matrices.items(): times[name] = np.asarray(value, float)
    candidates = [{'candidateIndex': 10 + 7*j, 'id': str(j),
                   'footprintRadiusMeters': math.sqrt(12 / math.pi)} for j in range(sites)]
    districts = [{'id': str(i), 'population': value} for i, value in enumerate(pop)]
    return [times, np.asarray(pop, float), np.asarray([str(i) for i in range(len(pop))]),
            districts, sum(pop), health, {}, candidates]


def build(args, **kw):
    return p.build_permanent_problem(*args, **kw)


def seed(problem):
    result = p._greedy_seed(problem, p.monotonic() + 3)
    assert result is not None
    return result


def native_result(x, status=1, bound=np.nan):
    return SimpleNamespace(x=x, status=status, message='kTimeLimit' if status == 1 else 'kOptimal',
        mip_dual_bound=bound, mip_gap=np.nan, isTimeLimit=status == 1,
        warm={'solverAcceptedFeasibleStart': x is not None})


def no_mip(monkeypatch):
    monkeypatch.setattr(p, '_native', lambda model, seconds, start=None, **kw: native_result(start))


def test_builder_is_pure_and_keeps_five_complete_demands(monkeypatch):
    import highspy
    monkeypatch.setattr(highspy.Highs, 'run', lambda *a: pytest.fail('Builder invoked native solver'))
    model = build(case())
    assert tuple(model.times) == p.PROFILES
    assert model.dimensions['flowVariables'] == 20
    assert model.target == pytest.approx(1.9)
    assert model.material == pytest.approx(9.5)
    assert model.modal_weights == {'car': .7, **{name: .075 for name in p.PROFILES[1:]}}


@pytest.mark.parametrize('count', [2, 4])
def test_generic_builder_bit_matches_frozen_rows_bounds_and_indices(count):
    from backend.hybrid import _build_two_profile_problem
    from backend.joint_model import build_joint_problem
    args = case({'car': [[1, np.inf], [1, 2]], 'weekday-0800': [[2, 1], [np.inf, 2]]})
    times = dict(list(args[0].items())[:count])
    scenario = dict(p.FIXED_POLICY, threshold=60)
    model = p._build_profiles(times, *args[1:5], args[7], args[5], scenario, [(10, 17)])
    old = (_build_two_profile_problem if count == 2 else build_joint_problem)(
        times, *args[1:5], args[7], args[5], scenario, [(10, 17)])
    for a, b in zip(model.model, old.model):
        if hasattr(a, 'indptr'):
            assert np.array_equal(a.indptr, b.indptr)
            assert np.array_equal(a.indices, b.indices)
            assert np.array_equal(a.data, b.data)
        else: assert np.array_equal(a, b)
    assert model.offsets == old.offsets and model.material == old.material
    assert np.array_equal(model.xsite, old.xsite) and np.array_equal(model.xtype, old.xtype)


@pytest.mark.parametrize('name', p.PROFILES)
def test_any_one_profile_failure_cannot_be_hidden_by_weights(name):
    result = p.solve_permanent(*case({name: [[np.inf, np.inf], [np.inf, np.inf]]}), time_limit=1)
    assert result['status'] == 'inconclusive'
    assert result['representedSupportNecessaryFailure']
    assert not result['independentlyProvenRealCityInfeasible']
    assert name in result['reason']


@pytest.mark.parametrize('field,value', [('threshold', 45), ('transitThreshold', 90),
    ('coverageTarget', 90), ('districtFloor', 75), ('bedOccupancy', 85),
    ('contactsPerDoctor', 2200), ('carWeight', 75), ('costTolerance', 20),
    ('demandMultiplier', 2), ('trafficFactor', 1.2), ('hospitalLimit', 91),
    ('carWeight', True), ('bedOccupancy', float('nan'))])
def test_public_policy_cannot_silently_change(field, value):
    args = case(); args[6][field] = value
    with pytest.raises(ValueError): build(args)


@pytest.mark.parametrize('kind', ['missing', 'extra', 'reordered'])
def test_profile_identity_order_is_exact(kind):
    args = case()
    if kind == 'missing': args[0].pop('sunday-1000')
    elif kind == 'extra': args[0]['monday'] = np.ones((2, 2))
    else: args[0] = dict(reversed(list(args[0].items())))
    with pytest.raises(ValueError): build(args)


def test_policy_profile_ids_cannot_disagree_with_actual_matrices():
    args = case(); args[6]['profileIds'] = list(p.PROFILES[:-1])
    with pytest.raises(ValueError, match='profile identities'): build(args)
    args[6]['profileIds'] = list(p.PROFILES)
    args[6]['rationale'] = 'These are policy choices, not universal clinical standards.'
    assert build(args).policy['rationale'] == args[6]['rationale']


@pytest.mark.parametrize('bad', [np.nan, -1., -np.inf])
def test_invalid_matrix_rejected(bad):
    args = case(); args[0]['sunday-1000'][0, 0] = bad
    with pytest.raises(ValueError): build(args)


def test_thresholds_are_separate_and_all_known_pt_edges_retained():
    args = case({'car': [[30, 31], [29, 30]],
                 'weekday-0800': [[60, 61], [59, 60]]})
    model = build(args, car_neighbors=1)
    assert np.isinf(model.times['car'][0, 1])
    assert np.isinf(model.times['weekday-0800'][0, 1])
    assert len(model.edges['car'][0]) == 2
    assert len(model.edges['weekday-0800'][0]) == 3
    assert len(model.edges['sunday-1000'][0]) == 4
    assert model.search_scope['allKnownTransitEdgesRetained']
    assert model.search_scope['restricted']


def test_capacity_is_profile_maximum_and_material_bill_once(monkeypatch):
    no_mip(monkeypatch)
    result = p.solve_permanent(*case(), time_limit=2)
    assert result['status'] == 'feasible'
    assert result['capacity']['totalBeds'] == 2
    assert result['capacity']['totalDoctors'] == 2
    assert result['capacity']['annualMaterialCostTRY'] == pytest.approx(9.5)
    assert result['capacity']['annualEquivalentCostTRY'] == pytest.approx(24.5)
    assert sum(site['operatingBreakdown']['materialsTRY'] for site in result['capacitySites']) == pytest.approx(9.5)
    assert all(x['metrics']['coveragePercent'] == pytest.approx(95) for x in result['profiles'].values())
    assert result['permanentSummary']['profileCount'] == 5
    assert result['capacity']['annualEquivalentCostTRY'] == pytest.approx(sum(
        site['annualEquivalentCostTRY'] for site in result['capacitySites']))


def test_complete_same_resources_allow_different_profile_allocations(monkeypatch):
    no_mip(monkeypatch)
    matrices = {name: ([[1, np.inf], [np.inf, 1]] if i % 2 else [[np.inf, 1], [1, np.inf]])
                for i, name in enumerate(p.PROFILES)}
    result = p.solve_permanent(*case(matrices), time_limit=2)
    assert result['status'] == 'feasible'
    assert result['hospitalCount'] == 2
    assert result['capacity']['totalDoctors'] == result['capacity']['totalBeds'] == 2
    assert result['profiles']['car']['assignments'][0]['candidateIndex'] != result['profiles']['weekday-0800']['assignments'][0]['candidateIndex']
    assert not result['permanentSummary']['sameIndividualsAcrossProfilesConstrained']


def test_district_missing_population_stays_in_denominator():
    args = case()
    args[3][0]['population'] = 2; args[4] = 3
    result = p.solve_permanent(*args, time_limit=1)
    assert result['representedSupportNecessaryFailure']


def test_weighted_mean_and_critical_transit_are_whole_profiles(monkeypatch):
    no_mip(monkeypatch)
    levels = dict(zip(p.PROFILES, [2, 4, 6, 8, 10]))
    args = case({name: np.full((2, 2), t) for name, t in levels.items()})
    result = p.solve_permanent(*args, time_limit=2)
    assert result['permanentSummary']['weightedMeanMinutes'] == pytest.approx(.7*2 + .075*(4+6+8+10))
    assert result['permanentSummary']['meanTransitMinutes'] == pytest.approx(7)
    assert result['criticalTransitProfile'] == 'sunday-1000'
    assert result['modalResults']['transit'] == result['profiles']['sunday-1000']
    assert result['metrics'] == result['profiles']['car']['metrics']
    assert result['assignments'] == result['profiles']['car']['assignments']


def test_tied_critical_profile_has_stable_id_tiebreak(monkeypatch):
    no_mip(monkeypatch)
    result = p.solve_permanent(*case(), time_limit=2)
    assert result['criticalTransitProfile'] == min(p.PROFILES[1:])


def test_fixed_resource_lp_improves_weighted_time_without_changing_bill():
    args = case({name: [[1, 9], [9, 1]] for name in p.PROFILES})
    model = build(args); v = np.zeros_like(model.c)
    # Deliberately valid slow source: one person-capacity site for each origin.
    for j in range(2):
        x = next(x for x in model.site_xs[j] if model.beds[model.xtype[x]] == 1)
        v[x] = 1; v[model.nx+j] = 1
    for name, (oi, sj) in model.edges.items():
        v[model.offsets[name] + np.flatnonzero(oi != sj)] = .00095
    model.validate(v)
    final, record = p._fixed_travel(model, v, p.monotonic()+5)
    assert record['allProfilesAccepted']
    assert np.array_equal(final[:model.nf], v[:model.nf])
    assert model.cost(final) == model.cost(v)
    assert p._travel_objective(model) @ final == pytest.approx(1.)
    assert all(r['certificate']['certifiedForRepresentedFixedResourceLP'] for r in record['profiles'])
    assert not record['wholeJointTravelOptimumProven']


def test_fixed_lp_expired_deadline_preserves_all_five_flows():
    model = build(case()); v = seed(model)
    final, record = p._fixed_travel(model, v, p.monotonic()-1)
    assert np.array_equal(final, v)
    assert not record['allProfilesAccepted']
    assert all(r['sourceFallback'] for r in record['profiles'])


def test_incomplete_two_profile_source_is_not_a_five_profile_warm_start():
    model = build(case()); plan = model.serialize(seed(model)); plan['profiles'] = plan['profiles'][:2]
    with pytest.raises(ValueError, match='profile identities'):
        model.read_plan(plan)


def test_no_incumbent_remains_unknown_not_zero_hospitals(monkeypatch):
    monkeypatch.setattr(p, '_greedy_seed', lambda *a: None)
    monkeypatch.setattr(p, '_native', lambda *a, **kw: native_result(None))
    result = p.solve_permanent(*case(), time_limit=1)
    assert result['status'] == 'inconclusive' and result['hospitalCount'] is None
    assert not result['incumbentValidated']


def test_native_infeasible_is_reported_separately_from_real_city_proof(monkeypatch):
    monkeypatch.setattr(p, '_greedy_seed', lambda *a: None)
    monkeypatch.setattr(p, '_native', lambda *a, **kw: native_result(None, 2))
    result = p.solve_permanent(*case(), time_limit=1)
    assert result['status'] == 'inconclusive' and result['nativeReportedInfeasible']
    assert not result['independentlyProvenRealCityInfeasible']


def test_native_infeasible_cannot_contradict_checked_seed_silently(monkeypatch):
    monkeypatch.setattr(p, '_native', lambda *a, **kw: native_result(None, 2))
    with pytest.raises(RuntimeError, match='contradicts'):
        p.solve_permanent(*case(), time_limit=1)


def test_native_timeout_keeps_complete_validated_source_and_null_bounds(monkeypatch):
    def timeout(*a, **kw): raise TimeoutError('before native')
    monkeypatch.setattr(p, '_native', timeout)
    result = p.solve_permanent(*case(), time_limit=2)
    assert result['status'] == 'feasible'
    assert result['capacity']['costStageGap'] is None
    assert result['capacity']['travelStageGap'] is None
    assert not result['solver']['costStagePerformed']
    assert len(result['profiles']) == 5


def test_negative_and_closed_site_flows_cannot_become_a_valid_fallback():
    model = build(case()); v = seed(model)
    bad = v.copy(); bad[model.nf] = -1e-14
    final, reason = p._candidate(model, bad, v)
    assert reason and np.array_equal(final, v)
    closed = np.flatnonzero(~model.resources(v)[0])[0]
    name = 'sunday-1000'; edge = np.flatnonzero(model.edges[name][1] == closed)[0]
    bad = v.copy(); bad[model.offsets[name]+edge] = 1e-12
    final, reason = p._candidate(model, bad, v)
    assert reason and np.array_equal(final, v)


def test_cost_first_then_weighted_native_respects_original_budget_row():
    args = case({name: [[1, 9], [1, 9]] if name == 'car' else [[9, 1], [9, 1]] for name in p.PROFILES})
    result = p.solve_permanent(*args, time_limit=4)
    assert result['status'] == 'feasible'
    assert result['capacity']['referenceCostTRY'] == pytest.approx(24.5)
    assert result['capacity']['budgetLimitTRY'] == pytest.approx(26.95)
    assert result['capacity']['annualEquivalentCostTRY'] <= 26.95 + 1e-8
    assert result['selectedIndices'] == [10]
    assert result['permanentSummary']['weightedMeanMinutes'] == pytest.approx(3.4)
    assert result['solver']['travelWarmStartAccepted']


def test_conflicting_plots_cannot_be_opened_by_different_profiles():
    args = case({name: [[1, np.inf], [1, np.inf]] if name == 'car' else [[np.inf, 1], [np.inf, 1]] for name in p.PROFILES})
    result = p.solve_permanent(*args, conflicts=[(10, 17)], time_limit=2)
    assert result['status'] == 'inconclusive' and result['nativeReportedInfeasible']


def test_bound_contradiction_is_not_clamped_to_zero():
    with pytest.raises(RuntimeError): p._bound_gap(10, 11, .01)


def test_time_limit_cap_rejects_unbounded_and_boolean_values():
    for seconds in (181, float('inf'), True, 0):
        with pytest.raises(ValueError): p.solve_permanent(*case(), time_limit=seconds)


def test_exact_five_profile_json_vector_roundtrip():
    model = build(case()); v = seed(model); plan = model.serialize(v)
    reconstructed, _ = model.read_plan(plan)
    assert np.max(np.abs(v-reconstructed)) <= 1e-12
    assert [item['profile'] for item in plan['profiles']] == list(p.PROFILES)


def test_separate_bed_and_physician_design_not_a_fixed_ratio(monkeypatch):
    no_mip(monkeypatch)
    args = case(); args[5]['rates']['contactsPerResident'] = 1070
    result = p.solve_permanent(*args, time_limit=2)
    assert result['capacity']['totalBeds'] == 2
    assert result['capacity']['totalDoctors'] == 1
    assert result['capacity']['annualMaterialCostTRY'] == pytest.approx(4.75)


def test_original_area_and_small_district_percentage_tolerances_stay_strict():
    args = case(pop=(1, 10), sites=1)
    args[5]['templates'] = [{'id': 'large', 'beds': 11, 'grossAreaM2': 11}]
    args[7][0]['footprintRadiusMeters'] = math.sqrt(25 / math.pi)
    model = build(args); v = np.zeros_like(model.c)
    v[0] = 1; v[model.nx] = 11
    for name in p.PROFILES:
        v[model.offsets[name]:model.offsets[name]+2] = [.00079995, .00965005]
    with pytest.raises(ValueError, match='district'): model.validate(v)
    for name in p.PROFILES:
        v[model.offsets[name]:model.offsets[name]+2] = [.0008, .00965]
    model.validate(v)
    model.available[0] = 21.99
    with pytest.raises(ValueError, match='area'): model.validate(v)


def test_any_fixed_resource_mutation_in_reused_helper_is_rejected(monkeypatch):
    model = build(case()); v = seed(model)
    def bad(problem, current, name, *args, **kw):
        changed = current.copy(); changed[problem.nx:problem.nf] += 1
        return {'accepted': True, 'sourceFallback': False}, changed
    monkeypatch.setattr(p, 'one_profile', bad)
    with pytest.raises((ValueError, RuntimeError)): p._fixed_travel(model, v, p.monotonic()+1)


def test_new_cost_and_travel_vectors_are_validated_before_fallback(monkeypatch):
    calls = []
    def broken(model, seconds, start=None, **kw):
        calls.append(model)
        bad = start.copy(); bad[-1] = -1e-12
        return native_result(bad)
    monkeypatch.setattr(p, '_native', broken)
    result = p.solve_permanent(*case(), time_limit=2)
    assert len(calls) == 2
    assert result['status'] == 'feasible'
    assert len(result['capacity']['numericalFallback']) == 2
    assert all(x['validatedSourcePreserved'] for x in result['capacity']['numericalFallback'])
    assert not result['provenOptimal'] and not result['secondaryOptimal']
