"""The travel objective must not preserve gratuitous beds, staff or sites."""
import json
from pathlib import Path
import numpy as np
import pytest
import backend.capacity as capacity


def test_travel_optimal_but_wasteful_incumbent_is_cleaned_without_changing_flow(monkeypatch):
    planning = json.loads((Path(__file__).resolve().parents[1] /
                           'data/processed/health-planning.json').read_text(encoding='utf-8'))
    templates = planning['templates']
    k, h = len(templates), 3
    nx, nd = h * k, h * k + h
    bed_type = {t['beds']: i for i, t in enumerate(templates)}
    needed_doctors = int(np.ceil(75000 * planning['rates']['contactsPerResident'] / 2140))
    captured = []
    optimize = capacity.optimize

    def inject(objective, integrality, bounds, A, lower, upper, time_limit, seed=None):
        result = optimize(objective, integrality, bounds, A, lower, upper, time_limit, seed)
        captured.append({'objective': objective.copy(), 'result': result,
                         'original': None if result.x is None else result.x.copy()})
        if len(captured) == 4:
            # Both demand origins receive 1-minute service. The middle hospital
            # has zero flow, the left has excess beds/staff. This is a valid
            # SECONDARY optimum because cost is only a budget constraint.
            v = np.zeros_like(result.x)
            v[bed_type[600]] = 1
            v[k + bed_type[50]] = 1
            v[2 * k + bed_type[300]] = 1
            v[nx:nd] = [needed_doctors + 15, 12, needed_doctors]
            # With no nearest-neighbor pruning, both rows retain 0,1,2 order.
            v[nd:] = [75, 0, 0, 0, 0, 75]
            assert np.all(A @ v >= np.asarray(lower) - 1e-6)
            assert np.all(A @ v <= np.asarray(upper) + 1e-6)
            assert np.all(v <= bounds.ub) and np.all(v >= bounds.lb)
            assert objective @ v == pytest.approx(objective @ result.x)
            result.x = v
            captured[-1]['injected'] = v.copy()
        return result

    monkeypatch.setattr(capacity, 'optimize', inject)
    result = capacity.solve_capacity(np.array([[1., 10., 30.], [30., 10., 1.]]),
        np.array([75000, 75000]), np.array(['A', 'A']),
        [{'id': 'A', 'name': 'A', 'population': 150000}], 150000, planning,
        coverage_target=1, district_floor=1, cost_tolerance=.3, neighbors=None, time_limit=3)
    c = result['capacity']
    assert result['hospitalCount'] == 2
    assert set(result['selectedIndices']) == {0, 2}
    assert c['totalBeds'] == 600
    assert c['totalDoctors'] == 2 * needed_doctors
    assert result['metrics']['coveredPopulation'] == pytest.approx(150000)
    assert result['metrics']['meanMinutes'] == pytest.approx(1)
    assert all(a['allocations'][0]['population'] == pytest.approx(75000) for a in result['assignments'])
    cleanup = c['resourceCleanup']
    assert cleanup['removedHospitalCount'] == 1
    assert cleanup['removedBeds'] == 350
    assert cleanup['removedDoctors'] == 27
    assert cleanup['allocationsPreserved'] and cleanup['travelPreserved']
    assert cleanup['annualCostReductionTRY'] > 0
    before_cost = captured[1]['objective'] @ captured[3]['injected'] * 1e9
    assert c['annualEquivalentCostTRY'] + cleanup['annualCostReductionTRY'] == pytest.approx(before_cost)
    assert c['annualEquivalentCostTRY'] <= c['budgetLimitTRY']
    for site in result['capacitySites']:
        assert site['annualContacts'] <= site['contactCapacity'] + 1e-6
        assert site['annualBedDays'] <= site['bedDayCapacity'] + 1e-6
    original = captured[1]['original']
    original_x = np.rint(original[:nx]).reshape(h, k)
    reference = c['referenceStage']
    assert reference['hospitalCount'] == int(original_x.sum())
    assert reference['totalBeds'] == int((original_x * [t['beds'] for t in templates]).sum())
    assert reference['totalDoctors'] == int(np.rint(original[nx:nd]).sum())
    assert reference['annualEquivalentCostTRY'] == pytest.approx(c['referenceCostTRY'])
    assert reference['boundScope'] == 'all_candidate_allocation_edges'
    assert c['travelStageGap'] == pytest.approx(0)
    assert c['finalPlanCostGap'] == pytest.approx(
        (c['annualEquivalentCostTRY'] - result['lowerBound']) / c['annualEquivalentCostTRY'])
    # Cleaning the selected result cannot silently mutate the original stage.
    assert np.array_equal(captured[1]['result'].x, captured[1]['original'])


def tiny_planning():
    return {
        'version': 'tiny', 'rates': {'contactsPerResident': 1., 'visitsPerResident': .9,
            'admissionsPerResident': .1, 'bedDaysPerResident': .1},
        'templates': [{'id': 's', 'label': 'small', 'beds': 10, 'grossAreaM2': 100}],
        'design': {'areaPerDoctorM2': 10, 'minimumDoctorsPerSite': 1, 'maxFloors': 1},
        'economics': {'realDiscountRate': 0, 'horizonYears': 10, 'buildingUnitCostTRY': 10000,
            'annualFixedSiteCostTRY': 100000, 'annualBedSupportCostTRY': 100,
            'annualDoctorCostTRY': 1000, 'costPerContactTRY': 1, 'priceBase': 'test'},
    }


def test_reference_metadata_keeps_restricted_scope_and_stage_gap():
    result = capacity.solve_capacity(np.array([[1., 2.]]), np.array([1000]), np.array(['A']),
        [{'id': 'A', 'name': 'A', 'population': 1000}], 1000, tiny_planning(),
        coverage_target=1, district_floor=1, contacts_per_doctor=1000, neighbors=1, time_limit=2)
    c = result['capacity']
    assert c['referenceStage']['boundScope'] == 'restricted_allocation_edges'
    assert c['optimalityScope'] == 'restricted_allocation_edges'
    assert result['gap'] == c['costStageGap'] == c['referenceStage']['gap']
    assert c['referenceStage']['coveredPopulation'] == pytest.approx(1000)
    assert c['referenceStage']['coveragePercent'] == pytest.approx(100)
    assert c['resourceCleanup']['annualCostReductionTRY'] >= -1e-6


@pytest.mark.parametrize('tiny_flow', [1e-12, 1e-9])
def test_tiny_closed_site_flow_returns_an_earlier_supported_plan_explicitly(monkeypatch,tiny_flow):
    optimize = capacity.optimize
    calls = []

    def inject(*args, **kwargs):
        result = optimize(*args, **kwargs)
        calls.append(result)
        if len(calls) == 4:
            result.x = np.array([1., 0., 1., 0., 1. - tiny_flow, tiny_flow])
        return result

    monkeypatch.setattr(capacity, 'optimize', inject)
    result = capacity.solve_capacity(np.array([[1., 2.]]), np.array([1000]), np.array(['A']),
        [{'id': 'A', 'name': 'A', 'population': 1000}], 1000, tiny_planning(),
        coverage_target=1, district_floor=1, contacts_per_doctor=1000, neighbors=None, time_limit=2)
    cleanup = result['capacity']['resourceCleanup']
    fallback = result['capacity']['numericalFallback']
    assert fallback['reason'] == 'positive_flow_at_closed_site_within_solver_tolerance'
    assert fallback['rejectedClosedSiteFlowResidents'] == pytest.approx(tiny_flow*1000)
    assert fallback['allocationAbsoluteDifferenceResidents'] > 0
    assert fallback['selectedIncumbentValidated'] is True
    assert cleanup['toleratedClosedSiteFlowResidents'] == 0
    assert cleanup['allocationsPreserved'] is True
    assert np.array_equal(calls[3].x, [1., 0., 1., 0., 1. - tiny_flow, tiny_flow])
    assert all(part['candidateIndex'] in result['selectedIndices']
               for assignment in result['assignments'] for part in assignment['allocations'])


def test_no_supported_incumbent_is_inconclusive_not_a_feasible_plan(monkeypatch):
    optimize = capacity.optimize
    calls = 0

    def inject(*args, **kwargs):
        nonlocal calls
        result = optimize(*args, **kwargs)
        calls += 1
        if calls >= 2:
            result.x = np.array([1., 0., 1., 0., 1. - 1e-9, 1e-9])
        return result

    monkeypatch.setattr(capacity, 'optimize', inject)
    result = capacity.solve_capacity(np.array([[1., 2.]]), np.array([1000]), np.array(['A']),
        [{'id': 'A', 'name': 'A', 'population': 1000}], 1000, tiny_planning(),
        coverage_target=1, district_floor=1, contacts_per_doctor=1000, neighbors=None, time_limit=2)
    assert result['status'] == 'inconclusive'
    assert result['numericalDiagnostics']['closedSiteFlowResidents'] == pytest.approx(1e-6)
    assert 'assignments' not in result


def test_materially_inconsistent_cost_dual_bound_is_not_clipped_to_zero_gap(monkeypatch):
    optimize = capacity.optimize
    calls = 0

    def inject(*args, **kwargs):
        nonlocal calls
        result = optimize(*args, **kwargs)
        calls += 1
        if calls == 2:
            result.mip_dual_bound = float(args[0] @ result.x) + .0001
        return result

    monkeypatch.setattr(capacity, 'optimize', inject)
    with pytest.raises(RuntimeError, match='Cost lower bound exceeds'):
        capacity.solve_capacity(np.array([[1., 2.]]), np.array([1000]), np.array(['A']),
            [{'id': 'A', 'name': 'A', 'population': 1000}], 1000, tiny_planning(),
            coverage_target=1, district_floor=1, contacts_per_doctor=1000, neighbors=None, time_limit=2)
