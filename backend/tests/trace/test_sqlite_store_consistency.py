import pytest
from datetime import datetime, timezone, timedelta
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

    loaded = trace_store.get("dup1")
    assert loaded.trace_id == "dup1"

def test_contract_serialization_error(trace_store):
    with pytest.raises(TraceSerializationError):
        rec = TraceRecord(trace_id="t_bad", trace_type="debug", payload={})
        rec.payload = {"bad": object()}  # type: ignore # bypass post_init validation via mutation
        trace_store.save(rec)

# Scoped filter tests to ensure Failure Locality

def test_contract_filter_by_trace_type(trace_store):
    trace_store.save(TraceRecord(trace_id="t1", trace_type="sql_pipeline", payload={}))
    trace_store.save(TraceRecord(trace_id="t2", trace_type="schema_pruning", payload={}))

    res = trace_store.list_traces(TraceQuery(trace_type="sql_pipeline"))
    assert len(res) == 1
    assert res[0].trace_id == "t1"

def test_contract_filter_by_request_id(trace_store):
    trace_store.save(TraceRecord(trace_id="t1", trace_type="debug", payload={}, request_id="req1"))
    trace_store.save(TraceRecord(trace_id="t2", trace_type="debug", payload={}, request_id="req2"))

    res = trace_store.list_traces(TraceQuery(request_id="req1"))
    assert len(res) == 1
    assert res[0].trace_id == "t1"

def test_contract_filter_by_job_id(trace_store):
    trace_store.save(TraceRecord(trace_id="t1", trace_type="debug", payload={}, job_id="job1"))
    trace_store.save(TraceRecord(trace_id="t2", trace_type="debug", payload={}, job_id="job2"))

    res = trace_store.list_traces(TraceQuery(job_id="job1"))
    assert len(res) == 1
    assert res[0].trace_id == "t1"

def test_contract_filter_by_dialect(trace_store):
    trace_store.save(TraceRecord(trace_id="t1", trace_type="debug", payload={"dialect": "postgres"}))
    trace_store.save(TraceRecord(trace_id="t2", trace_type="debug", payload={"dialect": "mysql"}))

    res = trace_store.list_traces(TraceQuery(dialect="postgres"))
    assert len(res) == 1
    assert res[0].trace_id == "t1"

def test_contract_filter_by_created_after(trace_store):
    trace_store.save(TraceRecord(trace_id="t1", trace_type="debug", payload={}, created_at=datetime(2026, 6, 1, 10, 0, 1, tzinfo=timezone.utc)))
    trace_store.save(TraceRecord(trace_id="t2", trace_type="debug", payload={}, created_at=datetime(2026, 6, 1, 10, 0, 3, tzinfo=timezone.utc)))

    res = trace_store.list_traces(TraceQuery(created_after="2026-06-01T10:00:02+00:00"))
    assert len(res) == 1
    assert res[0].trace_id == "t2"

def test_contract_filter_by_created_before(trace_store):
    trace_store.save(TraceRecord(trace_id="t1", trace_type="debug", payload={}, created_at=datetime(2026, 6, 1, 10, 0, 1, tzinfo=timezone.utc)))
    trace_store.save(TraceRecord(trace_id="t2", trace_type="debug", payload={}, created_at=datetime(2026, 6, 1, 10, 0, 3, tzinfo=timezone.utc)))

    res = trace_store.list_traces(TraceQuery(created_before="2026-06-01T10:00:02+00:00"))
    assert len(res) == 1
    assert res[0].trace_id == "t1"

def test_contract_limit_and_offset(trace_store):
    # Sort order DESC: t3 (newest), t2, t1 (oldest)
    trace_store.save(TraceRecord(trace_id="t1", trace_type="debug", payload={}, created_at=datetime(2026, 6, 1, 10, 0, 1, tzinfo=timezone.utc)))
    trace_store.save(TraceRecord(trace_id="t2", trace_type="debug", payload={}, created_at=datetime(2026, 6, 1, 10, 0, 2, tzinfo=timezone.utc)))
    trace_store.save(TraceRecord(trace_id="t3", trace_type="debug", payload={}, created_at=datetime(2026, 6, 1, 10, 0, 3, tzinfo=timezone.utc)))

    res = trace_store.list_traces(TraceQuery(limit=2, offset=1))
    assert len(res) == 2
    assert res[0].trace_id == "t2"
    assert res[1].trace_id == "t1"

def test_contract_ordering_determinism(trace_store):
    same_time = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    
    trace_store.save(TraceRecord(trace_id="trace-b", trace_type="debug", payload={}, created_at=same_time))
    trace_store.save(TraceRecord(trace_id="trace-c", trace_type="debug", payload={}, created_at=same_time))
    trace_store.save(TraceRecord(trace_id="trace-a", trace_type="debug", payload={}, created_at=same_time))

    res = trace_store.list_traces(TraceQuery(limit=10))
    assert len(res) == 3
    # Expected ordering: created_at DESC, trace_id DESC
    assert [t.trace_id for t in res] == ["trace-c", "trace-b", "trace-a"]

def test_contract_timezone_offset_ordering(trace_store):
    # Chronological instant sort check with varying timezone offsets:
    # 1. t_newest: 11:00 UTC / 14:00 +03:00 (newest)
    # 2. t_middle: 10:30 UTC / 10:30 +00:00 (middle)
    # 3. t_oldest: 10:00 UTC / 13:00 +03:00 (oldest)
    
    t_oldest = TraceRecord(
        trace_id="t_oldest",
        trace_type="debug",
        payload={},
        created_at=datetime(2026, 6, 1, 13, 0, 0, tzinfo=timezone(timedelta(hours=3)))
    )
    t_middle = TraceRecord(
        trace_id="t_middle",
        trace_type="debug",
        payload={},
        created_at=datetime(2026, 6, 1, 10, 30, 0, tzinfo=timezone.utc)
    )
    t_newest = TraceRecord(
        trace_id="t_newest",
        trace_type="debug",
        payload={},
        created_at=datetime(2026, 6, 1, 14, 0, 0, tzinfo=timezone(timedelta(hours=3)))
    )
    
    trace_store.save(t_middle)
    trace_store.save(t_newest)
    trace_store.save(t_oldest)
    
    res = trace_store.list_traces(TraceQuery(limit=10))
    assert len(res) == 3
    # Sorted newest first (instant chronology)
    assert [t.trace_id for t in res] == ["t_newest", "t_middle", "t_oldest"]
