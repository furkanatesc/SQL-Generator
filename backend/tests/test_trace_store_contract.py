import pytest
import time
from datetime import datetime
from app.trace.memory_store import InMemoryTraceStore
from app.trace.models import TraceRecord, DuplicateTraceError, TraceSerializationError
from app.trace.query import TraceQuery

def test_in_memory_trace_store_save_and_get():
    store = InMemoryTraceStore()

    record = TraceRecord(
        trace_id="trace_1",
        trace_type="sql_pipeline",
        payload={"success": True},
        job_id="job_1",
    )

    saved = store.save(record)

    assert saved.trace_id == "trace_1"
    assert store.get("trace_1") == saved

def test_trace_store_generates_trace_id_when_missing():
    store = InMemoryTraceStore()

    record = TraceRecord(
        trace_id="",
        trace_type="sql_pipeline",
        payload={},
    )

    saved = store.save(record)

    assert saved.trace_id.startswith("trace_")
    assert store.get(saved.trace_id) == saved

def test_trace_store_rejects_duplicate_trace_id():
    store = InMemoryTraceStore()

    store.save(TraceRecord(trace_id="trace_1", trace_type="debug", payload={}))

    with pytest.raises(DuplicateTraceError):
        store.save(TraceRecord(trace_id="trace_1", trace_type="debug", payload={}))

def test_trace_store_lists_newest_first():
    store = InMemoryTraceStore()
    
    # Save traces with a slight delay to ensure different created_at
    store.save(TraceRecord(trace_id="trace_old", trace_type="debug", payload={}))
    time.sleep(0.01)
    store.save(TraceRecord(trace_id="trace_new", trace_type="debug", payload={}))

    traces = store.list_traces()
    assert len(traces) == 2
    assert traces[0].trace_id == "trace_new"
    assert traces[1].trace_id == "trace_old"
    assert traces[0].created_at >= traces[1].created_at

def test_trace_store_filters_by_trace_type():
    store = InMemoryTraceStore()
    store.save(TraceRecord(trace_type="sql_pipeline", payload={}))
    store.save(TraceRecord(trace_type="schema_pruning", payload={}))

    result = store.list_traces(TraceQuery(trace_type="sql_pipeline"))

    assert len(result) == 1
    assert result[0].trace_type == "sql_pipeline"

def test_trace_store_filters_by_job_id():
    store = InMemoryTraceStore()
    store.save(TraceRecord(trace_type="sql_pipeline", job_id="job_a", payload={}))
    store.save(TraceRecord(trace_type="sql_pipeline", job_id="job_b", payload={}))

    result = store.list_traces(TraceQuery(job_id="job_b"))

    assert len(result) == 1
    assert result[0].job_id == "job_b"

def test_trace_store_limit_offset():
    store = InMemoryTraceStore()
    for i in range(10):
        # Time sleep to ensure ordering is strict (newest first)
        time.sleep(0.001)
        store.save(TraceRecord(trace_id=f"trace_{i}", trace_type="debug", payload={}))

    # Expect traces to be ordered from trace_9 down to trace_0
    result = store.list_traces(TraceQuery(limit=3, offset=2))

    assert len(result) == 3
    # trace_9 is offset 0, trace_8 is offset 1, trace_7 is offset 2
    assert result[0].trace_id == "trace_7"
    assert result[1].trace_id == "trace_6"
    assert result[2].trace_id == "trace_5"

def test_trace_store_rejects_non_json_serializable_payload():
    store = InMemoryTraceStore()

    with pytest.raises(TraceSerializationError):
        store.save(TraceRecord(
            trace_id="trace_bad",
            trace_type="sql_pipeline",
            payload={"bad": object()},
        ))

def test_trace_record_rejects_naive_created_at():
    with pytest.raises(ValueError, match="timezone-aware"):
        TraceRecord(
            trace_type="debug",
            payload={},
            created_at=datetime.utcnow(),
        )

def test_trace_store_filters_by_request_id():
    store = InMemoryTraceStore()
    store.save(TraceRecord(trace_type="sql_pipeline", request_id="req_a", payload={}))
    store.save(TraceRecord(trace_type="sql_pipeline", request_id="req_b", payload={}))

    result = store.list_traces(TraceQuery(request_id="req_b"))

    assert len(result) == 1
    assert result[0].request_id == "req_b"

def test_trace_record_rejects_non_dict_payload():
    with pytest.raises(TypeError, match="payload must be a dictionary"):
        TraceRecord(trace_type="debug", payload="not a dict")  # type: ignore

    with pytest.raises(TypeError, match="payload must be a dictionary"):
        TraceRecord(trace_type="debug", payload=[1, 2, 3])  # type: ignore

def test_trace_query_validation():
    with pytest.raises(ValueError, match="limit must be >= 1"):
        TraceQuery(limit=0)

    with pytest.raises(ValueError, match="limit must be >= 1"):
        TraceQuery(limit=-5)

    with pytest.raises(ValueError, match="offset must be >= 0"):
        TraceQuery(offset=-1)
