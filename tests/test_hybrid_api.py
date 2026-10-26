"""Provider isolation and separate-mode API regressions; no external calls."""
from copy import deepcopy
import numpy as np
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

import backend.main as api


@pytest.fixture(autouse=True)
def clear_caches():
    clear = [api.legacy_matrix.cache_clear, api.count_bound.cache_clear, api._cached_solve.cache_clear]
    for fn in clear:
        fn()
    yield
    for fn in clear:
        fn()


@pytest.fixture(autouse=True)
def fake_live_identity(monkeypatch):
    import backend.motis_runtime as runtime
    import backend.motis as motis
    monkeypatch.setattr(runtime, 'runtime_identity', lambda: {'pid': 1, 'processImportVerified': True})
    monkeypatch.setattr(motis, 'evidence', lambda profile: {'packageId': 'motis-test'})


@pytest.fixture
def small_data(monkeypatch):
    data = {'metadata': {'provincePopulation': 100},
            'demands': [{'id': 'd', 'name': 'Mahalle', 'population': 100,
                         'districtId': 'x', 'node': 0, 'snapMeters': 75, 'lon': 32., 'lat': 39.}],
            'candidates': [{'id': 'c', 'name': 'Aday', 'node': 1, 'accessMeters': 150,
                            'lon': 32.1, 'lat': 39.1, 'entryLon': 32.09, 'entryLat': 39.09,
                            'footprintRadiusMeters': 80}], 'hospitals': [],
            'districts': [{'id': 'x', 'population': 100}]}
    monkeypatch.setattr(api, 'dataset', lambda: deepcopy(data))
    monkeypatch.setattr(api, 'coordinates', lambda: np.array([[32., 39.], [32.09, 39.09]]))
    return data


@pytest.mark.parametrize('params', [
    {'carWeight': 50}, {'carWeight': 101}, {'carWeight': float('nan')},
    {'transitThreshold': 9}, {'transitEngine': 'google'},
])
def test_invalid_hybrid_preferences_are_rejected(params):
    with pytest.raises(ValidationError):
        api.Scenario(mode='hybrid', **params)


def test_hybrid_never_forms_a_blended_travel_matrix(monkeypatch, small_data):
    calls = []
    def fake_matrix(mode, profile, engine):
        calls.append((mode, engine))
        return np.array([[10. if mode == 'car' else 40.]])
    monkeypatch.setattr(api, 'matrix', fake_matrix)
    s = api.Scenario(mode='hybrid', transitEngine='motis', threshold=30, transitThreshold=45)
    with pytest.raises(ValueError, match='iki ayrı'):
        api.travel_times(s)
    assert api.travel_times(s, 'car')[0, 0] == 10
    assert api.travel_times(s, 'transit')[0, 0] == 40
    assert calls == [('car', 'motis'), ('transit', 'motis')]


def test_hybrid_car_traffic_changes_only_drive_component(monkeypatch, small_data):
    monkeypatch.setattr(api, 'matrix', lambda *args: np.array([[16.]]))
    s = api.Scenario(mode='hybrid', trafficFactor=2)
    # 1 min origin + 2 min entry + 3 min overhead remain unchanged.
    assert api.travel_times(s, 'car')[0, 0] == 26
    assert api.travel_times(s, 'transit')[0, 0] == 16


def test_hybrid_route_requires_an_explicit_display_mode(small_data):
    response = TestClient(api.app).post('/api/route', json={
        'mode': 'hybrid', 'demandId': 'd', 'candidateId': 'c'})
    assert response.status_code == 422
    assert 'ulaşım türünü seçin' in response.json()['detail']


def test_motis_route_rejects_mismatched_matrix_instead_of_switching_provider(monkeypatch, small_data):
    import backend.motis as motis
    monkeypatch.setattr(api, 'travel_times', lambda *args: np.array([[42.]]))
    monkeypatch.setattr(motis, 'plan', lambda *args, **kwargs: {'minutes': 41., 'legs': [], 'boardings': [], 'evidence': {'packageId': 'motis-test'}})
    response = TestClient(api.app).post('/api/route', json={
        'mode': 'hybrid', 'routeMode': 'transit', 'transitEngine': 'motis',
        'demandId': 'd', 'candidateId': 'c'})
    assert response.status_code == 409
    assert 'eşleşmiyor' in response.json()['detail']


def test_motis_route_passes_connector_times_once_and_preserves_leg_geometry(monkeypatch, small_data):
    import backend.motis as motis
    calls = []
    def fake_plan(*args, **kwargs):
        calls.append((args, kwargs))
        return {'minutes': 42., 'legs': [{'kind': 'ride', 'label': '206',
                 'coordinates': [[32.01, 39.01], [32.08, 39.08]]}], 'boardings': [], 'evidence': {'packageId': 'motis-test'}}
    monkeypatch.setattr(api, 'travel_times', lambda *args: np.array([[42.]]))
    monkeypatch.setattr(motis, 'plan', fake_plan)
    response = TestClient(api.app).post('/api/route', json={
        'mode': 'hybrid', 'routeMode': 'transit', 'transitEngine': 'motis',
        'demandId': 'd', 'candidateId': 'c'})
    assert response.status_code == 200
    body = response.json()
    assert body['minutes'] == 42
    assert [p['kind'] for p in body['legs']] == ['connector', 'ride', 'connector']
    assert body['legs'][1]['coordinates'] == [[32.01, 39.01], [32.08, 39.08]]
    assert calls[0][0][:2] == ((39., 32.), (39.09, 32.09))
    assert calls[0][1] == {'origin_access_meters': 75, 'destination_access_meters': 150}


def test_no_paid_or_legacy_fallback_when_motis_matrix_is_unavailable(monkeypatch):
    import backend.motis as motis
    def unavailable(profile):
        raise RuntimeError('Eksik doğrulanmış matris')
    monkeypatch.setattr(motis, 'load_matrix', unavailable)
    with pytest.raises(HTTPException) as exc:
        api.matrix('transit', 'weekday-1000', 'motis')
    assert exc.value.status_code == 409
    assert 'Eksik doğrulanmış matris' in exc.value.detail


def test_motis_matrix_revalidates_after_a_previous_success(monkeypatch):
    import backend.motis as motis
    calls = []
    def changed_matrix(profile):
        calls.append(profile)
        if len(calls) > 1:
            raise ValueError('Matrix checksum mismatch')
        return np.array([[20.]])
    monkeypatch.setattr(motis, 'load_matrix', changed_matrix)
    assert api.matrix('transit', engine='motis')[0, 0] == 20
    with pytest.raises(HTTPException) as exc:
        api.matrix('transit', engine='motis')
    assert exc.value.status_code == 409 and len(calls) == 2


@pytest.mark.parametrize('mode', ['transit', 'hybrid'])
def test_sparse_motis_failure_stays_inconclusive_without_global_certificate(monkeypatch, small_data, mode):
    import backend.motis as motis
    import backend.hybrid as hybrid
    monkeypatch.setattr(motis, 'evidence', lambda profile: {
        'engine': 'motis', 'packageId': 'motis-test', 'existingComparisonAvailable': False})
    monkeypatch.setattr(api, 'travel_times', lambda *args: np.array([[20.]]))
    monkeypatch.setattr(api, 'health_planning', lambda: {})
    monkeypatch.setattr(api, 'site_conflicts', lambda: [])
    def restricted_failure(*args, **kwargs):
        return {'status': 'infeasible', 'selectedIndices': [], 'reason': 'No feasible queried edges'}
    monkeypatch.setattr(hybrid, 'solve_hybrid', restricted_failure)
    monkeypatch.setattr(api, 'solve_capacity', restricted_failure)
    def no_global_certificate(*args):
        raise AssertionError('Unqueried MOTIS edges cannot certify all-candidate infeasibility')
    monkeypatch.setattr(api, 'count_bound', no_global_certificate)
    response = TestClient(api.app).post('/api/solve', json={
        'mode': mode, 'transitEngine': 'motis', 'hospitalLimit': 91})
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'inconclusive'
    assert body['restrictedModelStatus'] == 'infeasible'
    assert 'geographicCertificate' not in body and 'selected' not in body
    assert body['scenario']['coverageTarget'] == 95
    assert body['scenario']['districtFloor'] == 80


def test_legacy_hybrid_failure_without_allocations_is_not_a_server_error(monkeypatch, small_data):
    import backend.hybrid as hybrid
    data = deepcopy(small_data)
    data['metadata'].update(transitVersion='test', transitDataQuality={})
    monkeypatch.setattr(api, 'dataset', lambda: data)
    monkeypatch.setattr(api, 'travel_times', lambda *args: np.array([[20.]]))
    monkeypatch.setattr(api, 'health_planning', lambda: {})
    monkeypatch.setattr(api, 'site_conflicts', lambda: [])
    monkeypatch.setattr(hybrid, 'solve_hybrid', lambda *args, **kwargs: {
        'status': 'inconclusive', 'selectedIndices': [], 'reason': 'No checked incumbent'})
    response = TestClient(api.app).post('/api/solve', json={'mode': 'hybrid', 'transitEngine': 'ego'})
    assert response.status_code == 200
    assert response.json()['status'] == 'inconclusive'


def test_solve_cache_tracks_motis_package_and_revalidates_every_request(monkeypatch):
    import backend.motis as motis
    identity = {'package': 'motis-a', 'calls': 0}
    def evidence(profile):
        identity['calls'] += 1
        if identity['package'] is None:
            raise ValueError('Corrupted input')
        return {'packageId': identity['package']}
    monkeypatch.setattr(motis, 'evidence', evidence)
    calls = []
    monkeypatch.setattr(api, '_cached_solve', lambda request, package: calls.append(package) or {'package': package})
    s = api.Scenario(mode='hybrid', transitEngine='motis').model_dump_json()
    assert api.cached_solve(s)['package'] == 'motis-a'
    identity['package'] = 'motis-b'
    assert api.cached_solve(s)['package'] == 'motis-b'
    identity['package'] = None
    with pytest.raises(HTTPException) as exc:
        api.cached_solve(s)
    assert exc.value.status_code == 409
    assert calls == ['motis-a', 'motis-b'] and identity['calls'] == 3


@pytest.mark.parametrize('changed', ['package', 'process'])
def test_motis_route_cannot_relabel_a_changed_package_or_process(monkeypatch, small_data, changed):
    import backend.motis as motis
    import backend.motis_runtime as runtime
    counter = {'package': 0, 'process': 0}
    def evidence(profile):
        counter['package'] += 1
        return {'packageId': 'new' if changed == 'package' and counter['package'] > 1 else 'old'}
    def identity():
        counter['process'] += 1
        return {'pid': 2 if changed == 'process' and counter['process'] > 1 else 1}
    monkeypatch.setattr(motis, 'evidence', evidence)
    monkeypatch.setattr(runtime, 'runtime_identity', identity)
    monkeypatch.setattr(api, 'travel_times', lambda *args: np.array([[42.]]))
    monkeypatch.setattr(motis, 'plan', lambda *args, **kwargs: {
        'minutes': 42, 'legs': [], 'boardings': [], 'evidence': {'packageId': 'old'}})
    response = TestClient(api.app).post('/api/route', json={
        'mode': 'hybrid', 'routeMode': 'transit', 'transitEngine': 'motis',
        'demandId': 'd', 'candidateId': 'c'})
    assert response.status_code == 409
    assert 'değişti' in response.json()['detail']


def test_motis_route_rejects_an_assignment_from_a_previous_result_package(monkeypatch, small_data):
    import backend.motis as motis
    monkeypatch.setattr(motis, 'evidence', lambda profile: {'packageId': 'new'})
    def should_not_query(*args, **kwargs):
        pytest.fail('An old result must be rejected before a new route is queried')
    monkeypatch.setattr(motis, 'plan', should_not_query)
    response = TestClient(api.app).post('/api/route', json={
        'mode': 'hybrid', 'routeMode': 'transit', 'transitEngine': 'motis',
        'routingPackageId': 'old', 'demandId': 'd', 'candidateId': 'c'})
    assert response.status_code == 409
    assert 'eski MOTIS' in response.json()['detail']
