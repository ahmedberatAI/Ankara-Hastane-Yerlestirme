"""Synthetic source/claim audits; no current processed dataset is read/written."""
from copy import deepcopy
from types import SimpleNamespace
import math
import numpy as np
import pytest
from backend.shared_capacity import repair_shared_capacity
import scripts.audit_shared_capacity as audit


def fixture():
    planning = {'version': 'tiny', 'rates': {'contactsPerResident': 1, 'bedDaysPerResident': 365},
        'templates': [{'id': 'one', 'beds': 1, 'grossAreaM2': 1}, {'id': 'two', 'beds': 2, 'grossAreaM2': 2}],
        'design': {'areaPerDoctorM2': 1, 'maxFloors': 1, 'minimumDoctorsPerSite': 1},
        'economics': {'realDiscountRate': 0, 'horizonYears': 1, 'buildingUnitCostTRY': 1,
            'annualFixedSiteCostTRY': 1, 'annualBedSupportCostTRY': 2, 'annualDoctorCostTRY': 3, 'costPerContactTRY': 5}}
    sites = [{'candidateIndex': i, 'id': str(i), 'footprintRadiusMeters': math.sqrt(5 / math.pi)} for i in range(2)]
    scenario = {'threshold': 45, 'coverageTarget': 100, 'districtFloor': 100, 'bedOccupancy': 100,
                'demandMultiplier': 1, 'contactsPerDoctor': 1, 'operatingCostMultiplier': 1}
    matrices = {name: np.array([[1, np.inf], [np.inf, 1]]) if i % 2 == 0 else
                np.array([[np.inf, 1], [1, np.inf]]) for i, name in enumerate(audit.PROFILES)}
    return matrices, np.array([1, 2]), np.array(['a', 'b']), [{'id': 'a', 'population': 1}, {'id': 'b', 'population': 2}], 3, sites, planning, scenario


def result_and_ceiling():
    args = fixture()
    result = repair_shared_capacity(*args, original_annual_budget=100, time_limit=3)
    ceiling = audit.independent_resource_ceiling(*args)
    return args, result, ceiling


def test_independent_serialized_flow_cost_audit_and_ceiling_pass():
    args, result, ceiling = result_and_ceiling()
    audit.audit_shared_result(result, *args, 100)
    audit.verify_ceiling_record(ceiling, ceiling)
    audit.verify_recomputed_claims(result, result, ceiling)
    assert result['totalBeds'] == result['totalDoctors'] == 4
    assert result['annualEquivalentCostTRY'] == 45
    assert all(x['maximumCoveragePercent'] == 100 for x in ceiling['profiles'])
    assert all(x['linearProgrammingDualCertified'] for x in ceiling['profiles'])


@pytest.mark.parametrize('field', ['area', 'radius', 'physicians', 'beds', 'money', 'allocation', 'time', 'profile', 'budget', 'bound_scope'])
def test_mutated_report_is_not_blessed(field):
    args, result, _ = result_and_ceiling()
    if field == 'area': result['selected'][0]['grossAreaM2'] += 2
    elif field == 'radius': result['selected'][0]['footprintRadiusMeters'] += 1
    elif field == 'physicians': result['selected'][0]['doctors'] = 1
    elif field == 'beds': result['selected'][0]['beds'] = 1
    elif field == 'money': result['annualEquivalentCostTRY'] += 10
    elif field == 'allocation': result['profiles'][0]['allocations'][0]['population'] += 1
    elif field == 'time': result['profiles'][0]['allocations'][0]['minutes'] = 46
    elif field == 'profile': result['profiles'][0]['profile'] = 'wrong'
    elif field == 'bound_scope': result['boundScope'] = 'global_All_Ankara_minimum_hospital_count'
    else: result['originalAnnualBudgetTRY'] = 999
    with pytest.raises((AssertionError, KeyError)):
        audit.audit_shared_result(result, *args, 100)


def test_cost_free_physical_upper_bound_can_certify_failure():
    args = list(fixture())
    args[6]['templates'] = args[6]['templates'][:1]  # one resident per site
    args[7]['districtFloor'] = 0
    ceiling = audit.independent_resource_ceiling(*args)
    assert ceiling['anyProfileProvesTargetsImpossible']
    for row in ceiling['profiles']:
        assert row['status'] == 'optimal'
        assert row['maximumCoveredPopulation'] == pytest.approx(2)
        assert row['certifiedPopulationUpperBound'] == pytest.approx(2)
        assert row['provinceTargetShortfallResidents'] == pytest.approx(1)


def test_district_infeasibility_is_not_zero_coverage():
    args = list(fixture())
    args[6]['templates'] = args[6]['templates'][:1]
    ceiling = audit.independent_resource_ceiling(*args)
    for row in ceiling['profiles']:
        assert row['status'] == 'district_targets_infeasible'
        assert row['maximumCoveragePercent'] is None
        assert row['provinceTargetShortfallResidents'] is None
        assert row['districtTargetsFeasible'] is False


def test_nearly_integral_area_does_not_remove_a_valid_integer_physician():
    args = list(fixture())
    args[0] = {name: np.ones((1, 1)) for name in audit.PROFILES}
    args[1:5] = [np.array([2]), np.array(['a']), [{'id': 'a', 'population': 2}], 2]
    args[5] = [{'candidateIndex': 0, 'id': '0', 'footprintRadiusMeters': math.sqrt(4 / math.pi)}]
    args[7]['districtFloor'] = 0
    assert math.pi * args[5][0]['footprintRadiusMeters'] ** 2 < 4
    result = repair_shared_capacity(*args, original_annual_budget=100, time_limit=3)
    ceiling = audit.independent_resource_ceiling(*args)
    assert result['status'] == 'feasible'
    assert result['totalBeds'] == result['totalDoctors'] == 2
    audit.audit_shared_result(result, *args, 100)
    audit.verify_recomputed_claims(result, result, ceiling)
    assert not ceiling['anyProfileProvesTargetsImpossible']
    assert all(r['maximumCoveredPopulation'] == 2 for r in ceiling['profiles'])


def test_ceiling_area_tolerance_is_optimistic_but_bounded():
    args = list(fixture())
    args[0] = {name: np.ones((1, 1)) for name in audit.PROFILES}
    args[1:5] = [np.array([2]), np.array(['a']), [{'id': 'a', 'population': 2}], 2]
    args[7]['districtFloor'] = 0
    for missing_area, expected in ((.0005, 2), (.002, 1)):
        args[5] = [{'candidateIndex': 0, 'id': '0', 'footprintRadiusMeters': math.sqrt((4 - missing_area) / math.pi)}]
        ceiling = audit.independent_resource_ceiling(*args)
        assert all(r['maximumCoveredPopulation'] == expected for r in ceiling['profiles'])


@pytest.mark.parametrize('status', ['inconclusive', 'infeasible'])
@pytest.mark.parametrize('field', ['provenOptimal', 'incumbentValidated', 'timeLimitedFeasible', 'annualMaterialCostTRY'])
def test_terminal_failure_cannot_claim_a_validated_or_optimal_incumbent(monkeypatch, status, field):
    import backend.shared_capacity as shared
    monkeypatch.setattr(shared, 'optimize', lambda *a, **k: SimpleNamespace(
        status=2 if status == 'infeasible' else 1, x=None, mip_dual_bound=np.nan, mip_gap=np.inf))
    args = fixture()
    result = repair_shared_capacity(*args, original_annual_budget=100, time_limit=3)
    audit.audit_shared_result(result, *args, 100)
    result[field] = 1. if field == 'annualMaterialCostTRY' else True
    with pytest.raises(AssertionError): audit.audit_shared_result(result, *args, 100)


@pytest.mark.parametrize('failure', ['district_targets_infeasible', 'mandatory_site_infeasible'])
@pytest.mark.parametrize('value', [True, False, None])
def test_physical_failure_district_label_must_match_status(failure, value):
    args = list(fixture())
    if failure == 'district_targets_infeasible':
        args[6]['templates'] = args[6]['templates'][:1]
    else:
        args[5][0]['footprintRadiusMeters'] = .01
    ceiling = audit.independent_resource_ceiling(*args)
    saved = deepcopy(ceiling)
    saved['profiles'][0]['districtTargetsFeasible'] = value
    if value is (False if failure == 'district_targets_infeasible' else None):
        audit.verify_ceiling_record(saved, ceiling)
    else:
        with pytest.raises(AssertionError): audit.verify_ceiling_record(saved, ceiling)


def test_lp_time_limit_stays_unknown_even_if_a_partial_incumbent_exists(monkeypatch):
    monkeypatch.setattr(audit, 'linprog', lambda *a, **k: SimpleNamespace(
        status=1, success=False, message='time limit', x=np.ones(2), fun=-2))
    ceiling = audit.independent_resource_ceiling(*fixture())
    assert not ceiling['anyProfileProvesTargetsImpossible']
    for row in ceiling['profiles']:
        assert row['status'] == 'inconclusive'
        assert row['maximumCoveragePercent'] is None and row['provinceTargetPossible'] is None


def test_bad_lp_dual_is_inconclusive_not_a_certificate(monkeypatch):
    original = audit.linprog
    def corrupt(*args, **kwargs):
        result = original(*args, **kwargs)
        result.ineqlin.marginals[:] = 1
        return result
    monkeypatch.setattr(audit, 'linprog', corrupt)
    ceiling = audit.independent_resource_ceiling(*fixture())
    assert all(row['status'] == 'inconclusive' for row in ceiling['profiles'])


def test_no_edges_and_nonfitting_mandatory_site_report_distinct_failures():
    args = list(fixture())
    args[0] = {name: np.full((2, 2), np.inf) for name in audit.PROFILES}
    assert audit.independent_resource_ceiling(*args)['profiles'][0]['status'] == 'district_targets_infeasible'
    args[5][0]['footprintRadiusMeters'] = .01
    ceiling = audit.independent_resource_ceiling(*args)
    assert ceiling['impossibleMandatorySiteIndices'] == [0]
    assert ceiling['profiles'][0]['status'] == 'mandatory_site_infeasible'


def test_unknown_saved_ceiling_cannot_silently_gain_zero_value_or_false_proof():
    _, _, ceiling = result_and_ceiling()
    saved = deepcopy(ceiling)
    saved['profiles'][0].update(status='inconclusive', maximumCoveragePercent=None,
        maximumCoveredPopulation=None, certifiedPopulationUpperBound=None, provinceTargetShortfallResidents=None,
        linearProgrammingDualCertified=False, provinceTargetPossible=None, districtTargetsFeasible=None)
    audit.verify_ceiling_record(saved, ceiling)
    saved['profiles'][0]['maximumCoveragePercent'] = 0
    with pytest.raises(AssertionError): audit.verify_ceiling_record(saved, ceiling)


def test_claimed_optimum_or_infeasibility_needs_new_evidence():
    _, result, ceiling = result_and_ceiling()
    weak = deepcopy(result); weak['minimumAnnualCostLowerBoundTRY'] = 0
    with pytest.raises(AssertionError, match='too weak'):
        audit.verify_recomputed_claims(result, weak, ceiling)
    infeasible = {'status': 'infeasible', 'minimumAnnualCostLowerBoundTRY': None}
    with pytest.raises(AssertionError, match='contradicts'):
        audit.verify_recomputed_claims(infeasible, result, ceiling)
    inconclusive = {'status': 'inconclusive', 'minimumAnnualCostLowerBoundTRY': None}
    with pytest.raises(AssertionError, match='No reproduced proof'):
        audit.verify_recomputed_claims(infeasible, inconclusive, ceiling)


def identity_fixture():
    candidate = {'id': 'c', 'lon': 32, 'lat': 40, 'node': 0, 'entryLon': 32, 'entryLat': 40,
                 'accessMeters': 10, 'footprintRadiusMeters': 45}
    data = {'metadata': {'transitPackageId': 'pkg'}, 'candidates': [candidate], 'demands': [{'id': 'd'}],
            'districts': [{'id': 'a', 'population': 1}, {'id': 'b', 'population': 2}]}
    plan = {'status': 'feasible', 'scenario': {'mode': 'transit', 'threshold': 45, 'coverageTarget': 95,
            'districtFloor': 80, 'transitProfile': 'weekday-1000'}, 'metadata': {'transitPackageId': 'pkg'},
            'transitEvidence': {'packageId': 'pkg'}, 'selected': [{**candidate, 'candidateIndex': 0}],
            'hospitalCount': 1, 'selectedIndices': [0], 'assignments': [{'demandId': 'd'}],
            'districts': deepcopy(data['districts']),
            'capacity': {'planningVersion': 'tiny', 'budgetLimitTRY': 100}}
    return plan, data, {'version': 'tiny'}, 'pkg'


@pytest.mark.parametrize('change', ['package', 'plot', 'identity', 'demand', 'target', 'calibration'])
def test_source_plan_cannot_migrate_to_new_package_or_plot(change):
    plan, data, health, package = identity_fixture()
    audit.validate_source_identity(plan, data, health, package)
    if change == 'package': plan['metadata']['transitPackageId'] = 'old'
    elif change == 'plot': plan['selected'][0]['footprintRadiusMeters'] = 80
    elif change == 'identity': plan['selected'][0]['id'] = 'other'
    elif change == 'demand': plan['assignments'][0]['demandId'] = 'other'
    elif change == 'target': plan['scenario']['coverageTarget'] = 90
    else: health['version'] = 'new'
    with pytest.raises(AssertionError): audit.validate_source_identity(plan, data, health, package)


@pytest.mark.parametrize('change', ['missing', 'empty', 'duplicate', 'unknown', 'denominator', 'negative', 'boolean'])
def test_source_plan_district_identity_completeness_and_denominators(change):
    plan, data, health, package = identity_fixture()
    if change == 'missing': plan['districts'].pop()
    elif change == 'empty': plan['districts'] = []
    elif change == 'duplicate': plan['districts'][1] = deepcopy(plan['districts'][0])
    elif change == 'unknown': plan['districts'][0]['id'] = 'not-in-source'
    elif change == 'denominator': plan['districts'][0]['population'] = 3
    elif change == 'negative': plan['districts'][0]['population'] = -1
    else: plan['districts'][0]['population'] = True
    with pytest.raises(AssertionError): audit.validate_source_identity(plan, data, health, package)


def test_same_district_records_may_be_reordered():
    plan, data, health, package = identity_fixture()
    plan['districts'].reverse()
    audit.validate_source_identity(plan, data, health, package)


def test_production_runner_has_no_frozen_artifacts_bypass_and_checks_package_first(monkeypatch):
    called = []
    def reject(root):
        called.append(root)
        raise AssertionError('package mismatch')
    monkeypatch.setattr(audit, 'check_package', reject)
    with pytest.raises(AssertionError, match='package mismatch'):
        audit.run(write=False)
    assert len(called) == 1


@pytest.mark.parametrize('field', ['transitPackageId', 'sourcePlan', 'sourceFiles', 'modelFiles'])
def test_exact_plan_matrix_health_and_code_bindings_cannot_be_relabelled(field):
    source = {'sha256': 'plan-sha', 'hospitalCount': 2, 'scenario': {'threshold': 45}, 'originalAnnualBudgetTRY': 100}
    inputs = {'matrix': 'matrix-sha', 'health': 'health-sha'}
    models = {'model.py': 'code-sha'}
    record = {'format': 1, 'scope': audit.REPORT_SCOPE, 'transitPackageId': 'package',
              'sourcePlan': deepcopy(source), 'sourceFiles': deepcopy(inputs), 'modelFiles': deepcopy(models)}
    audit.verify_bindings(record, 'package', source, inputs, models)
    if field == 'transitPackageId': record[field] = 'another-package'
    elif field == 'sourcePlan': record[field]['sha256'] = 'new-plan-sha'
    else: record[field][next(iter(record[field]))] = 'changed-hash'
    with pytest.raises(AssertionError): audit.verify_bindings(record, 'package', source, inputs, models)
