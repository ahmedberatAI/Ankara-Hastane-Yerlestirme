"""Independent certificate audit regressions; never invoke an optimizer."""
from copy import deepcopy
import json
import math
import os
from pathlib import Path

import numpy as np
import pytest

from scripts import audit_joint_plan as a

ROOT = Path(__file__).resolve().parents[1]


def update_cost(cert, health):
    plan = cert['plan']; sites = plan['selected']; e = health['economics']; s = cert['scenario']
    construction = sum(x['grossAreaM2'] for x in sites) * e['buildingUnitCostTRY'] / e['horizonYears']
    fixed = sum(e['annualFixedSiteCostTRY'] + x['beds'] * e['annualBedSupportCostTRY']
                + x['doctors'] * e['annualDoctorCostTRY'] for x in sites) * s['operatingCostMultiplier']
    material = 190 * health['rates']['contactsPerResident'] * s['demandMultiplier'] * e['costPerContactTRY'] * s['operatingCostMultiplier']
    plan['annualEquivalentCostTRY'] = construction + fixed + material
    plan['annualMaterialCostTRY'] = material
    plan['annualFixedResourceCostTRY'] = construction + fixed
    plan['hospitalCount'] = len(sites); plan['totalBeds'] = sum(x['beds'] for x in sites)
    plan['totalDoctors'] = sum(x['doctors'] for x in sites)


@pytest.fixture
def tiny():
    scenario = {'mode': 'transit', 'threshold': 45, 'coverageTarget': 95., 'districtFloor': 80.,
                'trafficFactor': 1., 'demandMultiplier': 1., 'bedOccupancy': 80., 'contactsPerDoctor': 20,
                'costTolerance': 10., 'hospitalLimit': None, 'operatingCostMultiplier': 1., 'transitProfile': 'weekday-1000'}
    data = {'metadata': {'transitPackageId': 'p', 'transitProfiles': list(a.PROFILES), 'provincePopulation': 200},
            'districts': [{'id': 'a', 'name': 'A', 'population': 100}, {'id': 'b', 'name': 'B', 'population': 100}],
            'demands': [{'id': 'da', 'districtId': 'a', 'population': 100}, {'id': 'db', 'districtId': 'b', 'population': 100}],
            'candidates': [{'id': f's{j}', 'lon': 32.8 + j * .1, 'lat': 39.9, 'footprintRadiusMeters': 10.} for j in range(3)]}
    health = {'version': 'h', 'design': {'minimumDoctorsPerSite': 1, 'areaPerDoctorM2': 1, 'maxFloors': 1},
              'rates': {'contactsPerResident': 1., 'bedDaysPerResident': 1.},
              'templates': [{'id': 'ten', 'beds': 10, 'grossAreaM2': 100}],
              'economics': {'realDiscountRate': 0., 'horizonYears': 10, 'buildingUnitCostTRY': 100,
                            'annualFixedSiteCostTRY': 1000, 'annualDoctorCostTRY': 200,
                            'annualBedSupportCostTRY': 100, 'costPerContactTRY': 5}}
    matrices = {p: np.array([[10., 11., np.inf], [20., 21., np.inf]]) for p in a.PROFILES}
    hashes = {name: a.sha256(name.encode()) for name in a.SOURCE_FILES}
    cert = {'format': 1, 'transitPackageId': 'p', 'planningVersion': 'h', 'scenario': scenario,
            'sourceSHA256': deepcopy(hashes), 'generation': {'method': 'Synthetic certificate; no solve',
                'researchReportSHA256': 'a' * 64, 'researchVectorSHA256': 'b' * 64, 'searchProvenOptimal': False,
                'minimumHospitalCountProven': False, 'travelTimeOptimized': False, 'annualDemandCountedOnce': True,
                'sameIndividualsAcrossProfilesConstrained': False},
            'plan': {'selected': [{'candidateIndex': 0, 'id': 's0', 'templateId': 'ten', 'beds': 10, 'doctors': 10,
                                  'grossAreaM2': 110., 'footprintRadiusMeters': 10., 'maximumAssignedPopulationAcrossProfiles': 190.}],
                     'profiles': []}}
    for p, amounts in zip(a.PROFILES, [(90, 100), (100, 90), (95, 95), (95, 95)]):
        cert['plan']['profiles'].append({'profile': p, 'coveredPopulation': 190., 'coveragePercent': 95.,
            'meanMinutes': (amounts[0] * 10 + amounts[1] * 20) / 190,
            'districts': [{'id': k, 'coveragePercent': float(n)} for k, n in zip(('a', 'b'), amounts)],
            'allocations': [{'demandIndex': i, 'candidateIndex': 0, 'population': float(n), 'minutes': float(10 + i * 10)}
                            for i, n in enumerate(amounts)]})
    update_cost(cert, health)
    published = {'status': 'feasible', 'transitEvidence': {'packageId': 'p'},
                 'scenario': deepcopy(scenario), 'metadata': {'transitPackageId': 'p', 'provincePopulation': 200},
                 'capacity': {'planningVersion': 'h', 'budgetLimitTRY': 10000.}}
    return cert, data, health, matrices, published, hashes


def test_tiny_independent_resource_cost_and_intersection(tiny):
    r = a.validate_joint_plan(*tiny, package_id='p')
    assert r['witnessFound'] and r['status'] == 'witness_validated'
    assert r['annualEquivalentCostTRY'] == 6050 and a.D(r['decimalAnnualMaterialCostTRY']) == 950
    assert r['hospitalCount'] == 1 and r['beds'] == 10 and r['doctors'] == 10
    assert r['budgetSlackTRY'] == 3950
    assert all(p['coveragePercent'] == 95 for p in r['profiles'])
    assert r['conditionalOverlap']['province']['lowerPercent'] == 80
    assert r['conditionalOverlap']['province']['upperPercent'] == 90
    assert not r['sameIndividualsAcrossProfilesConstrained'] and not r['solverRun']


def test_above_budget_is_valid_plan_not_global_infeasibility(tiny):
    tiny[4]['capacity']['budgetLimitTRY'] = 6049.99
    r = a.validate_joint_plan(*tiny)
    assert not r['witnessFound'] and not r['withinOriginalTransitBudget']
    assert r['status'] == 'validated_model_plan_above_reference_budget'
    # Even a one-cent overrun is not rounded into a budget witness.
    assert r['budgetSlackTRY'] == pytest.approx(-.01)


@pytest.mark.parametrize('flag', ['searchProvenOptimal', 'minimumHospitalCountProven', 'travelTimeOptimized',
                                'annualDemandCountedOnce', 'sameIndividualsAcrossProfilesConstrained'])
@pytest.mark.parametrize('value', [1, 0, None, 'false'])
def test_claim_flags_are_strict_booleans(tiny, flag, value):
    tiny[0]['generation'][flag] = value
    with pytest.raises(ValueError): a.validate_joint_plan(*tiny)


@pytest.mark.parametrize('mutation', [
    'source_sha', 'source_file', 'cert_package', 'current_package', 'health', 'ref_health', 'profiles_metadata',
    'reference_status', 'reference_evidence', 'missing_reference_evidence',
    'format_bool', 'extra_optimal_claim', 'selected_duplicate', 'selected_identity', 'selected_bool', 'selected_unknown',
    'hospital_float', 'beds', 'doctors_fractional', 'minimum_doctors', 'footprint', 'area_report', 'area_limit', 'plot_overlap',
    'duplicate_candidate', 'candidate_nan', 'duplicate_demand', 'demand_unknown_district', 'duplicate_district',
    'district_denominator', 'located_denominator', 'missing_profile', 'duplicate_profile', 'profile_order',
    'missing_profile_district', 'duplicate_profile_district', 'unknown_profile_district', 'district_summary',
    'closed_flow', 'duplicate_flow', 'flow_identity', 'zero_flow', 'negative_flow', 'nan_flow', 'inf_flow', 'bool_flow',
    'float_index', 'minutes_mismatch', 'unreachable', 'over_threshold', 'matrix_nan', 'matrix_negative', 'matrix_shape',
    'matrix_boolean', 'missing_matrix', 'origin_excess', 'province_target', 'doctor_capacity', 'bed_capacity',
    'maximum_load', 'total_doctors', 'double_material', 'cost_summary', 'profile_mean', 'profile_coverage'])
def test_rejects_malformed_or_invalid_complete_plan(tiny, mutation):
    c, d, h, m, p, hashes = tiny; plan = c['plan']; site = plan['selected'][0]; profile = plan['profiles'][0]
    flow = profile['allocations'][0]
    if mutation == 'source_sha': c['sourceSHA256']['dataset.json'] = '0' * 64
    elif mutation == 'source_file': del c['sourceSHA256']['dataset.json']
    elif mutation == 'cert_package': c['transitPackageId'] = 'stale'
    elif mutation == 'current_package': d['metadata']['transitPackageId'] = 'stale'
    elif mutation == 'health': c['planningVersion'] = 'stale'
    elif mutation == 'ref_health': p['capacity']['planningVersion'] = 'stale'
    elif mutation == 'profiles_metadata': d['metadata']['transitProfiles'].pop()
    elif mutation == 'reference_status': p['status'] = 'infeasible'
    elif mutation == 'reference_evidence': p['transitEvidence']['packageId'] = 'stale'
    elif mutation == 'missing_reference_evidence': del p['transitEvidence']
    elif mutation == 'format_bool': c['format'] = True
    elif mutation == 'extra_optimal_claim': plan['provenOptimal'] = True
    elif mutation == 'selected_duplicate': plan['selected'].append(deepcopy(site)); plan['hospitalCount'] += 1
    elif mutation == 'selected_identity': site['id'] = 's1'
    elif mutation == 'selected_bool': site['candidateIndex'] = False
    elif mutation == 'selected_unknown': site['candidateIndex'] = 99
    elif mutation == 'hospital_float': plan['hospitalCount'] = 1.
    elif mutation == 'beds': site['beds'] += 1
    elif mutation == 'doctors_fractional': site['doctors'] = 10.5
    elif mutation == 'minimum_doctors': site['doctors'] = 0
    elif mutation == 'footprint': site['footprintRadiusMeters'] += 1
    elif mutation == 'area_report': site['grossAreaM2'] += 1
    elif mutation == 'area_limit': site['footprintRadiusMeters'] = d['candidates'][0]['footprintRadiusMeters'] = 1.
    elif mutation == 'plot_overlap':
        duplicate = deepcopy(site); duplicate.update(candidateIndex=1, id='s1')
        plan['selected'].append(duplicate); plan['hospitalCount'] += 1
        d['candidates'][1].update(lon=d['candidates'][0]['lon'], lat=d['candidates'][0]['lat'])
        update_cost(c, h)
    elif mutation == 'duplicate_candidate': d['candidates'][1]['id'] = 's0'
    elif mutation == 'candidate_nan': d['candidates'][0]['lon'] = float('nan')
    elif mutation == 'duplicate_demand': d['demands'][1]['id'] = 'da'
    elif mutation == 'demand_unknown_district': d['demands'][0]['districtId'] = 'unknown'
    elif mutation == 'duplicate_district': d['districts'][1]['id'] = 'a'
    elif mutation == 'district_denominator': d['districts'][0]['population'] += 1
    elif mutation == 'located_denominator': d['districts'][0]['population'] = 99; d['districts'][1]['population'] = 101
    elif mutation == 'missing_profile': plan['profiles'].pop()
    elif mutation == 'duplicate_profile': plan['profiles'][1] = deepcopy(profile)
    elif mutation == 'profile_order': plan['profiles'].reverse()
    elif mutation == 'missing_profile_district': profile['districts'].pop()
    elif mutation == 'duplicate_profile_district': profile['districts'][1] = deepcopy(profile['districts'][0])
    elif mutation == 'unknown_profile_district': profile['districts'][0]['id'] = 'x'
    elif mutation == 'district_summary': profile['districts'][0]['coveragePercent'] += 1
    elif mutation == 'closed_flow': flow['candidateIndex'] = 1
    elif mutation == 'duplicate_flow': profile['allocations'].append(deepcopy(flow))
    elif mutation == 'flow_identity': flow['demandIndex'] = 99
    elif mutation == 'zero_flow': flow['population'] = 0
    elif mutation == 'negative_flow': flow['population'] = -1
    elif mutation == 'nan_flow': flow['population'] = float('nan')
    elif mutation == 'inf_flow': flow['population'] = float('inf')
    elif mutation == 'bool_flow': flow['population'] = True
    elif mutation == 'float_index': flow['demandIndex'] = 0.
    elif mutation == 'minutes_mismatch': flow['minutes'] += .01
    elif mutation == 'unreachable': m[profile['profile']][0, 0] = np.inf
    elif mutation == 'over_threshold': m[profile['profile']][0, 0] = flow['minutes'] = 45.01
    elif mutation == 'matrix_nan': m[profile['profile']][0, 2] = np.nan
    elif mutation == 'matrix_negative': m[profile['profile']][0, 2] = -1
    elif mutation == 'matrix_shape': m[profile['profile']] = np.zeros((2, 2))
    elif mutation == 'matrix_boolean': m[profile['profile']] = np.zeros((2, 3), dtype=bool)
    elif mutation == 'missing_matrix': del m[a.PROFILES[1]]
    elif mutation == 'origin_excess': flow['population'] = 101; profile['allocations'][1]['population'] = 89
    elif mutation == 'province_target': flow['population'] -= 1
    elif mutation == 'doctor_capacity':
        site['doctors'] = 9; site['grossAreaM2'] = 109.; update_cost(c, h)
    elif mutation == 'bed_capacity':
        h['rates']['bedDaysPerResident'] = 20.
    elif mutation == 'maximum_load': site['maximumAssignedPopulationAcrossProfiles'] += 1
    elif mutation == 'total_doctors': plan['totalDoctors'] += 1
    elif mutation == 'double_material':
        plan['annualEquivalentCostTRY'] += plan['annualMaterialCostTRY']; plan['annualMaterialCostTRY'] *= 2
    elif mutation == 'cost_summary': plan['annualEquivalentCostTRY'] += 10
    elif mutation == 'profile_mean': profile['meanMinutes'] += 1
    elif mutation == 'profile_coverage': profile['coveragePercent'] += 1
    with pytest.raises(ValueError): a.validate_joint_plan(*tiny)


@pytest.mark.parametrize('key,value', [('threshold', 46), ('coverageTarget', 94), ('districtFloor', 79),
                                     ('hospitalLimit', 91), ('mode', 'car'), ('transitProfile', 'sunday-1000'),
                                     ('bedOccupancy', 101), ('contactsPerDoctor', True), ('demandMultiplier', float('nan'))])
def test_wrong_scenarios_are_rejected_even_when_reference_matches(tiny, key, value):
    tiny[0]['scenario'][key] = tiny[4]['scenario'][key] = value
    with pytest.raises(ValueError): a.validate_joint_plan(*tiny)


def test_unchanged_scenario_parameters_must_match_reference(tiny):
    tiny[0]['scenario']['operatingCostMultiplier'] = 1.01
    with pytest.raises(ValueError): a.validate_joint_plan(*tiny)


def test_unused_open_site_preserves_cost_resources_and_count(tiny):
    c, d, h, m, p, hashes = tiny
    extra = deepcopy(c['plan']['selected'][0]); extra.update(candidateIndex=1, id='s1', doctors=1,
                                                            grossAreaM2=101., maximumAssignedPopulationAcrossProfiles=0.)
    c['plan']['selected'].append(extra); update_cost(c, h)
    r = a.validate_joint_plan(*tiny)
    assert r['hospitalCount'] == 2 and r['beds'] == 20 and r['doctors'] == 11
    assert r['annualEquivalentCostTRY'] == 9260
    assert r['selected'][1]['maximumAssignedPopulationAcrossProfiles'] == 0


def test_physical_spare_staff_cannot_exceed_original_model_variable_bound(tiny):
    c, d, h, m, p, hashes = tiny
    # ceil(190 contacts / 20 contacts per doctor) = 10. An eleventh doctor fits
    # the plot and budget, but not the original model's explicit variable bound.
    c['plan']['selected'][0]['doctors'] = 11
    c['plan']['selected'][0]['grossAreaM2'] = 111.
    update_cost(c, h)
    with pytest.raises(ValueError, match='province-derived staff bound'):
        a.validate_joint_plan(*tiny)


@pytest.mark.parametrize('throughput,accepted', [(19., False), (math.nextafter(19., 0.), True),
                                                (math.nextafter(19., math.inf), False)])
def test_staff_bound_preserves_declared_float_ceil_boundary(tiny, throughput, accepted):
    c, d, h, m, p, hashes = tiny
    c['scenario']['contactsPerDoctor'] = p['scenario']['contactsPerDoctor'] = throughput
    c['plan']['selected'][0].update(doctors=11, grossAreaM2=111.)
    update_cost(c, h)
    if accepted:
        assert a.validate_joint_plan(*tiny)['doctors'] == 11
    else:
        with pytest.raises(ValueError, match='province-derived staff bound'):
            a.validate_joint_plan(*tiny)


def test_district_percentage_tolerance_does_not_use_absolute_resident_shortcut(tiny):
    # The origin/province tolerances allow this .00005 person movement, but the
    # first district is 79.995%, outside its actual percentage tolerance.
    c, d, h, m, p, hashes = tiny
    d['districts'][0]['population'] = d['demands'][0]['population'] = .001
    d['districts'][1]['population'] = d['demands'][1]['population'] = 10.999
    d['metadata']['provincePopulation'] = p['metadata']['provincePopulation'] = 11.
    c['plan']['selected'][0]['doctors'] = 1
    c['plan']['selected'][0]['grossAreaM2'] = 101.
    c['plan']['totalDoctors'] = 1
    for profile in c['plan']['profiles']:
        profile['allocations'][0]['population'] = .00079995
        profile['allocations'][1]['population'] = 10.45 - .00079995
    with pytest.raises(ValueError, match='District percentage target'): a.validate_joint_plan(*tiny)


def write_fixture(directory, tiny):
    c, d, h, matrices, p, hashes = deepcopy(tiny)
    directory.mkdir(parents=True, exist_ok=True)
    for name, payload in [('dataset.json', d), ('health-planning.json', h), ('example-transit-result.json', p),
                           ('transit-package.json', {'packageId': 'p'})]:
        (directory / name).write_text(json.dumps(payload), encoding='utf8')
    for name, matrix in matrices.items(): np.savez_compressed(directory / f'transit-{name}-matrix.npz', minutes=matrix)
    c['sourceSHA256'] = {name: a.sha256((directory / name).read_bytes()) for name in a.SOURCE_FILES}
    (directory / 'joint-plan.json').write_text(json.dumps(c), encoding='utf8')
    return directory


@pytest.fixture
def cli(tmp_path, tiny, monkeypatch):
    directory = write_fixture(tmp_path / 'data/processed', tiny)
    monkeypatch.setattr(a, 'ROOT', tmp_path)
    calls = []
    def package(root): calls.append(root); return 'p'
    monkeypatch.setattr(a, 'check_package', package)
    return directory, calls


def test_real_current_certificate_has_valid_independent_full_plan():
    r = a.current_report(ROOT / 'data/processed')
    c = a.load_json((ROOT / 'data/processed/joint-plan.json').read_bytes())
    assert r['hospitalCount'] == c['plan']['hospitalCount']
    assert r['beds'] == c['plan']['totalBeds'] and r['doctors'] == c['plan']['totalDoctors']
    assert len(r['profiles']) == 4 and all(len(p['districts']) == 25 for p in r['profiles'])
    assert len(r['sourceSHA256']) == 9 and not r['solverRun']
    assert all(p['maxMinutes'] <= 45 and p['minimumDistrictCoveragePercent'] >= 80 - 1e-6 for p in r['profiles'])


def test_cli_safe_write_then_default_readonly(cli):
    directory, calls = cli
    inputs = {name: (directory / name).read_bytes() for name in a.FILES}
    r = a.run(write=True); before = {p.name: p.read_bytes() for p in directory.iterdir()}
    assert a.run() == r and len(calls) == 4
    assert before == {p.name: p.read_bytes() for p in directory.iterdir()}
    assert inputs == {name: (directory / name).read_bytes() for name in a.FILES}


@pytest.mark.parametrize('field,value', [('format', True), ('witnessFound', 1), ('solverRun', 0),
                                     ('hospitalCount', 1.), ('annualEquivalentCostTRY', float('nan'))])
def test_summary_comparison_is_type_strict(cli, field, value):
    directory, calls = cli; report = a.current_report(directory); report[field] = value
    with pytest.raises(ValueError): a.compare_report(report, directory)


@pytest.mark.parametrize('name', a.SOURCE_FILES)
def test_every_bound_source_change_rejects_certificate(cli, name):
    directory, calls = cli; path = directory / name; path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError): a.current_report(directory)


def test_certificate_byte_change_invalidates_saved_summary(cli):
    directory, calls = cli; r = a.run(write=True)
    path = directory / 'joint-plan.json'; path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError): a.run()
    assert not a.digest(r) == a.digest(a.current_report(directory))


@pytest.mark.parametrize('payload', [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'{"a":-Infinity}'])
def test_json_parser_rejects_duplicates_and_nonfinite(payload):
    with pytest.raises(ValueError): a.load_json(payload)


def test_exit_package_change_prevents_publication(cli, monkeypatch):
    directory, calls = cli; seq = iter(['p', 'changed'])
    monkeypatch.setattr(a, 'check_package', lambda root: next(seq))
    with pytest.raises(ValueError, match='Package changed'): a.run(write=True)
    assert not (directory / 'joint-plan-summary.json').exists()


def test_exit_source_change_prevents_publication(cli, monkeypatch):
    directory, calls = cli
    def package(root):
        calls.append(root)
        if len(calls) == 2:
            path = directory / 'joint-plan.json'; path.write_bytes(path.read_bytes() + b' ')
        return 'p'
    monkeypatch.setattr(a, 'check_package', package)
    with pytest.raises(ValueError, match='Source changed'): a.run(write=True)
    assert not (directory / 'joint-plan-summary.json').exists()


def test_hardlinked_output_does_not_modify_input(cli):
    directory, calls = cli; source = directory / 'joint-plan.json'; original = source.read_bytes()
    os.link(source, directory / 'joint-plan-summary.json')
    # Also poison the old predictable temporary spelling. It must never be opened.
    os.link(source, directory / 'joint-plan-summary.json.tmp')
    a.run(write=True)
    assert source.read_bytes() == original
    assert (directory / 'joint-plan-summary.json.tmp').read_bytes() == original


def test_failed_replace_removes_only_own_temporary_file(cli, monkeypatch):
    directory, calls = cli; marker = directory / '.joint-plan-keep.json.tmp'; marker.write_text('keep')
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    def fail(*args): raise OSError('replace failed')
    monkeypatch.setattr(Path, 'replace', fail)
    with pytest.raises(OSError): a.run(write=True)
    assert before == {p.name: p.read_bytes() for p in directory.iterdir()}


def test_source_symlink_escape_is_rejected(tmp_path, tiny):
    directory = write_fixture(tmp_path / 'processed', tiny); path = directory / 'dataset.json'
    outside = tmp_path / 'outside.json'; outside.write_bytes(path.read_bytes()); path.unlink()
    try: path.symlink_to(outside)
    except OSError: pytest.skip('Windows symlink privilege unavailable')
    with pytest.raises(ValueError, match='escapes'): a.current_report(directory)
