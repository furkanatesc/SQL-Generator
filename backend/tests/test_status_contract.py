import os
import json
import pytest
from fastapi.testclient import TestClient
from app.main import app, verify_api_key

client = TestClient(app)

def get_expected_status(key: str) -> int:
    snapshot_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "contracts",
        "status_contract_snapshot.json"
    )
    with open(snapshot_path, "r", encoding="utf-8") as f:
        snapshot = json.load(f)
    return snapshot[key]

def test_health_status():
    expected = get_expected_status("health")
    res = client.get("/health")
    assert res.status_code == expected, f"Expected health status {expected}, got {res.status_code}"

def test_missing_api_key_status():
    app.dependency_overrides.clear()
    expected = get_expected_status("missing_api_key")
    res = client.get("/api/jobs")
    assert res.status_code == expected, f"Expected missing API key status {expected}, got {res.status_code}"

def test_invalid_api_key_status():
    app.dependency_overrides.clear()
    expected = get_expected_status("invalid_api_key")
    res = client.get("/api/jobs", headers={"X-API-Key": "invalid_api_key_value"})
    assert res.status_code == expected, f"Expected invalid API key status {expected}, got {res.status_code}"

def test_missing_resource_status():
    # Bypass auth using dependency overrides
    app.dependency_overrides[verify_api_key] = lambda: True
    try:
        expected = get_expected_status("missing_resource")
        res = client.get("/api/jobs/nonexistent-job-uuid-12345")
        assert res.status_code == expected, f"Expected missing resource status {expected}, got {res.status_code}"
    finally:
        app.dependency_overrides.clear()

def test_validation_error_status():
    # Bypass auth using dependency overrides
    app.dependency_overrides[verify_api_key] = lambda: True
    try:
        expected = get_expected_status("validation_error")
        res = client.post("/api/jobs/without-file", json={})
        assert res.status_code == expected, f"Expected validation error status {expected}, got {res.status_code}"
    finally:
        app.dependency_overrides.clear()
