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
