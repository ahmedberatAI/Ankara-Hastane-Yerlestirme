"""Endpoint attribution arithmetic and current-source publication gates; no solver."""
from copy import deepcopy
import json
import math
import os
from pathlib import Path

import pytest
from scripts import audit_access_connectors as a
from test_joint_plan_audit import tiny, write_fixture
from test_joint_travel_audit import portable, blob


def arithmetic_fixture():
    data = {'metadata': {'provincePopulation': 100, 'matchedPopulation': 98, 'unlocatedPopulation': 2},
            'demands': [{'population': 50, 'snapMeters': 75}, {'population': 48, 'snapMeters': 0}],
            'candidates': [{'id': 'a', 'accessMeters': 250}, {'id': 'b', 'accessMeters': 500}]}
    allocations = [{'demandIndex': 0, 'candidateIndex': 0, 'population': 50, 'minutes': 5},
                   {'demandIndex': 1, 'candidateIndex': 1, 'population': 45, 'minutes': 10}]
    certificate = {'transitPackageId': 'p', 'planningVersion': 'h', 'plan': {'hospitalCount': 2,
        'selected': [{'candidateIndex': 0, 'id': 'a'}, {'candidateIndex': 1, 'id': 'b'}],
        'profiles': [dict(profile=p, coveredPopulation=95, meanMinutes=700/95,
                          allocations=deepcopy(allocations)) for p in a.travel.PROFILES]}}
    return data, certificate


def test_manual_unequal_weights_and_ratio_of_sums_with_unlocated_denominator():
    result = a.compute(*arithmetic_fixture()); p = result['profiles'][0]
    assert result['population'] == dict(provincePopulation=100, locatedPopulation=98,
        unlocatedPopulation=2, targetServedPopulationEquivalentPerProfile=95)
    assert p['servedEquivalent'] == 95
    assert p['meanOriginMinutes'] == 50/95
    assert p['meanHospitalMinutes'] == pytest.approx((50*250+45*500)/75/95)
    assert p['meanEndpointMinutes'] == pytest.approx((50*325+45*500)/75/95)
    assert p['shareOfPersonMinutesPercent'] == pytest.approx((50*325+45*500)/75/700*100)
    individual_ratio_mean = (50*(325/75/5)+45*(500/75/10))/95*100
    assert abs(p['shareOfPersonMinutesPercent']-individual_ratio_mean) > 1
    assert set(p) == {'profile','servedEquivalent','meanOriginMinutes','meanHospitalMinutes',
                      'meanEndpointMinutes','shareOfPersonMinutesPercent','totalMeanMinutes'}
    assert 'not independently verified walkable paths' in result['definitions']['scope']


@pytest.mark.parametrize('value', [math.nan, math.inf, -1e-30, True])
@pytest.mark.parametrize('field', ['snap', 'site', 'flow'])
def test_finite_nonnegative_units_and_strict_positive_flow(value, field):
    data, cert = arithmetic_fixture()
    if field == 'snap': data['demands'][0]['snapMeters'] = value
    elif field == 'site': data['candidates'][0]['accessMeters'] = value
    else: cert['plan']['profiles'][0]['allocations'][0]['population'] = value
    with pytest.raises(ValueError): a.compute(data, cert)


@pytest.mark.parametrize('mutation', ['zero_flow', 'duplicate', 'mean', 'unlocated', 'profile', 'closed', 'greater_total'])
def test_no_silent_dropping_relabelling_or_counterfactual_clipping(mutation):
    data, cert = arithmetic_fixture(); row = cert['plan']['profiles'][0]
    if mutation == 'zero_flow': row['allocations'][0]['population'] = 0
    if mutation == 'duplicate': row['allocations'].append(row['allocations'][0])
    if mutation == 'mean': row['meanMinutes'] += .01
    if mutation == 'unlocated': data['metadata']['unlocatedPopulation'] = 3
    if mutation == 'profile': row['profile'] = 'unobserved'
    if mutation == 'closed': cert['plan']['selected'].pop(); cert['plan']['hospitalCount'] = 1
    if mutation == 'greater_total': data['candidates'][0]['accessMeters'] = 1000
    with pytest.raises(ValueError): a.compute(data, cert)


@pytest.fixture
def cli(tmp_path, tiny, monkeypatch):
    data = tiny[1]
    data['metadata'].update(matchedPopulation=200, unlocatedPopulation=0)
    for i, demand in enumerate(data['demands']): demand['snapMeters'] = 75*(i+1)
    for candidate in data['candidates']: candidate['accessMeters'] = 300
    directory = write_fixture(tmp_path/'data/processed', tiny)
    for name in set(a.travel.MODEL_FILES) | {a.SELF, *a.SEMANTIC_FILES}:
        target = tmp_path/name; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((a.ROOT/name).read_bytes())
    source = a.load_json((directory/'joint-plan.json').read_bytes())
    changed = (source, *tiny[1:5], source['sourceSHA256'])
    args = portable(changed, a.travel.code_hashes(tmp_path), a.sha256((directory/'joint-plan.json').read_bytes()))
    (directory/'travel-plan.json').write_bytes(blob(args['travel_plan']))
    (directory/'travel-proof.json').write_bytes(blob(args['proof']))
    calls = []
    monkeypatch.setattr(a.travel, 'ROOT', tmp_path)
    monkeypatch.setattr(a.travel, 'check_package', lambda root: 'p')
    monkeypatch.setattr(a, 'check_package', lambda root: calls.append(root) or 'p')
    a.travel.run(write=True)
    return tmp_path, directory, calls


def test_complete_independent_tiny_audit_safe_write_and_readonly(cli):
    root, directory, _ = cli
    before = {p.name:p.read_bytes() for p in directory.iterdir()}
    result = a.run(write=True, root=root)
    assert len(result['sourceSHA256']) == 11
    assert len(result['semanticCodeSHA256']) == 2
    assert result['travelPlanSHA256'] == a.sha256(before['travel-plan.json'])
    assert result['sourceTravelSummarySHA256'] == a.sha256(before['travel-summary.json'])
    assert all((directory/name).read_bytes() == content for name,content in before.items())
    snapshot = {p.name:p.read_bytes() for p in directory.iterdir()}
    assert a.run(root=root) == result
    assert snapshot == {p.name:p.read_bytes() for p in directory.iterdir()}
    assert result['profiles'][0]['meanEndpointMinutes'] == pytest.approx((100*5+90*6)/190)


def test_default_missing_summary_writes_nothing(cli):
    root, directory, _ = cli; before = set(directory.iterdir())
    with pytest.raises(FileNotFoundError): a.run(root=root)
    assert set(directory.iterdir()) == before


@pytest.mark.parametrize('name', (*a.travel.FILES, 'travel-summary.json'))
def test_current_source_mutation_rejected(cli, name):
    root, directory, _ = cli; a.run(write=True, root=root)
    with (directory/name).open('ab') as stream: stream.write(b' ')
    with pytest.raises(ValueError): a.run(root=root)


@pytest.mark.parametrize('name', (a.SELF, *a.SEMANTIC_FILES, 'backend/joint_model.py'))
def test_code_changes_not_reused_as_same_summary(cli, name):
    root, directory, _ = cli; a.run(write=True, root=root)
    with (root/name).open('ab') as stream: stream.write(b' ')
    with pytest.raises(ValueError): a.run(root=root)


@pytest.mark.parametrize('target', ['dataset.json', 'travel-summary.json', 'semantic', 'self', 'published_model'])
def test_change_during_arithmetic_prevents_publication(cli, monkeypatch, target):
    root, directory, _ = cli; original = a.compute
    def changed(*args):
        result = original(*args)
        path = (root/a.SEMANTIC_FILES[0] if target == 'semantic' else root/a.SELF if target == 'self'
                else root/'backend/joint_model.py' if target == 'published_model' else directory/target)
        with path.open('ab') as stream: stream.write(b' ')
        return result
    monkeypatch.setattr(a, 'compute', changed)
    with pytest.raises(ValueError): a.run(write=True, root=root)
    assert not (directory/a.OUTPUT).exists()


def test_saved_statistics_or_scope_tamper_fails_readonly(cli):
    root, directory, _ = cli; result = a.run(write=True, root=root)
    result['definitions']['scope'] = 'All routes are independently validated'
    (directory/a.OUTPUT).write_bytes(blob(result))
    with pytest.raises(ValueError, match='summary differs'): a.run(root=root)


def test_atomic_replace_does_not_follow_hardlink_or_touch_unowned_temp(cli):
    root, directory, _ = cli; source = directory/'travel-plan.json'; before = source.read_bytes()
    os.link(source, directory/a.OUTPUT)
    marker = directory/'.access-connector-keep.json.tmp'; marker.write_text('keep')
    a.run(write=True, root=root)
    assert source.read_bytes() == before and marker.read_text() == 'keep'


def test_failed_replace_cleans_owned_temporary_only(cli, monkeypatch):
    root, directory, _ = cli
    marker = directory/'.access-connector-keep.json.tmp'; marker.write_text('keep')
    before = {p.name:p.read_bytes() for p in directory.iterdir()}
    monkeypatch.setattr(Path, 'replace', lambda *args: (_ for _ in ()).throw(OSError('synthetic failure')))
    with pytest.raises(OSError): a.run(write=True, root=root)
    assert before == {p.name:p.read_bytes() for p in directory.iterdir()}


def test_symlink_output_escape_rejected(cli, tmp_path):
    root, directory, _ = cli; external = root/'elsewhere.json'; external.write_text('unchanged')
    try: (directory/a.OUTPUT).symlink_to(external)
    except OSError: pytest.skip('OS does not grant symlink creation')
    with pytest.raises(ValueError, match='Redirected output'): a.run(write=True, root=root)
    assert external.read_text() == 'unchanged'
