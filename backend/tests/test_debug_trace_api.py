import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.trace.dependencies import get_trace_store
from app.trace.memory_store import InMemoryTraceStore
from app.trace.models import NL2SQLTrace


@pytest.fixture
def test_client():
    client = TestClient(app)
    return client

@pytest.fixture
def mock_store():
    store = InMemoryTraceStore()
    app.dependency_overrides[get_trace_store] = lambda: store
    yield store
    app.dependency_overrides.clear()

def test_list_traces(test_client, mock_store):
    # Setup
    t1 = NL2SQLTrace(trace_id="t1", raw_query="q1")
    t2 = NL2SQLTrace(trace_id="t2", raw_query="q2")
    mock_store.save(t1)
    mock_store.save(t2)

    # Execute
    response = test_client.get("/api/debug/traces")

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

    response = test_client.get("/api/debug/traces?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 5
    assert len(data["traces"]) == 5

def test_get_trace(test_client, mock_store):
    t1 = NL2SQLTrace(trace_id="t1", raw_query="q1")
    mock_store.save(t1)

    response = test_client.get("/api/debug/traces/t1")
    assert response.status_code == 200
    data = response.json()
    assert data["trace_id"] == "t1"
    assert data["raw_query"] == "q1"

def test_get_trace_missing(test_client, mock_store):
    response = test_client.get("/api/debug/traces/missing_id")
    assert response.status_code == 404
    assert response.json()["detail"] == "Trace not found"

def test_debug_traces_disabled(monkeypatch, test_client, mock_store):
    monkeypatch.setenv("NL2SQL_DEBUG_ENDPOINTS_ENABLED", "false")
    
    response = test_client.get("/api/debug/traces")
    assert response.status_code == 404
    assert response.json()["detail"] == "Not found"

    response = test_client.get("/api/debug/traces/t1")
    assert response.status_code == 404
    assert response.json()["detail"] == "Not found"
