import numpy as np
import pytest
from backend.robustness import evaluate_fixed_plan
from scripts.audit_robustness import assert_plan_binding, aggregate_profiles


def evaluate(times, populations, sites, **changes):
    scenario = {'threshold': 45, 'coverageTarget': 95, 'districtFloor': 0,
                'demandMultiplier': 1, 'contactsPerDoctor': 100,
                'bedOccupancy': 100}
    scenario.update(changes)
    districts = [{'id': str(i), 'name': str(i), 'population': pop} for i, pop in enumerate(populations)]
    return evaluate_fixed_plan(np.asarray(times, dtype=float), populations,
        np.array([d['id'] for d in districts]), districts, sum(populations), sites,
        {'rates': {'contactsPerResident': 1, 'bedDaysPerResident': 1}}, scenario)


def test_fixed_plan_checks_doctor_and_bed_resources_separately():
    doctor_limited = evaluate([[1]], [1000], [{'beds': 10, 'doctors': 2}])
    bed_limited = evaluate([[1]], [1000], [{'beds': 1, 'doctors': 10}])
    assert doctor_limited['maximumCoveredPopulation'] == pytest.approx(200)
    assert bed_limited['maximumCoveredPopulation'] == pytest.approx(365)
    assert doctor_limited['status'] == bed_limited['status'] == 'province_target_not_met'


def test_same_plan_can_fail_another_time_profile_without_moving_sites():
    sites = [{'beds': 10, 'doctors': 10}, {'beds': 10, 'doctors': 10}]
    morning = evaluate([[10, 50], [50, 10]], [100, 100], sites, districtFloor=80)
    weekend = evaluate([[50, 50], [50, 10]], [100, 100], sites, districtFloor=80)
    assert morning['targetsMet'] is True
    assert weekend['status'] == 'district_targets_infeasible'
    assert weekend['maximumCoveragePercent'] is None
    assert weekend['withoutDistrictTargets']['maximumCoveragePercent'] == pytest.approx(50)


def test_all_selected_edges_are_used_for_reallocation():
    # Closest-only assignment overloads site 0; both sites are fixed and usable.
    result = evaluate([[1, 40], [1, 40]], [100, 100],
                      [{'beds': 10, 'doctors': 1}, {'beds': 10, 'doctors': 1}], districtFloor=100)
    assert result['targetsMet'] is True
    assert result['maximumCoveredPopulation'] == pytest.approx(200)
    assert result['allocationEdges'] == 4


def test_joint_district_resource_shortfall_is_not_just_geographic():
    result = evaluate([[1], [1]], [100, 100], [{'beds': 10, 'doctors': 1}], districtFloor=80)
    assert all(d['maximumPercent'] == 100 for d in result['geographicDistrictCeilings'])
    assert result['status'] == 'district_targets_infeasible'
    assert result['withoutDistrictTargets']['maximumCoveragePercent'] == pytest.approx(50)


def test_demand_multiplier_and_population_denominator_are_preserved():
    result = evaluate([[1]], [100], [{'beds': 10, 'doctors': 1}], demandMultiplier=2)
    assert result['maximumCoveragePercent'] == pytest.approx(50)
    scenario = {'threshold': 45, 'coverageTarget': 95, 'districtFloor': 0,
                'demandMultiplier': 1, 'contactsPerDoctor': 1000, 'bedOccupancy': 100}
    unlocated = evaluate_fixed_plan(np.array([[1.]]), np.array([80.]), np.array(['a']),
        [{'id': 'a', 'population': 100}], 100, [{'beds': 10, 'doctors': 10}],
        {'rates': {'contactsPerResident': 1, 'bedDaysPerResident': 1}}, scenario)
    assert unlocated['maximumCoveragePercent'] == pytest.approx(80)


def test_empty_reachable_edges_are_a_proven_failure_not_solver_error():
    result = evaluate([[np.inf]], [100], [{'beds': 10, 'doctors': 1}], districtFloor=80)
    assert result['status'] == 'district_targets_infeasible'
    result = evaluate([[np.inf]], [100], [{'beds': 10, 'doctors': 1}], districtFloor=0)
    assert result['status'] == 'province_target_not_met'
    assert result['maximumCoveredPopulation'] == 0


def test_negative_times_and_non_integer_staff_are_rejected():
    with pytest.raises(ValueError):
        evaluate([[-1]], [100], [{'beds': 10, 'doctors': 1}])
    with pytest.raises(ValueError):
        evaluate([[1]], [100], [{'beds': 10, 'doctors': 1.5}])


def test_saved_plan_package_and_order_are_not_silently_rebound():
    site = {'candidateIndex': 0, 'id': 'site', 'lon': 32, 'lat': 40}
    data = {'metadata': {'transitPackageId': 'new'}, 'candidates': [site],
            'demands': [{'id': 'd0'}, {'id': 'd1'}]}
    plan = {'metadata': {'transitPackageId': 'new'}, 'transitEvidence': {'packageId': 'new'},
            'status': 'feasible', 'scenario': {'mode': 'transit'}, 'selected': [site],
            'selectedIndices': [0], 'hospitalCount': 1,
            'assignments': [{'demandId': 'd0'}, {'demandId': 'd1'}]}
    assert_plan_binding(plan, data, 'new')
    plan['transitEvidence']['packageId'] = 'old'
    with pytest.raises(ValueError, match='another package'):
        assert_plan_binding(plan, data, 'new')
    plan['transitEvidence']['packageId'] = 'new'
    plan['assignments'].reverse()
    with pytest.raises(ValueError, match='row identities'):
        assert_plan_binding(plan, data, 'new')


def test_inconclusive_profile_is_not_aggregated_as_proven_failure():
    assert aggregate_profiles([{'targetsMet': True}, {'targetsMet': None}]) == (None, 'inconclusive')
    assert aggregate_profiles([{'targetsMet': True}, {'targetsMet': False}]) == (False, 'some_targets_failed')
    assert aggregate_profiles([{'targetsMet': None}, {'targetsMet': False}]) == (False, 'some_targets_failed')
    assert aggregate_profiles([{'targetsMet': True}, {'targetsMet': True}]) == (True, 'all_targets_met')
