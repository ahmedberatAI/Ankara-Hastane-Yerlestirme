"""Tamper controls for the independent saved-result physical audit."""
from copy import deepcopy
import json
import numpy as np
import pytest
from backend.hybrid import solve_hybrid
from scripts import verify_hybrid as audit


@pytest.fixture
def saved(tmp_path, monkeypatch):
    health = {'version': 'audit-toy', 'rates': {'contactsPerResident': 1, 'bedDaysPerResident': 365},
        'templates': [{'id': 'one', 'beds': 1, 'grossAreaM2': 1}, {'id': 'two', 'beds': 2, 'grossAreaM2': 2}],
        'design': {'areaPerDoctorM2': 1, 'maxFloors': 1, 'minimumDoctorsPerSite': 1},
        'economics': {'realDiscountRate': 0, 'horizonYears': 1, 'buildingUnitCostTRY': 1,
            'annualFixedSiteCostTRY': 1, 'annualDoctorCostTRY': 3, 'annualBedSupportCostTRY': 2,
            'costPerContactTRY': 5}}
    candidates = [{'id': str(i), 'candidateIndex': i, 'name': str(i), 'footprintRadiusMeters': 10,
        'lat': 39. + i, 'lon': 32. + i, 'node': i, 'entryLat': 39. + i, 'entryLon': 32. + i, 'accessMeters': 1} for i in range(2)]
    data = {'metadata': {'provincePopulation': 2}, 'candidates': candidates,
        'demands': [{'id': 'd0', 'population': 1, 'districtId': 'x'}, {'id': 'd1', 'population': 1, 'districtId': 'y'}],
        'districts': [{'id': 'x', 'population': 1}, {'id': 'y', 'population': 1}]}
    s = {'mode': 'hybrid', 'transitEngine': 'motis', 'threshold': 30, 'transitThreshold': 45,
         'carWeight': 70, 'coverageTarget': 100, 'districtFloor': 100, 'bedOccupancy': 100,
         'demandMultiplier': 1, 'contactsPerDoctor': 1, 'costTolerance': 10,
         'hospitalLimit': None, 'operatingCostMultiplier': 1, 'hybridNeighbors': None}
    car = np.array([[1., 20.], [2., 18.]])
    transit = np.array([[15., 4.], [17., 5.]])
    result = solve_hybrid(car, transit, [1, 1], ['x', 'y'], data['districts'], 2, health, s, candidates, time_limit=2)
    assert result['status'] == 'feasible'
    result['scenario'] = s
    result['transitEvidence'] = {'packageId': 'motis-test'}
    result['selected'] = [{**candidates[x['candidateIndex']], **x} for x in result.pop('capacitySites')]
    for modal in result['modalResults'].values():
        for assignment, demand in zip(modal['assignments'], data['demands']):
            assignment['demandId'] = demand['id']
            for part in assignment['allocations']:
                part['candidateId'] = candidates[part['candidateIndex']]['id']
    directory = tmp_path / 'data/processed'
    directory.mkdir(parents=True)
    (directory / 'dataset.json').write_text(json.dumps(data))
    (directory / 'health-planning.json').write_text(json.dumps(health))
    monkeypatch.setattr(audit, 'ROOT', tmp_path)
    monkeypatch.setattr(audit, 'code_identities', lambda: {'audit-test': 'same'})
    result['modelCodeLF_SHA256'] = audit.code_identities()
    result['dataSHA256'] = {'dataset': audit.motis.file_sha(directory / 'dataset.json'),
                            'planning': audit.motis.file_sha(directory / 'health-planning.json')}
    return result, data, health, {'car': car, 'transit': transit}, 'motis-test'


def test_saved_two_mode_physics_and_single_bill_reconstruct(saved):
    assert audit.audit(*saved)['provinceCoverageTarget'] == 100


@pytest.mark.parametrize('damage', ['double-materials', 'weight', 'threshold', 'coverage', 'doctor', 'flow', 'time', 'package', 'code'])
def test_independent_audit_rejects_tampered_claims(saved, damage):
    result, data, planning, matrices, package = deepcopy(saved)
    if damage == 'double-materials': result['capacity']['annualMaterialCostTRY'] *= 2
    elif damage == 'weight': result['hybridSummary']['weightedMeanMinutes'] += 1
    elif damage == 'threshold': result['hybridSummary']['thresholds']['transit'] += 1
    elif damage == 'coverage': result['modalResults']['transit']['metrics']['coveragePercent'] = 90
    elif damage == 'doctor': result['selected'][0]['doctors'] = 0
    elif damage == 'flow': result['modalResults']['transit']['assignments'][0]['allocations'][0]['population'] += 1
    elif damage == 'time': result['modalResults']['transit']['assignments'][0]['allocations'][0]['minutes'] += 1
    elif damage == 'package': result['transitEvidence']['packageId'] = 'other'
    elif damage == 'code': result['modelCodeLF_SHA256'] = {}
    with pytest.raises(AssertionError):
        audit.audit(result, data, planning, matrices, package)


@pytest.mark.parametrize('field', ['metrics', 'districts', 'assignments'])
def test_top_level_car_view_cannot_diverge_from_modal_view(saved, field):
    result, data, planning, matrices, package = deepcopy(saved)
    result[field] = {} if field == 'metrics' else []
    with pytest.raises(AssertionError, match='Top-level car view'):
        audit.audit(result, data, planning, matrices, package)


def test_duplicate_selected_or_district_entries_cannot_hide_in_set(saved):
    result, data, planning, matrices, package = deepcopy(saved)
    result['selectedIndices'].append(result['selectedIndices'][0])
    with pytest.raises(AssertionError):
        audit.audit(result, data, planning, matrices, package)
    result, data, planning, matrices, package = deepcopy(saved)
    result['modalResults']['transit']['districts'].append(deepcopy(result['modalResults']['transit']['districts'][0]))
    with pytest.raises(AssertionError):
        audit.audit(result, data, planning, matrices, package)


def test_overstaffed_plan_cannot_exceed_original_integer_variable_bound(saved):
    result, data, planning, matrices, package = deepcopy(saved)
    # Consistent extra resources can fit the physical plot and an enlarged
    # allowed budget, but violate the original model's target-based staff UB.
    site = result['selected'][0]
    delta = 3 - site['doctors']
    site['doctors'] = 3
    site['grossAreaM2'] += delta
    site['constructionCostTRY'] += delta
    site['operatingBreakdown']['physiciansTRY'] += 3 * delta
    site['annualOperatingCostTRY'] += 3 * delta
    site['annualEquivalentCostTRY'] += 4 * delta
    result['capacity']['totalDoctors'] += delta
    result['capacity']['constructionCostTRY'] += delta
    result['capacity']['annualOperatingCostTRY'] += 3 * delta
    result['capacity']['annualEquivalentCostTRY'] += 4 * delta
    result['scenario']['costTolerance'] = 30
    result['capacity']['budgetLimitTRY'] = result['capacity']['referenceCostTRY'] * 1.3
    with pytest.raises(AssertionError, match='Physician variable bound'):
        audit.audit(result, data, planning, matrices, package)


def test_tiny_district_floor_uses_original_percentage_tolerance(saved):
    result, data, planning, matrices, package = deepcopy(saved)
    assert len(result['selected']) == 1
    for mode, modal in result['modalResults'].items():
        for i, delta in [(0, -.00005), (1, .00005)]:
            assignment = modal['assignments'][i]
            assert len(assignment['allocations']) == 1
            part = assignment['allocations'][0]
            part['population'] += delta
            part['fraction'] = part['population']
            assignment['servedFraction'] = part['population']
            modal['districts'][i]['coveragePercent'] = part['population'] * 100
        modal['metrics']['meanMinutes'] = sum(a['allocations'][0]['population'] * a['allocations'][0]['minutes'] for a in modal['assignments']) / 2
    result['hybridSummary']['weightedMeanMinutes'] = .7 * result['modalResults']['car']['metrics']['meanMinutes'] + .3 * result['modalResults']['transit']['metrics']['meanMinutes']
    with pytest.raises(AssertionError, match='District percentage floor'):
        audit.audit(result, data, planning, matrices, package)
