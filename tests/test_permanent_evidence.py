"""Fixed-policy and cached-artifact source identity regressions."""
from copy import deepcopy
import json
import pytest
from backend import permanent_evidence as evidence
from backend import permanent_service as service


@pytest.mark.parametrize('change', ['engine', 'bool-weight', 'profile-mode', 'profile-date', 'shared-beds', 'target'])
def test_fixed_policy_rejects_semantic_drift(tmp_path, monkeypatch, change):
    policy = deepcopy(evidence.load_policy())
    if change == 'engine': policy['transitEngine'] = 'ego'
    if change == 'bool-weight': policy['profileWeights']['car'] = True
    if change == 'profile-mode': policy['profileDetails']['car']['mode'] = 'transit'
    if change == 'profile-date': policy['profileDetails']['weekday-0800']['departure'] = '2026-10-27T08:05:00+03:00'
    if change == 'shared-beds': policy['permanence']['sharedBeds'] = False
    if change == 'target': policy['coverageTarget'] = 94.9
    path = tmp_path / 'policy.json'; path.write_text(json.dumps(policy), encoding='utf8')
    monkeypatch.setattr(evidence, 'POLICY_FILE', path)
    with pytest.raises(ValueError): evidence.load_policy()


def test_all_direct_model_dependencies_are_bound():
    assert 'backend/joint_solver.py' in evidence.MODEL_FILES
    assert 'scripts/verify_permanent.py' in evidence.MODEL_FILES
    assert 'backend/permanent_service.py' in evidence.MODEL_FILES


@pytest.mark.parametrize('change', ['changed', 'missing'])
def test_cached_plan_rejects_changed_or_missing_motis_matrix(tmp_path, monkeypatch, change):
    import scripts.verify_permanent as verifier
    for profile in service.motis.PROFILES:
        (tmp_path / (profile + '-matrix.npz')).write_bytes(b'original')
    matrix = tmp_path / 'sunday-1000-matrix.npz'
    path = tmp_path / 'plan.json'; policy = tmp_path / 'policy.json'; policy.write_text('{}')
    result = {'identity': {'transitPackageId': 'p'}}
    result['planId'] = evidence.plan_id(result)
    path.write_text(json.dumps(result))
    for key, val in {'PLAN_FILE': path, 'POLICY_FILE': policy, 'MODEL_FILES': (), 'SOURCE_FILES': {}}.items():
        monkeypatch.setattr(service, key, val)
    monkeypatch.setattr(service.motis, 'MATRIX_DIR', tmp_path)
    monkeypatch.setattr(service.motis, 'manifest', lambda: {'packageId': 'p'})
    monkeypatch.setattr(service, 'inputs', lambda: ({}, {}, {}))
    monkeypatch.setattr(service, 'load_policy', lambda: {})
    monkeypatch.setattr(verifier, 'audit', lambda *args: {})
    def current():
        if matrix.read_bytes() != b'original': raise ValueError('MOTIS matrix checksum mismatch')
        return {'transitPackageId': 'p'}
    monkeypatch.setattr(service, 'current_identity', current)
    service._read.cache_clear()
    assert service.read_plan() == result
    if change == 'changed': matrix.write_bytes(b'changed matrix')
    else: matrix.unlink()
    with pytest.raises((ValueError, OSError)): service.read_plan()
    service._read.cache_clear()
