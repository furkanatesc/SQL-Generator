from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_get_api_v1_returns_canonical_envelope():
    resp = client.get("/api/v1")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"status", "data", "meta"}
    assert body["status"] == "success"
    assert body["meta"] is None


def test_get_api_v1_data_is_contract_descriptor():
    from app.api.contract import contract_descriptor
    resp = client.get("/api/v1")
    assert resp.json()["data"] == contract_descriptor()


def test_get_api_v1_is_public_no_api_key_required():
    # no X-API-Key header supplied; discovery endpoint must be reachable
    resp = client.get("/api/v1")
    assert resp.status_code == 200


def test_get_api_v1_emits_request_id_header():
    resp = client.get("/api/v1")
    assert resp.headers.get("X-Request-ID")
