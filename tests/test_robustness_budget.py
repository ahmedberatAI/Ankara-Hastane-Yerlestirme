import numpy as np
import pytest

from backend.robustness import evaluate_fixed_plan, fixed_plan_costs


def inputs():
    sites = [{'beds': 10, 'doctors': 10, 'grossAreaM2': 100}]
    planning = {'rates': {'contactsPerResident': 2, 'bedDaysPerResident': 1},
        'economics': {'realDiscountRate': 0, 'horizonYears': 10,
            'buildingUnitCostTRY': 100, 'annualFixedSiteCostTRY': 50,
            'annualDoctorCostTRY': 10, 'annualBedSupportCostTRY': 5,
            'costPerContactTRY': 1.5}}
    scenario = {'threshold': 45, 'coverageTarget': 95, 'districtFloor': 0,
        'demandMultiplier': 1, 'contactsPerDoctor': 100,
        'bedOccupancy': 100, 'operatingCostMultiplier': 1}
    return sites, planning, scenario


def test_fixed_budget_caps_reallocated_material_cost_not_only_resources():
    sites, planning, scenario = inputs()
    # Building annuity 1,000 + fixed site 50 + physicians 100 + bed support 50.
    # 1,350 budget leaves 150 for materials, at 3 TRY / resident-equivalent.
    assert fixed_plan_costs(sites, planning, scenario) == (1200, 3)
    result = evaluate_fixed_plan(np.array([[1.]]), np.array([100.]), np.array(['a']),
        [{'id': 'a', 'population': 100}], 100, sites, planning, scenario,
        annual_budget=1350)
    assert result['maximumCoveredPopulation'] == pytest.approx(50)
    assert result['annualEquivalentCostTRY'] == pytest.approx(1350)
    assert result['annualBudget']['enforced'] is True
    assert result['targetsMet'] is False


def test_floor_relaxed_diagnostic_still_obeys_original_budget():
    sites, planning, scenario = inputs()
    scenario['districtFloor'] = 80
    result = evaluate_fixed_plan(np.array([[1.]]), [100.], np.array(['a']),
        [{'id': 'a', 'population': 100}], 100, sites, planning, scenario,
        annual_budget=1350)
    assert result['status'] == 'district_targets_infeasible'
    assert result['maximumCoveragePercent'] is None
    assert result['withoutDistrictTargets']['maximumCoveredPopulation'] == pytest.approx(50)
    assert result['withoutDistrictTargets']['annualEquivalentCostTRY'] == pytest.approx(1350)


def test_fixed_cost_budget_failure_is_not_misreported_as_a_district_failure():
    sites, planning, scenario = inputs()
    result = evaluate_fixed_plan(np.array([[np.inf]]), [100.], np.array(['a']),
        [{'id': 'a', 'population': 100}], 100, sites, planning, scenario,
        annual_budget=1199)
    assert result['status'] == 'fixed_cost_exceeds_budget'
    assert result['targetsMet'] is False
    assert result['districtTargetsFeasible'] is None


def test_operating_multiplier_does_not_scale_construction_annuity():
    sites, planning, scenario = inputs()
    scenario['operatingCostMultiplier'] = 2
    scenario['demandMultiplier'] = 1.5
    assert fixed_plan_costs(sites, planning, scenario) == (1400, 9)


def test_zero_material_cost_does_not_divide_by_zero():
    sites, planning, scenario = inputs()
    planning['economics']['costPerContactTRY'] = 0
    result = evaluate_fixed_plan(np.array([[1.]]), [100.], np.array(['a']),
        [{'id': 'a', 'population': 100}], 100, sites, planning, scenario,
        annual_budget=1200)
    assert result['targetsMet'] is True
    assert result['annualEquivalentCostTRY'] == pytest.approx(1200)
