from fastapi.testclient import TestClient
from backend.main import app, reconstruct

client = TestClient(app)

def test_invalid_parameters_are_rejected():
    assert client.post('/api/solve', json={'mode':'flying'}).status_code == 422
    assert client.post('/api/solve', json={'threshold':0}).status_code == 422
    assert client.post('/api/solve', json={'coverageTarget':101}).status_code == 422
    assert client.post('/api/solve', json={'trafficFactor':0}).status_code == 422
    assert client.post('/api/solve', json={'transitProfile':'holiday-1000'}).status_code == 422
    for key, value in [('bedOccupancy', 100), ('contactsPerDoctor', 0), ('hospitalLimit', 0), ('operatingCostMultiplier', 0), ('demandMultiplier', 0), ('costTolerance', 31)]:
        assert client.post('/api/solve', json={key:value}).status_code == 422

def test_route_reconstruction_rejects_unreachable_and_keeps_direction():
    assert reconstruct([-9999,0,1],0,2) == [0,1,2]
    assert reconstruct([-9999,0,1],2,0) == []
    assert reconstruct([-9999],0,0) == [0]

def test_layer_path_is_allowlisted():
    assert client.get('/api/layers/secrets').status_code == 422

def test_health():
    assert client.get('/api/health').status_code == 200
