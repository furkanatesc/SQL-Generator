import pytest
import datetime as dt
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.trace.dependencies import get_trace_store
from app.trace.memory_store import InMemoryTraceStore
from app.trace.models import TraceRecord, NL2SQLTrace
from app.trace.sqlite_store import SQLiteTraceStore

API_KEY = "contract-test-key"

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

# --- 1. Response Shape Contract Tests ---

def test_debug_traces_list_response_shape_contract(test_client, mock_store):
    record = TraceRecord(
        trace_type="test_run",
        payload={"message": "hello world", "sql_valid": True},
        job_id="job_123",
        request_id="req_456"
    )
    mock_store.save(record)

    response = test_client.get("/api/debug/traces", headers=auth_headers())
    assert response.status_code == 200
    data = response.json()

    # Top-level keys check
    assert "count" in data
    assert "pagination" in data
    assert "filters" in data
    assert "traces" in data

    # Pagination shape check
    assert isinstance(data["pagination"], dict)
    assert "limit" in data["pagination"]
    assert "offset" in data["pagination"]
    assert "next_offset" in data["pagination"]
    assert "has_more" in data["pagination"]

    # Filters shape check
    assert isinstance(data["filters"], dict)
    for key in ["trace_type", "request_id", "job_id", "dialect", "created_after", "created_before", "sql_valid", "error_type"]:
        assert key in data["filters"]

    # Trace items shape check
    assert isinstance(data["traces"], list)
    assert len(data["traces"]) == 1
    item = data["traces"][0]
    assert item["trace_id"] == record.trace_id
    assert item["trace_type"] == "test_run"
    assert item["job_id"] == "job_123"
    assert item["request_id"] == "req_456"
    assert "created_at" in item
    assert "payload" in item
    assert item["payload"]["message"] == "hello world"

def test_debug_traces_get_single_response_shape_contract(test_client, mock_store):
    record = TraceRecord(
        trace_type="single_item",
        payload={"meta": "val"},
        job_id="j1",
        request_id="r1"
    )
    mock_store.save(record)

    response = test_client.get(f"/api/debug/traces/{record.trace_id}", headers=auth_headers())
    assert response.status_code == 200
    item = response.json()

    assert item["trace_id"] == record.trace_id
    assert item["trace_type"] == "single_item"
    assert item["job_id"] == "j1"
    assert item["request_id"] == "r1"
    assert "created_at" in item
    assert "payload" in item
    assert item["payload"]["meta"] == "val"

def test_debug_traces_get_single_returns_404_if_missing(test_client, mock_store):
    response = test_client.get("/api/debug/traces/missing_trace_id", headers=auth_headers())
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "NOT_FOUND"
    assert "Trace not found" in data["error"]["message"]

# --- 2. Query Parameter Validation Tests ---

def test_debug_traces_api_validation_limit_constraints(test_client, mock_store):
    # limit over 200
    res1 = test_client.get("/api/debug/traces?limit=201", headers=auth_headers())
    assert res1.status_code == 422

    # limit under 1
    res2 = test_client.get("/api/debug/traces?limit=0", headers=auth_headers())
    assert res2.status_code == 422

def test_debug_traces_api_validation_offset_constraints(test_client, mock_store):
    # offset under 0
    res = test_client.get("/api/debug/traces?offset=-5", headers=auth_headers())
    assert res.status_code == 422

# --- 3. Debug Endpoint Enable/Disable Toggle Tests ---

def test_debug_traces_disabled_behavior_returns_404(monkeypatch, test_client, mock_store):
    monkeypatch.setenv("NL2SQL_DEBUG_ENDPOINTS_ENABLED", "false")
    
    # List endpoint check
    response_list = test_client.get("/api/debug/traces", headers=auth_headers())
    assert response_list.status_code == 404

    # Single endpoint check
    response_single = test_client.get("/api/debug/traces/some-id", headers=auth_headers())
    assert response_single.status_code == 404

# --- 4. Auth Behavior Tests ---

def test_debug_traces_api_key_auth_enforcement(test_client, mock_store):
    # No auth header
    res1 = test_client.get("/api/debug/traces")
    assert res1.status_code == 403

    # Invalid auth header
    res2 = test_client.get("/api/debug/traces", headers={"X-API-Key": "wrong-key"})
    assert res2.status_code == 403

def test_debug_traces_disabled_endpoint_plus_valid_key_still_returns_404(monkeypatch, test_client, mock_store):
    monkeypatch.setenv("NL2SQL_DEBUG_ENDPOINTS_ENABLED", "false")
    response = test_client.get("/api/debug/traces", headers=auth_headers())
    assert response.status_code == 404

# --- 5. Secret Redaction Safety Tests ---

def test_debug_traces_payload_secrets_are_redacted(test_client, mock_store):
    record = TraceRecord(
        trace_type="secrets_run",
        payload={
            "api_key": "nvapi-1234567890abcdef",
            "password": "mysecretpassword123",
            "token": "sk-abc123xyz789",
            "normal_value": "safe to expose"
        }
    )
    mock_store.save(record)

    response = test_client.get(f"/api/debug/traces/{record.trace_id}", headers=auth_headers())
    assert response.status_code == 200
    data = response.json()

    # The payload fields should be redacted by redact_sensitive
    assert data["payload"]["api_key"] == "[REDACTED]"
    assert data["payload"]["password"] == "[REDACTED]"
    assert data["payload"]["token"] == "[REDACTED]"
    assert data["payload"]["normal_value"] == "safe to expose"

# --- 6. Dedicated Query Filter Tests ---

def test_debug_traces_filter_by_trace_type(test_client, mock_store):
    mock_store.save(TraceRecord(trace_type="type_a", payload={}))
    mock_store.save(TraceRecord(trace_type="type_b", payload={}))

    response = test_client.get("/api/debug/traces?trace_type=type_a", headers=auth_headers())
    data = response.json()
    assert len(data["traces"]) == 1
    assert data["traces"][0]["trace_type"] == "type_a"
    assert data["filters"]["trace_type"] == "type_a"

def test_debug_traces_filter_by_request_id(test_client, mock_store):
    mock_store.save(TraceRecord(trace_type="t", request_id="r1", payload={}))
    mock_store.save(TraceRecord(trace_type="t", request_id="r2", payload={}))

    response = test_client.get("/api/debug/traces?request_id=r2", headers=auth_headers())
    data = response.json()
    assert len(data["traces"]) == 1
    assert data["traces"][0]["request_id"] == "r2"
    assert data["filters"]["request_id"] == "r2"

def test_debug_traces_filter_by_job_id(test_client, mock_store):
    mock_store.save(TraceRecord(trace_type="t", job_id="j1", payload={}))
    mock_store.save(TraceRecord(trace_type="t", job_id="j2", payload={}))

    response = test_client.get("/api/debug/traces?job_id=j1", headers=auth_headers())
    data = response.json()
    assert len(data["traces"]) == 1
    assert data["traces"][0]["job_id"] == "j1"
    assert data["filters"]["job_id"] == "j1"

def test_debug_traces_filter_by_dialect(test_client, mock_store):
    mock_store.save(TraceRecord(trace_type="t", payload={"dialect": "postgres"}))
    mock_store.save(TraceRecord(trace_type="t", payload={"dialect": "oracle"}))

    response = test_client.get("/api/debug/traces?dialect=postgres", headers=auth_headers())
    data = response.json()
    assert len(data["traces"]) == 1
    assert data["traces"][0]["payload"]["dialect"] == "postgres"
    assert data["filters"]["dialect"] == "postgres"

def test_debug_traces_filter_by_created_after(test_client, mock_store):
    t1 = TraceRecord(trace_type="t", payload={}, created_at=dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.timezone.utc))
    t2 = TraceRecord(trace_type="t", payload={}, created_at=dt.datetime(2026, 1, 3, 12, 0, tzinfo=dt.timezone.utc))
    mock_store.save(t1)
    mock_store.save(t2)

    response = test_client.get("/api/debug/traces?created_after=2026-01-02T00:00:00%2B00:00", headers=auth_headers())
    data = response.json()
    assert len(data["traces"]) == 1
    assert data["traces"][0]["trace_id"] == t2.trace_id

def test_debug_traces_filter_by_created_before(test_client, mock_store):
    t1 = TraceRecord(trace_type="t", payload={}, created_at=dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.timezone.utc))
    t2 = TraceRecord(trace_type="t", payload={}, created_at=dt.datetime(2026, 1, 3, 12, 0, tzinfo=dt.timezone.utc))
    mock_store.save(t1)
    mock_store.save(t2)

    response = test_client.get("/api/debug/traces?created_before=2026-01-02T00:00:00%2B00:00", headers=auth_headers())
    data = response.json()
    assert len(data["traces"]) == 1
    assert data["traces"][0]["trace_id"] == t1.trace_id

def test_debug_traces_filter_by_sql_valid(test_client, mock_store):
    mock_store.save(TraceRecord(trace_type="t", payload={"sql_valid": True}))
    mock_store.save(TraceRecord(trace_type="t", payload={"sql_valid": False}))

    response = test_client.get("/api/debug/traces?sql_valid=true", headers=auth_headers())
    data = response.json()
    assert len(data["traces"]) == 1
    assert data["traces"][0]["payload"]["sql_valid"] is True

def test_debug_traces_filter_by_error_type(test_client, mock_store):
    mock_store.save(TraceRecord(trace_type="t", payload={"error_type": "ValueError"}))
    mock_store.save(TraceRecord(trace_type="t", payload={"error_type": "KeyError"}))

    response = test_client.get("/api/debug/traces?error_type=ValueError", headers=auth_headers())
    data = response.json()
    assert len(data["traces"]) == 1
    assert data["traces"][0]["payload"]["error_type"] == "ValueError"

# --- 7. Pagination limit / offset / has_more / next_offset Tests ---

def test_debug_traces_pagination_has_more_and_next_offset(test_client, mock_store):
    # Save 3 records
    for i in range(3):
        mock_store.save(TraceRecord(trace_type="t", payload={}))

    # Get page 1 (limit 2)
    response_p1 = test_client.get("/api/debug/traces?limit=2&offset=0", headers=auth_headers())
    data_p1 = response_p1.json()
    assert len(data_p1["traces"]) == 2
    assert data_p1["pagination"]["has_more"] is True
    assert data_p1["pagination"]["next_offset"] == 2

    # Get page 2 (limit 2)
    response_p2 = test_client.get("/api/debug/traces?limit=2&offset=2", headers=auth_headers())
    data_p2 = response_p2.json()
    assert len(data_p2["traces"]) == 1
    assert data_p2["pagination"]["has_more"] is False
    assert data_p2["pagination"]["next_offset"] is None

# --- 8. SQLite Integration Tests ---

def test_debug_traces_sqlite_integration_canonical_and_legacy(tmp_path, test_client):
    db_path = tmp_path / "traces_contract.db"
    sqlite_store = SQLiteTraceStore(str(db_path))

    # 1. Save canonical TraceRecord
    record = TraceRecord(
        trace_id="canonical-sqlite-1",
        trace_type="prod_pipeline",
        payload={"success": True, "dialect": "postgres"},
        job_id="job_sql_1",
        request_id="req_sql_1"
    )
    sqlite_store.save(record)

    # 2. Save legacy NL2SQLTrace
    legacy_trace = NL2SQLTrace(
        trace_id="legacy-sqlite-2",
        raw_query="SELECT COUNT(*) FROM users;",
        sql_valid=False,
        error_type="SyntaxError"
    )
    # Put dialect postgres into metadata for legacy trace
    legacy_trace.metadata = {"dialect": "postgres", "job_id": "job_sql_2", "request_id": "req_sql_2"}
    sqlite_store.save_legacy(legacy_trace)

    # Override get_trace_store dependency to use this active SQLiteTraceStore
    app.dependency_overrides[get_trace_store] = lambda: sqlite_store

    try:
        # Check GET /api/debug/traces
        response = test_client.get("/api/debug/traces", headers=auth_headers())
        assert response.status_code == 200
        data = response.json()
        
        # Verify both canonical and legacy records are returned by the merged list
        assert data["count"] == 2
        trace_ids = [t["trace_id"] for t in data["traces"]]
        assert "canonical-sqlite-1" in trace_ids
        assert "legacy-sqlite-2" in trace_ids
        
        # Test getting canonical record
        res_canonical = test_client.get("/api/debug/traces/canonical-sqlite-1", headers=auth_headers())
        assert res_canonical.status_code == 200
        can_data = res_canonical.json()
        assert can_data["trace_id"] == "canonical-sqlite-1"
        assert can_data["trace_type"] == "prod_pipeline"
        assert can_data["payload"]["dialect"] == "postgres"
        
        # Test getting legacy record
        res_legacy = test_client.get("/api/debug/traces/legacy-sqlite-2", headers=auth_headers())
        assert res_legacy.status_code == 200
        leg_data = res_legacy.json()
        assert leg_data["trace_id"] == "legacy-sqlite-2"
        assert leg_data["trace_type"] == "nl2sql"
        assert leg_data["raw_query"] == "SELECT COUNT(*) FROM users;"
        assert leg_data["payload"]["raw_query"] == "SELECT COUNT(*) FROM users;"
        
    finally:
        app.dependency_overrides.clear()
        sqlite_store.close()

def test_debug_traces_sqlite_integration_filter_trace_type(tmp_path, test_client):
    db_path = tmp_path / "traces_filter_trace_type.db"
    sqlite_store = SQLiteTraceStore(str(db_path))

    # 1. Save canonical TraceRecord with trace_type="prod_pipeline"
    record = TraceRecord(
        trace_id="canonical-sqlite-1",
        trace_type="prod_pipeline",
        payload={"dialect": "postgres"}
    )
    sqlite_store.save(record)

    # 2. Save legacy NL2SQLTrace (serialized trace_type will be "nl2sql")
    legacy_trace = NL2SQLTrace(
        trace_id="legacy-sqlite-2",
        raw_query="SELECT * FROM users;"
    )
    sqlite_store.save_legacy(legacy_trace)

    app.dependency_overrides[get_trace_store] = lambda: sqlite_store
    try:
        # GET /api/debug/traces?trace_type=prod_pipeline -> only canonical returned
        response = test_client.get("/api/debug/traces?trace_type=prod_pipeline", headers=auth_headers())
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["traces"][0]["trace_id"] == "canonical-sqlite-1"

        # GET /api/debug/traces?trace_type=nl2sql -> only legacy returned
        response_leg = test_client.get("/api/debug/traces?trace_type=nl2sql", headers=auth_headers())
        assert response_leg.status_code == 200
        data_leg = response_leg.json()
        assert data_leg["count"] == 1
        assert data_leg["traces"][0]["trace_id"] == "legacy-sqlite-2"
    finally:
        app.dependency_overrides.clear()
        sqlite_store.close()

def test_debug_traces_sqlite_integration_filter_request_id(tmp_path, test_client):
    db_path = tmp_path / "traces_filter_request_id.db"
    sqlite_store = SQLiteTraceStore(str(db_path))

    # 1. Save canonical TraceRecord with request_id="req-1"
    record = TraceRecord(
        trace_id="canonical-sqlite-1",
        trace_type="prod_pipeline",
        payload={"dialect": "postgres"},
        request_id="req-1"
    )
    sqlite_store.save(record)

    # 2. Save legacy NL2SQLTrace with request_id="req-2" in metadata
    legacy_trace = NL2SQLTrace(
        trace_id="legacy-sqlite-2",
        raw_query="SELECT * FROM users;"
    )
    legacy_trace.metadata = {"request_id": "req-2"}
    sqlite_store.save_legacy(legacy_trace)

    app.dependency_overrides[get_trace_store] = lambda: sqlite_store
    try:
        # GET /api/debug/traces?request_id=req-1 -> only canonical returned
        response = test_client.get("/api/debug/traces?request_id=req-1", headers=auth_headers())
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["traces"][0]["trace_id"] == "canonical-sqlite-1"

        # GET /api/debug/traces?request_id=req-2 -> only legacy returned
        response_leg = test_client.get("/api/debug/traces?request_id=req-2", headers=auth_headers())
        assert response_leg.status_code == 200
        data_leg = response_leg.json()
        assert data_leg["count"] == 1
        assert data_leg["traces"][0]["trace_id"] == "legacy-sqlite-2"
    finally:
        app.dependency_overrides.clear()
        sqlite_store.close()
