import pytest
import time
from app.trace.models import NL2SQLTrace
from app.trace.memory_store import InMemoryTraceStore

def test_trace_store_save_and_get():
    store = InMemoryTraceStore()
    
    trace = NL2SQLTrace(
        raw_query="test query",
        selected_tables=["A", "B"]
    )
    
    # Trace should not exist initially
    assert store.get(trace.trace_id) is None
    
    store.save(trace)
    
    # Trace should exist after save
    retrieved = store.get(trace.trace_id)
    assert retrieved is not None
    assert retrieved.trace_id == trace.trace_id
    assert retrieved.raw_query == "test query"
    assert retrieved.selected_tables == ["A", "B"]

def test_trace_store_list_recent_limits_and_sorts():
    store = InMemoryTraceStore()
    
    traces = []
    for i in range(5):
        trace = NL2SQLTrace(raw_query=f"query {i}")
        # Artificial delay to ensure different timestamps
        time.sleep(0.01)
        store.save(trace)
        traces.append(trace)
        
    recent = store.list_recent(limit=3)
    
    assert len(recent) == 3
    # Most recent should be query 4, 3, 2
    assert recent[0].raw_query == "query 4"
    assert recent[1].raw_query == "query 3"
    assert recent[2].raw_query == "query 2"

def test_trace_store_get_nonexistent_returns_none():
    store = InMemoryTraceStore()
    assert store.get("fake-id") is None

from app.trace.query import TraceQuery

def test_memory_store_filters_by_sql_valid():
    store = InMemoryTraceStore()
    store.save(NL2SQLTrace(trace_id="t1", sql_valid=True))
    store.save(NL2SQLTrace(trace_id="t2", sql_valid=False))
    
    assert len(store.list_traces(TraceQuery(sql_valid=True))) == 1
    assert store.list_traces(TraceQuery(sql_valid=True))[0].trace_id == "t1"
    
    assert len(store.list_traces(TraceQuery(sql_valid=False))) == 1
    assert store.list_traces(TraceQuery(sql_valid=False))[0].trace_id == "t2"

def test_memory_store_filters_by_error_type():
    store = InMemoryTraceStore()
    store.save(NL2SQLTrace(trace_id="t1", error_type="sql_generation_failed"))
    store.save(NL2SQLTrace(trace_id="t2", error_type="timeout"))
    
    res = store.list_traces(TraceQuery(error_type="sql_generation_failed"))
    assert len(res) == 1
    assert res[0].trace_id == "t1"

def test_memory_store_filters_by_job_id_from_metadata():
    store = InMemoryTraceStore()
    store.save(NL2SQLTrace(trace_id="t1", metadata={"job_id": "job1"}))
    store.save(NL2SQLTrace(trace_id="t2", metadata={"job_id": "job2"}))
    
    res = store.list_traces(TraceQuery(job_id="job1"))
    assert len(res) == 1
    assert res[0].trace_id == "t1"

def test_memory_store_filters_by_dialect_from_metadata():
    store = InMemoryTraceStore()
    store.save(NL2SQLTrace(trace_id="t1", metadata={"dialect": "postgresql"}))
    store.save(NL2SQLTrace(trace_id="t2", metadata={"dialect": "mysql"}))
    
    res = store.list_traces(TraceQuery(dialect="postgresql"))
    assert len(res) == 1
    assert res[0].trace_id == "t1"

def test_memory_store_applies_offset_and_limit():
    store = InMemoryTraceStore()
    for i in range(5):
        store.save(NL2SQLTrace(trace_id=f"t{i}", created_at=f"2026-01-0{i+1}T00:00:00+00:00"))
        
    res = store.list_traces(TraceQuery(limit=2, offset=1))
    assert len(res) == 2
    assert res[0].trace_id == "t3"  # t4 is the newest, then t3, t2, t1, t0
    assert res[1].trace_id == "t2"

def test_memory_store_orders_by_created_at_desc_then_trace_id_desc():
    store = InMemoryTraceStore()
    # Same created_at
    ts = "2026-01-01T00:00:00+00:00"
    store.save(NL2SQLTrace(trace_id="A", created_at=ts))
    store.save(NL2SQLTrace(trace_id="B", created_at=ts))
    store.save(NL2SQLTrace(trace_id="C", created_at=ts))
    
    res = store.list_traces(TraceQuery())
    assert len(res) == 3
    assert res[0].trace_id == "C"
    assert res[1].trace_id == "B"
    assert res[2].trace_id == "A"
