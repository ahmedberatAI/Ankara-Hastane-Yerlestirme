"""The public map reads one audited plan and requests only its assigned routes."""
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
import backend.main as api
from backend.permanent_evidence import load_policy

PLAN_ID = 'permanent-' + 'a' * 64


@pytest.fixture
def record(monkeypatch):
    policy = load_policy()
    value = {'planId': PLAN_ID, 'policy': policy,
        'criticalTransitProfile': 'sunday-1000', 'selected': [{'id': 'c'}],
        'identity': {'transitPackageId': 'motis-test'},
        'profiles': {'car': {'assignments': [{'demandId': 'd', 'allocations': [
            {'candidateId': 'c', 'population': 10, 'minutes': 20}]}]},
            'sunday-1000': {'assignments': [{'demandId': 'd', 'allocations': [
                {'candidateId': 'c', 'population': 10, 'minutes': 50}]}]}}}
    monkeypatch.setattr(api, 'saved_permanent_plan', lambda: deepcopy(value))
    return value


def body(**changes):
    return {'planId': PLAN_ID, 'view': 'car', 'demandId': 'd', 'candidateId': 'c', **changes}


def test_public_get_reads_same_plan_without_optimization(monkeypatch, record):
    def forbidden(*args):
        raise AssertionError('view must never solve')
    monkeypatch.setattr(api, 'cached_solve', forbidden)
    client = TestClient(api.app)
    assert client.get('/api/permanent-plan').json() == record
    assert client.get('/api/permanent-plan?threshold=120&transitProfile=weekday-0800').json() == record
    assert client.get('/api/planning-policy').json() == record['policy']


@pytest.mark.parametrize('view,minutes,profile', [('car', 20, 'car'), ('transit', 50, 'sunday-1000')])
def test_route_uses_fixed_policy_and_coherent_profile(monkeypatch, record, view, minutes, profile):
    calls = []
    def planned(request):
        calls.append(request.model_dump())
        return {'minutes': minutes, 'legs': [], 'routeMode': request.routeMode,
            'scenario': request.model_dump(), 'evidence': {'packageId': 'motis-test'}}
    monkeypatch.setattr(api, 'route', planned)
    response = TestClient(api.app).post('/api/permanent-route', json=body(view=view))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['planId'] == PLAN_ID and result['profileId'] == profile
    assert calls[0]['threshold'] == 30 and calls[0]['transitThreshold'] == 60
    assert calls[0]['trafficFactor'] == 1 and calls[0]['transitProfile'] == 'sunday-1000'
    assert calls[0]['mode'] == 'hybrid' and calls[0]['routeMode'] == view
    assert calls[0]['transitEngine'] == 'motis' and calls[0]['routingPackageId'] == 'motis-test'


@pytest.mark.parametrize('extra', [{'threshold': 120}, {'transitProfile': 'weekday-0800'},
    {'hospitalLimit': 91}, {'demandMultiplier': .5}, {'trafficFactor': 2},
    {'transitEngine': 'ego'}, {'carWeight': 95}, {'view': 'hybrid'}, {'planId': 'old'}])
def test_route_rejects_user_planning_overrides(record, extra):
    response = TestClient(api.app).post('/api/permanent-route', json=body(**extra))
    assert response.status_code == 422


@pytest.mark.parametrize('change', ['old-plan', 'unknown-demand', 'unknown-site', 'zero-flow', 'closed-site'])
def test_route_requires_current_positive_assigned_open_site(monkeypatch, record, change):
    def forbidden(*args):
        raise AssertionError('invalid plan cannot query a live route')
    monkeypatch.setattr(api, 'route', forbidden)
    changes = {}
    if change == 'old-plan': changes['planId'] = 'permanent-' + 'b' * 64
    if change == 'unknown-demand': changes['demandId'] = 'other'
    if change == 'unknown-site': changes['candidateId'] = 'other'
    if change == 'zero-flow': record['profiles']['car']['assignments'][0]['allocations'][0]['population'] = 0
    if change == 'closed-site': record['selected'] = []
    assert TestClient(api.app).post('/api/permanent-route', json=body(**changes)).status_code in (409, 422)


@pytest.mark.parametrize('view,minutes,package', [('car', 21, 'motis-test'),
    ('car', 31, 'motis-test'), ('transit', 50, 'other'), ('transit', 61, 'motis-test')])
def test_route_rejects_unmatched_minutes_or_provider(monkeypatch, record, view, minutes, package):
    monkeypatch.setattr(api, 'route', lambda request: {'minutes': minutes, 'evidence': {'packageId': package}})
    assert TestClient(api.app).post('/api/permanent-route', json=body(view=view)).status_code == 409


def test_plan_change_during_live_route_is_rejected(monkeypatch, record):
    def planned(request):
        record['planId'] = 'permanent-' + 'b' * 64
        return {'minutes': 20}
    monkeypatch.setattr(api, 'route', planned)
    assert TestClient(api.app).post('/api/permanent-route', json=body()).status_code == 409


def test_missing_or_stale_artifact_has_no_dynamic_fallback(monkeypatch):
    import backend.permanent_service as service
    def missing():
        raise ValueError('stale identity')
    monkeypatch.setattr(service, 'read_plan', missing)
    response = TestClient(api.app).get('/api/permanent-plan')
    assert response.status_code == 409 and 'stale identity' in response.json()['detail']
