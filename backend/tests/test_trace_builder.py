import pytest
from app.trace.builders import build_trace_from_pruned_schema

def test_build_trace_from_pruned_schema():
    raw_query = "doktor listesi"
    pruned_schema = {
        "pruned": True,
        "estimated_tokens": 123,
        "error": None,
        "debug_trace": {
            "candidate_signals": [{"table": "HST_DOKTOR", "score": 0.9}],
            "rag_matches": [],
            "selected_tables": ["HST_DOKTOR"],
            "graph_trace": {"path_mode": "undirected_weighted"},
        }
    }
    
    trace = build_trace_from_pruned_schema(raw_query, pruned_schema)
    
    assert trace.raw_query == raw_query
    assert trace.estimated_tokens == 123
    assert trace.selected_tables == ["HST_DOKTOR"]
    assert trace.candidate_signals == [{"table": "HST_DOKTOR", "score": 0.9}]
    assert trace.rag_matches == []
    assert trace.graph_trace == {"path_mode": "undirected_weighted"}
    assert trace.error_message is None
    
    # Ensure trace_id and created_at are generated
    assert trace.trace_id is not None
    assert trace.created_at is not None

def test_build_trace_with_error_and_empty_debug_trace():
    raw_query = "alakasiz query"
    pruned_schema = {
        "pruned": False,
        "error": "Tablo bulunamadı",
        # no debug_trace or estimated_tokens
    }
    
    trace = build_trace_from_pruned_schema(raw_query, pruned_schema)
    
    assert trace.raw_query == raw_query
    assert trace.error_message == "Tablo bulunamadı"
    assert trace.estimated_tokens == 0
    assert trace.candidate_signals == []
    assert trace.graph_trace == {}
