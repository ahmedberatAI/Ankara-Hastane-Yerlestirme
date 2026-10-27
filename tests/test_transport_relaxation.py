"""Regression tests for the no-solve, source-bound witness audit."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import math

import numpy as np
import pytest
from pyproj import Transformer

from scripts import audit_transport_relaxation as w

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def source():
    return [json.loads((ROOT / 'data/processed' / f).read_text(encoding='utf8')) for f in w.FILES]


def test_actual_current_plan_without_hardcoded_resource_totals(source):
    data, health, car, transit = source
    r = w.audit(*source)
    assert r['witnessFound'] and not r['solverRun']
    assert r['hospitalCount'] == car['hospitalCount'] <= r['hospitalLimit']
    assert r['beds'] == car['capacity']['totalBeds']
    assert r['doctors'] == car['capacity']['totalDoctors']
    assert len({p['allocationSHA256'] for p in r['profiles']}) == 1
    assert r['annualDemandCountedOnce'] and r['resourcesSharedAcrossProfiles']
    assert r['annualEquivalentCostTRY'] == pytest.approx(car['capacity']['annualEquivalentCostTRY'])
    assert 'actual EGO' in r['scope']


def test_packaged_report_replays_on_current_platform():
    directory = ROOT / 'data/processed'
    saved = json.loads((directory / 'transport-relaxation-results.json').read_bytes())
    assert w.compare_report(saved, directory)


def test_submicrometre_projection_noise_does_not_change_report(source, monkeypatch):
    baseline = w.audit(*source)
    original = w.Transformer.from_crs(4326, 32636, always_xy=True)

    class NoisyProjection:
        def transform(self, lon, lat):
            x, y = original.transform(lon, lat)
            return x + (1e-8 if lon < 33 else -1e-8), y

    monkeypatch.setattr(w.Transformer, 'from_crs', lambda *args, **kwargs: NoisyProjection())
    assert w.digest(w.audit(*source)) == w.digest(baseline)


def test_witness_not_found_is_not_infeasibility(source):
    r = w.audit(*source, hospital_limit=source[2]['hospitalCount'] - 1)
    assert not r['witnessFound'] and r['status'] == 'no_witness_from_saved_plan'
    copied = deepcopy(source)
    copied[3]['capacity']['budgetLimitTRY'] = source[2]['capacity']['annualEquivalentCostTRY'] - 100
    r = w.audit(*copied)
    assert not r['witnessFound'] and not r['withinOriginalTransitBudget']
    assert 'no conclusion of infeasibility' in r['noWitnessInterpretation']


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -float('inf'), True, False, '12'])
@pytest.mark.parametrize('field', ['population', 'doctors', 'radius', 'gross_area', 'cost', 'budget', 'rate', 'allocation'])
def test_consumed_numeric_values_cannot_hide_nan_or_boolean(source, bad, field):
    d, h, c, t = deepcopy(source)
    if field == 'population': d['metadata']['provincePopulation'] = bad
    elif field == 'doctors': c['selected'][0]['doctors'] = bad
    elif field == 'radius': c['selected'][0]['footprintRadiusMeters'] = bad
    elif field == 'gross_area': c['selected'][0]['grossAreaM2'] = bad
    elif field == 'cost': c['capacity']['annualEquivalentCostTRY'] = bad
    elif field == 'budget': t['capacity']['budgetLimitTRY'] = bad
    elif field == 'rate': h['rates']['contactsPerResident'] = bad
    elif field == 'allocation': next(a for a in c['assignments'] if a['allocations'])['allocations'][0]['population'] = bad
    with pytest.raises(ValueError): w.audit(d, h, c, t)


@pytest.mark.parametrize('mutation', ['physician_parameter', 'demand_parameter', 'occupancy_parameter',
    'operating_parameter', 'coverage_parameter', 'district_parameter', 'health_version', 'package',
    'missing_district', 'duplicate_district', 'missing_assignment', 'demand_identity', 'site_identity',
    'candidate_identity', 'duplicate_flow', 'closed_site', 'beds', 'capacity', 'plot_overlap', 'materials_twice'])
def test_scope_identity_flow_capacity_and_single_bill_guards(source, mutation):
    d, h, c, t = deepcopy(source)
    if mutation.endswith('_parameter'):
        field = {'physician_parameter': 'contactsPerDoctor', 'demand_parameter': 'demandMultiplier',
                 'occupancy_parameter': 'bedOccupancy', 'operating_parameter': 'operatingCostMultiplier',
                 'coverage_parameter': 'coverageTarget', 'district_parameter': 'districtFloor'}[mutation]
        c['scenario'][field] += 1
    elif mutation == 'health_version': c['capacity']['planningVersion'] = 'other'
    elif mutation == 'package': t['metadata']['transitPackageId'] = 'other'
    elif mutation == 'missing_district': d['districts'].pop()
    elif mutation == 'duplicate_district': d['districts'].append(deepcopy(d['districts'][0]))
    elif mutation == 'missing_assignment': c['assignments'].pop()
    elif mutation == 'demand_identity': c['assignments'][0]['demandId'] = 'other'
    elif mutation == 'site_identity': c['selected'][0]['id'] = 'other'
    elif mutation == 'candidate_identity': d['candidates'][0]['id'] = d['candidates'][1]['id']
    elif mutation == 'duplicate_flow':
        a = next(a for a in c['assignments'] if a['allocations'])
        a['allocations'].append(deepcopy(a['allocations'][0]))
    elif mutation == 'closed_site':
        a = next(a for a in c['assignments'] if a['allocations'])['allocations'][0]
        a['candidateIndex'] = next(j for j in range(len(d['candidates'])) if j not in c['selectedIndices'])
    elif mutation == 'beds': c['selected'][0]['beds'] += 1
    elif mutation == 'capacity': c['selected'][0]['doctors'] = 0
    elif mutation == 'plot_overlap':
        a, b = c['selected'][:2]
        for key in ('lon', 'lat'):
            b[key] = a[key]
            d['candidates'][b['candidateIndex']][key] = a[key]
    elif mutation == 'materials_twice':
        r = w.audit(*source)
        c['capacity']['annualEquivalentCostTRY'] += float(r['decimalAnnualMaterialCostTRY'])
        c['capacity']['annualOperatingCostTRY'] += float(r['decimalAnnualMaterialCostTRY'])
    with pytest.raises(ValueError): w.audit(d, h, c, t)


def test_read_only_report_comparison_rejects_staleness_and_tampering(source, tmp_path):
    for name, value in zip(w.FILES, source):
        (tmp_path / name).write_text(json.dumps(value, ensure_ascii=False), encoding='utf8')
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    r = w.current_report(tmp_path)
    assert w.compare_report(r, tmp_path)
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    bad = deepcopy(r); bad['hospitalCount'] += 1
    with pytest.raises(ValueError): w.compare_report(bad, tmp_path)
    # Even a source change irrelevant to arithmetic invalidates the stored hash.
    d = deepcopy(source[0]); d['metadata']['auditTestNote'] = 'changed'
    (tmp_path / w.FILES[0]).write_text(json.dumps(d, ensure_ascii=False), encoding='utf8')
    with pytest.raises(ValueError): w.compare_report(r, tmp_path)


@pytest.mark.parametrize('field,value', [('witnessFound', 1), ('solverRun', 0),
    ('annualDemandCountedOnce', 1), ('resourcesSharedAcrossProfiles', 1),
    ('hospitalCount', 46.0), ('format', True), ('annualEquivalentCostTRY', float('nan'))])
def test_canonical_report_comparison_distinguishes_boolean_and_numeric_types(source, tmp_path, field, value):
    for name, payload in zip(w.FILES, source):
        (tmp_path / name).write_text(json.dumps(payload, ensure_ascii=False), encoding='utf8')
    report = w.current_report(tmp_path)
    if field == 'hospitalCount': value = float(report['hospitalCount'])
    report[field] = value
    with pytest.raises(ValueError): w.compare_report(report, tmp_path)


def test_unused_open_site_is_kept_in_count_area_resources_and_cost(source):
    d, h, c, t = deepcopy(source)
    transform = Transformer.from_crs(4326, 32636, always_xy=True)
    xy = np.array([transform.transform(s['lon'], s['lat']) for s in c['selected']])
    radii = np.array([s['footprintRadiusMeters'] for s in c['selected']])
    design, eco = h['design'], h['economics']
    docs = design['minimumDoctorsPerSite']; module = h['templates'][0]
    area = module['grossAreaM2'] + docs * design['areaPerDoctorM2']
    for j, base in enumerate(d['candidates']):
        if j in c['selectedIndices']: continue
        if area > math.pi * base['footprintRadiusMeters'] ** 2 * design['maxFloors']: continue
        if np.all(np.linalg.norm(xy - transform.transform(base['lon'], base['lat']), axis=1) >= radii + base['footprintRadiusMeters']): break
    else: pytest.fail('No independent unused plot available for fixture')
    c['selected'].append(dict(base, candidateIndex=j, templateId=module['id'], beds=module['beds'],
                              doctors=docs, grossAreaM2=area, assignedPopulation=0.))
    c['selectedIndices'].append(j); c['hospitalCount'] += 1
    cap = c['capacity']; cap['totalBeds'] += module['beds']; cap['totalDoctors'] += docs
    construction = area * eco['buildingUnitCostTRY']
    operating = t['scenario']['operatingCostMultiplier'] * (eco['annualFixedSiteCostTRY'] +
                 module['beds'] * eco['annualBedSupportCostTRY'] + docs * eco['annualDoctorCostTRY'])
    rate = eco['realDiscountRate']; years = eco['horizonYears']
    annuity = rate / (1 - (1 + rate) ** -years) if rate else 1 / years
    cap['constructionCostTRY'] += construction
    cap['annualOperatingCostTRY'] += operating
    cap['annualEquivalentCostTRY'] += construction * annuity + operating
    report = w.audit(d, h, c, t)
    assert report['hospitalCount'] == source[2]['hospitalCount'] + 1
    assert report['beds'] == cap['totalBeds'] and report['doctors'] == cap['totalDoctors']
    assert report['annualEquivalentCostTRY'] == pytest.approx(cap['annualEquivalentCostTRY'])
    assert report['profiles'][0]['allocationCount'] == w.audit(*source)['profiles'][0]['allocationCount']


def test_source_filename_cannot_resolve_outside_directory(source, tmp_path):
    outside = tmp_path / 'outside.json'
    outside.write_text(json.dumps(source[0], ensure_ascii=False), encoding='utf8')
    directory = tmp_path / 'processed'; directory.mkdir()
    try:
        (directory / w.FILES[0]).symlink_to(outside)
    except OSError:
        pytest.skip('OS does not permit creating a symlink in this session')
    with pytest.raises(ValueError, match='escapes'):
        w.current_report(directory)


@pytest.fixture
def cli_workspace(source, tmp_path, monkeypatch):
    directory = tmp_path / 'data/processed'; directory.mkdir(parents=True)
    for name, value in zip(w.FILES, source):
        (directory / name).write_text(json.dumps(value, ensure_ascii=False), encoding='utf8')
    monkeypatch.setattr(w, 'ROOT', tmp_path)
    calls = []
    def package(root):
        assert root == tmp_path
        calls.append(root)
        return source[0]['metadata']['transitPackageId']
    monkeypatch.setattr(w, 'check_package', package)
    return directory, calls


def test_cli_defaults_read_only_and_requires_explicit_write(cli_workspace):
    directory, calls = cli_workspace
    output = directory / 'transport-relaxation-results.json'
    with pytest.raises(FileNotFoundError): w.run()
    assert not output.exists()
    report = w.run(write=True)
    assert type(report['hospitalLimit']) is int and report['hospitalLimit'] == 91
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    assert w.run() == report
    assert before == {p.name: p.read_bytes() for p in directory.iterdir()}
    assert len(calls) >= 5  # Entry/exit package gates, including missing artifact attempt.


@pytest.mark.parametrize('limit', [90, 92, True, 91.0, '91'])
def test_cli_rejects_changed_or_noninteger_fixed_benchmark_limit(cli_workspace, limit):
    directory, _ = cli_workspace
    report = w.run(write=True); report['hospitalLimit'] = limit
    (directory / 'transport-relaxation-results.json').write_text(json.dumps(report), encoding='utf8')
    with pytest.raises(ValueError, match='integer 91'): w.run()


def test_cli_rejects_stale_source_and_preserves_existing_report(cli_workspace):
    directory, _ = cli_workspace
    w.run(write=True)
    output = directory / 'transport-relaxation-results.json'; before = output.read_bytes()
    path = directory / w.FILES[0]
    changed = json.loads(path.read_bytes()); changed['metadata']['unusedTestNote'] = 'changed'
    path.write_text(json.dumps(changed), encoding='utf8')
    with pytest.raises(ValueError, match='differs'): w.run()
    assert output.read_bytes() == before


def test_cli_calls_actual_package_gate_before_writing(cli_workspace, monkeypatch):
    directory, _ = cli_workspace
    def stale(root): raise AssertionError('actual package mismatch')
    monkeypatch.setattr(w, 'check_package', stale)
    with pytest.raises(AssertionError, match='actual package mismatch'): w.run(write=True)
    assert not (directory / 'transport-relaxation-results.json').exists()


def test_cli_rejects_wrong_package_and_package_change_during_audit(cli_workspace, source, monkeypatch):
    directory, _ = cli_workspace
    monkeypatch.setattr(w, 'check_package', lambda root: 'other-package')
    with pytest.raises(ValueError, match='package mismatch'): w.run(write=True)
    sequence = iter([source[0]['metadata']['transitPackageId'], 'other-package'])
    monkeypatch.setattr(w, 'check_package', lambda root: next(sequence))
    with pytest.raises(ValueError, match='package changed'): w.run(write=True)
    assert not (directory / 'transport-relaxation-results.json').exists()


def test_cli_existing_fixed_temp_hardlink_cannot_truncate_source(cli_workspace):
    directory, _ = cli_workspace
    source = directory / 'dataset.json'
    predictable = directory / 'transport-relaxation-results.json.tmp'
    os.link(source, predictable)
    before = {name: (directory / name).read_bytes() for name in w.FILES}
    w.run(write=True)
    assert before == {name: (directory / name).read_bytes() for name in w.FILES}
    assert predictable.read_bytes() == before['dataset.json']
    assert not list(directory.glob('.transport-relaxation-*.json.tmp'))
    w.run()


def test_cli_atomic_output_hardlink_replacement_preserves_source(cli_workspace):
    directory, _ = cli_workspace
    output = directory / 'transport-relaxation-results.json'
    source = directory / 'dataset.json'
    before = source.read_bytes()
    os.link(source, output)
    w.run(write=True)
    assert source.read_bytes() == before
    assert output.read_bytes() != before
    assert not os.path.samefile(source, output)


def test_cli_failed_replace_cleans_only_its_exclusive_temporary(cli_workspace, monkeypatch):
    directory, _ = cli_workspace
    w.run(write=True)
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    def fail_replace(self, target):
        raise OSError('injected atomic replace failure')
    monkeypatch.setattr(Path, 'replace', fail_replace)
    with pytest.raises(OSError, match='injected atomic replace'): w.run(write=True)
    assert before == {p.name: p.read_bytes() for p in directory.iterdir()}


def test_cli_existing_fixed_temp_symlink_cannot_follow_source(cli_workspace):
    directory, _ = cli_workspace
    source = directory / 'dataset.json'
    predictable = directory / 'transport-relaxation-results.json.tmp'
    try:
        predictable.symlink_to(source)
    except OSError:
        pytest.skip('OS does not permit creating a file symlink in this session')
    before = source.read_bytes()
    w.run(write=True)
    assert source.read_bytes() == before
    assert predictable.is_symlink() and predictable.read_bytes() == before
