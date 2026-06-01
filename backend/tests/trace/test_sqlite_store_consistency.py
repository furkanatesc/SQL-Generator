import pytest
import time
from datetime import datetime, timezone
from app.trace.memory_store import InMemoryTraceStore
from app.trace.sqlite_store import SQLiteTraceStore
from app.trace.models import TraceRecord, DuplicateTraceError, TraceSerializationError
from app.trace.query import TraceQuery

@pytest.fixture(params=["memory", "sqlite"])
def trace_store(request, tmp_path):
    if request.param == "memory":
        return InMemoryTraceStore()
    db_path = tmp_path / "traces.db"
    return SQLiteTraceStore(str(db_path))

def test_contract_round_trip(trace_store):
    created = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    record = TraceRecord(
        trace_id="t1",
        trace_type="sql_pipeline",
        payload={"nested": {"data": 42}, "dialect": "postgres"},
        created_at=created,
        job_id="job_abc",
        request_id="req_123"
    )

    saved = trace_store.save(record)
    assert saved.trace_id == "t1"

    loaded = trace_store.get("t1")
    assert loaded is not None
    assert loaded.trace_id == "t1"
    assert loaded.trace_type == "sql_pipeline"
    assert loaded.payload == {"nested": {"data": 42}, "dialect": "postgres"}
    assert loaded.created_at == created
    assert loaded.created_at.tzinfo is not None
    assert loaded.job_id == "job_abc"
    assert loaded.request_id == "req_123"

def test_contract_duplicate_raises_error(trace_store):
    record1 = TraceRecord(trace_id="dup1", trace_type="debug", payload={})
    record2 = TraceRecord(trace_id="dup1", trace_type="debug", payload={})

    trace_store.save(record1)

    with pytest.raises(DuplicateTraceError):
        trace_store.save(record2)

    # Verify no silent overwrite occurred
    loaded = trace_store.get("dup1")
    assert loaded.trace_id == "dup1"

def test_contract_serialization_error(trace_store):
    with pytest.raises(TraceSerializationError):
        rec = TraceRecord(trace_id="t_bad", trace_type="debug", payload={})
        rec.payload = {"bad": object()}  # bypass post_init validation via mutation
        trace_store.save(rec)

def test_contract_query_filtering(trace_store):
    # Setup some test records
    base_time = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    
    # Trace 1
    t1 = TraceRecord(
        trace_id="t1",
        trace_type="sql_pipeline",
        payload={"dialect": "postgres"},
        created_at=datetime(2026, 6, 1, 10, 0, 1, tzinfo=timezone.utc),
        job_id="job1",
        request_id="req1"
    )
    # Trace 2
    t2 = TraceRecord(
        trace_id="t2",
        trace_type="schema_pruning",
        payload={"dialect": "mysql"},
        created_at=datetime(2026, 6, 1, 10, 0, 2, tzinfo=timezone.utc),
        job_id="job1",
        request_id="req2"
    )
    # Trace 3
    t3 = TraceRecord(
        trace_id="t3",
        trace_type="sql_pipeline",
        payload={"dialect": "postgres"},
        created_at=datetime(2026, 6, 1, 10, 0, 3, tzinfo=timezone.utc),
        job_id="job2",
        request_id="req1"
    )

    trace_store.save(t1)
    trace_store.save(t2)
    trace_store.save(t3)

    # Filter by trace_type
    res = trace_store.list_traces(TraceQuery(trace_type="sql_pipeline"))
    assert len(res) == 2
    assert {t.trace_id for t in res} == {"t1", "t3"}

    # Filter by request_id
    res = trace_store.list_traces(TraceQuery(request_id="req1"))
    assert len(res) == 2
    assert {t.trace_id for t in res} == {"t1", "t3"}

    # Filter by job_id
    res = trace_store.list_traces(TraceQuery(job_id="job1"))
    assert len(res) == 2
    assert {t.trace_id for t in res} == {"t1", "t2"}

    # Filter by dialect
    res = trace_store.list_traces(TraceQuery(dialect="postgres"))
    assert len(res) == 2
    assert {t.trace_id for t in res} == {"t1", "t3"}

    # Filter by created_after (t2 & t3)
    res = trace_store.list_traces(TraceQuery(created_after="2026-06-01T10:00:02+00:00"))
    assert len(res) == 2
    assert {t.trace_id for t in res} == {"t2", "t3"}

    # Filter by created_before (t1 & t2)
    res = trace_store.list_traces(TraceQuery(created_before="2026-06-01T10:00:02+00:00"))
    assert len(res) == 2
    assert {t.trace_id for t in res} == {"t1", "t2"}

    # Limit and offset
    # Sorted desc by created_at: t3 (newest), t2, t1 (oldest)
    res = trace_store.list_traces(TraceQuery(limit=2, offset=1))
    assert len(res) == 2
    assert res[0].trace_id == "t2"
    assert res[1].trace_id == "t1"

def test_contract_ordering_determinism(trace_store):
    same_time = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    
    # Save three traces with the exact same created_at
    trace_store.save(TraceRecord(trace_id="trace-b", trace_type="debug", payload={}, created_at=same_time))
    trace_store.save(TraceRecord(trace_id="trace-c", trace_type="debug", payload={}, created_at=same_time))
    trace_store.save(TraceRecord(trace_id="trace-a", trace_type="debug", payload={}, created_at=same_time))

    res = trace_store.list_traces(TraceQuery(limit=10))
    assert len(res) == 3
    # Expected ordering: created_at DESC, trace_id DESC
    # Since created_at is identical, it must fall back to trace_id descending: trace-c, trace-b, trace-a
    assert [t.trace_id for t in res] == ["trace-c", "trace-b", "trace-a"]
