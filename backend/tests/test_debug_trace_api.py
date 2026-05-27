import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.trace.dependencies import get_trace_store
from app.trace.memory_store import InMemoryTraceStore
from app.trace.models import NL2SQLTrace

API_KEY = "test-key"

@pytest.fixture
def test_client():
    with patch("app.auth.get_config", return_value=API_KEY):
        client = TestClient(app)
        yield client

@pytest.fixture
def mock_store():
    store = InMemoryTraceStore()
    app.dependency_overrides[get_trace_store] = lambda: store
    yield store
    app.dependency_overrides.clear()

def auth_headers():
    return {"X-API-Key": API_KEY}

def test_debug_traces_requires_api_key(test_client, mock_store):
    response = test_client.get("/api/debug/traces")
    assert response.status_code == 403

def test_list_traces(test_client, mock_store):
    # Setup
    t1 = NL2SQLTrace(trace_id="t1", raw_query="q1")
    t2 = NL2SQLTrace(trace_id="t2", raw_query="q2")
    mock_store.save(t1)
    mock_store.save(t2)

    # Execute
    response = test_client.get("/api/debug/traces", headers=auth_headers())

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert len(data["traces"]) == 2
    
    trace_ids = [t["trace_id"] for t in data["traces"]]
    assert "t1" in trace_ids
    assert "t2" in trace_ids

def test_list_traces_limit(test_client, mock_store):
    for i in range(10):
        mock_store.save(NL2SQLTrace(trace_id=f"t{i}", raw_query=f"q{i}"))

    response = test_client.get("/api/debug/traces?limit=5", headers=auth_headers())
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 5
    assert len(data["traces"]) == 5

def test_get_trace(test_client, mock_store):
    t1 = NL2SQLTrace(trace_id="t1", raw_query="q1")
    mock_store.save(t1)

    response = test_client.get("/api/debug/traces/t1", headers=auth_headers())
    assert response.status_code == 200
    data = response.json()
    assert data["trace_id"] == "t1"
    assert data["raw_query"] == "q1"

def test_get_trace_missing(test_client, mock_store):
    response = test_client.get("/api/debug/traces/missing_id", headers=auth_headers())
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "NOT_FOUND"
    assert data["error"]["message"] == "Trace not found"

def test_debug_traces_disabled(monkeypatch, test_client, mock_store):
    monkeypatch.setenv("NL2SQL_DEBUG_ENDPOINTS_ENABLED", "false")
    
    response = test_client.get("/api/debug/traces", headers=auth_headers())
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "NOT_FOUND"
    assert data["error"]["message"] == "Not found"

    response = test_client.get("/api/debug/traces/t1", headers=auth_headers())
    assert response.status_code == 404
    data2 = response.json()
    assert data2["error"]["code"] == "NOT_FOUND"
    assert data2["error"]["message"] == "Not found"

def test_debug_traces_filters_by_sql_valid(test_client, mock_store):
    mock_store.save(NL2SQLTrace(trace_id="t1", sql_valid=True))
    mock_store.save(NL2SQLTrace(trace_id="t2", sql_valid=False))

    res = test_client.get("/api/debug/traces?sql_valid=false", headers=auth_headers())
    assert res.status_code == 200
    data = res.json()
    assert len(data["traces"]) == 1
    assert data["traces"][0]["trace_id"] == "t2"
    assert data["filters"]["sql_valid"] is False

def test_debug_traces_filters_by_error_type(test_client, mock_store):
    mock_store.save(NL2SQLTrace(trace_id="t1", error_type="err1"))
    mock_store.save(NL2SQLTrace(trace_id="t2", error_type="err2"))

    res = test_client.get("/api/debug/traces?error_type=err1", headers=auth_headers())
    assert res.status_code == 200
    data = res.json()
    assert len(data["traces"]) == 1
    assert data["traces"][0]["trace_id"] == "t1"
    assert data["filters"]["error_type"] == "err1"

def test_debug_traces_filters_by_job_id(test_client, mock_store):
    mock_store.save(NL2SQLTrace(trace_id="t1", metadata={"job_id": "j1"}))
    mock_store.save(NL2SQLTrace(trace_id="t2", metadata={"job_id": "j2"}))

    res = test_client.get("/api/debug/traces?job_id=j1", headers=auth_headers())
    assert res.status_code == 200
    data = res.json()
    assert len(data["traces"]) == 1
    assert data["traces"][0]["trace_id"] == "t1"
    assert data["filters"]["job_id"] == "j1"

def test_debug_traces_filters_by_dialect(test_client, mock_store):
    mock_store.save(NL2SQLTrace(trace_id="t1", metadata={"dialect": "pg"}))
    mock_store.save(NL2SQLTrace(trace_id="t2", metadata={"dialect": "mysql"}))

    res = test_client.get("/api/debug/traces?dialect=pg", headers=auth_headers())
    assert res.status_code == 200
    data = res.json()
    assert len(data["traces"]) == 1
    assert data["traces"][0]["trace_id"] == "t1"
    assert data["filters"]["dialect"] == "pg"

def test_debug_traces_paginates_with_limit_and_offset(test_client, mock_store):
    for i in range(5):
        mock_store.save(NL2SQLTrace(trace_id=f"t{i}", created_at=f"2026-01-0{i+1}T00:00:00+00:00"))

    res = test_client.get("/api/debug/traces?limit=2&offset=1", headers=auth_headers())
    assert res.status_code == 200
    data = res.json()
    assert len(data["traces"]) == 2
    assert data["traces"][0]["trace_id"] == "t3"
    assert data["traces"][1]["trace_id"] == "t2"

def test_debug_traces_returns_pagination_metadata(test_client, mock_store):
    for i in range(3):
        mock_store.save(NL2SQLTrace(trace_id=f"t{i}"))

    res = test_client.get("/api/debug/traces?limit=2&offset=0", headers=auth_headers())
    data = res.json()
    
    assert data["pagination"]["limit"] == 2
    assert data["pagination"]["offset"] == 0
    assert data["pagination"]["has_more"] is True
    assert data["pagination"]["next_offset"] == 2
    
    # Second page
    res2 = test_client.get("/api/debug/traces?limit=2&offset=2", headers=auth_headers())
    data2 = res2.json()
    
    assert data2["pagination"]["limit"] == 2
    assert data2["pagination"]["offset"] == 2
    assert data2["pagination"]["has_more"] is False
    assert data2["pagination"]["next_offset"] is None

def test_debug_trace_api_response_shape_is_stable(test_client, mock_store):
    mock_store.save(NL2SQLTrace(trace_id="t1"))
    
    res = test_client.get("/api/debug/traces", headers=auth_headers())
    data = res.json()
    
    assert "count" in data
    assert "pagination" in data
    assert "filters" in data
    assert "traces" in data
    
    assert "limit" in data["pagination"]
    assert "offset" in data["pagination"]
    assert "next_offset" in data["pagination"]
    assert "has_more" in data["pagination"]

def test_debug_trace_api_rejects_limit_over_200(test_client, mock_store):
    res = test_client.get("/api/debug/traces?limit=201", headers=auth_headers())
    assert res.status_code == 422  # validation error

def test_debug_trace_api_rejects_negative_offset(test_client, mock_store):
    res = test_client.get("/api/debug/traces?offset=-1", headers=auth_headers())
    assert res.status_code == 422  # validation error

def test_debug_trace_api_combines_filters_with_and_semantics(test_client, mock_store):
    mock_store.save(NL2SQLTrace(trace_id="t1", error_type="e1", metadata={"job_id": "j1"}))
    mock_store.save(NL2SQLTrace(trace_id="t2", error_type="e2", metadata={"job_id": "j1"}))
    mock_store.save(NL2SQLTrace(trace_id="t3", error_type="e1", metadata={"job_id": "j2"}))
    
    res = test_client.get("/api/debug/traces?error_type=e1&job_id=j1", headers=auth_headers())
    data = res.json()
    assert len(data["traces"]) == 1
    assert data["traces"][0]["trace_id"] == "t1"
    
    assert data["filters"]["error_type"] == "e1"
    assert data["filters"]["job_id"] == "j1"
