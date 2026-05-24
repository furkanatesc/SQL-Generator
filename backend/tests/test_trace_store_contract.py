import pytest
from app.trace.models import NL2SQLTrace
from app.trace.memory_store import InMemoryTraceStore
from app.trace.sqlite_store import SQLiteTraceStore
from app.trace.query import TraceQuery

@pytest.fixture(params=["memory", "sqlite"])
def store(request, tmp_path):
    if request.param == "memory":
        yield InMemoryTraceStore()
    else:
        db_path = tmp_path / "traces.db"
        store = SQLiteTraceStore(str(db_path))
        yield store
        store.close()

def test_list_recent_backward_compatibility(store):
    for i in range(3):
        store.save(NL2SQLTrace(trace_id=f"t{i}", created_at=f"2026-01-0{i+1}T00:00:00+00:00"))
    
    recent = store.list_recent(limit=2)
    assert len(recent) == 2
    assert recent[0].trace_id == "t2"
    assert recent[1].trace_id == "t1"

def test_trace_store_contract_orders_deterministically(store):
    ts = "2026-01-01T00:00:00+00:00"
    store.save(NL2SQLTrace(trace_id="A", created_at=ts))
    store.save(NL2SQLTrace(trace_id="C", created_at=ts))
    store.save(NL2SQLTrace(trace_id="B", created_at=ts))
    
    res = store.list_traces(TraceQuery())
    assert len(res) == 3
    # Order should be created_at DESC, trace_id DESC
    assert res[0].trace_id == "C"
    assert res[1].trace_id == "B"
    assert res[2].trace_id == "A"

def test_trace_store_contract_filters_with_and_semantics(store):
    store.save(NL2SQLTrace(trace_id="t1", sql_valid=True, error_type="e1"))
    store.save(NL2SQLTrace(trace_id="t2", sql_valid=False, error_type="e1"))
    store.save(NL2SQLTrace(trace_id="t3", sql_valid=False, error_type="e2"))
    
    res = store.list_traces(TraceQuery(sql_valid=False, error_type="e1"))
    assert len(res) == 1
    assert res[0].trace_id == "t2"

def test_trace_store_contract_round_trips_attempts_and_validation_errors(store):
    trace = NL2SQLTrace(
        trace_id="t1",
        last_generated_sql="SELECT *",
        sql_valid=False,
        sql_validation_errors=[{"type": "unsafe_sql", "stage": "sql_guardrail"}],
        attempts=[{"attempt": 1, "valid": False, "validation_errors": [{"type": "unsafe_sql"}]}]
    )
    store.save(trace)
    
    loaded = store.get("t1")
    assert loaded.last_generated_sql == "SELECT *"
    assert loaded.sql_valid is False
    assert loaded.sql_validation_errors == [{"type": "unsafe_sql", "stage": "sql_guardrail"}]
    assert loaded.attempts == [{"attempt": 1, "valid": False, "validation_errors": [{"type": "unsafe_sql"}]}]

def test_trace_store_contract_filters_by_job_id_and_dialect(store):
    store.save(NL2SQLTrace(trace_id="t1", metadata={"job_id": "j1", "dialect": "pg"}))
    store.save(NL2SQLTrace(trace_id="t2", metadata={"job_id": "j1", "dialect": "mysql"}))
    store.save(NL2SQLTrace(trace_id="t3", metadata={"job_id": "j2", "dialect": "pg"}))

    res = store.list_traces(TraceQuery(job_id="j1", dialect="pg"))
    assert len(res) == 1
    assert res[0].trace_id == "t1"
