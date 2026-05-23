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

def test_build_trace_from_pruned_schema_includes_sql_error_latency_metadata():
    raw_query = "show users"
    pruned_schema = {"estimated_tokens": 50, "error": "some internal err"}
    trace = build_trace_from_pruned_schema(
        raw_query=raw_query,
        pruned_schema=pruned_schema,
        generated_sql="SELECT * FROM users",
        error_type="SyntaxError",
        latency_ms={"total": 1200},
        metadata={"job_id": "job-123"}
    )
    assert trace.generated_sql == "SELECT * FROM users"
    assert trace.error_message == "some internal err"
    assert trace.error_type == "SyntaxError"
    assert trace.latency_ms == {"total": 1200}
    assert trace.metadata == {"job_id": "job-123"}

def test_build_trace_includes_validation_fields():
    trace = build_trace_from_pruned_schema(
        raw_query="q",
        pruned_schema={"estimated_tokens": 12},
        generated_sql="SELECT 1",
        last_generated_sql="SELECT 1",
        sql_valid=True,
        sql_validation_errors=[],
        attempts=[{"attempt": 1, "valid": True}],
    )

    assert trace.generated_sql == "SELECT 1"
    assert trace.last_generated_sql == "SELECT 1"
    assert trace.sql_valid is True
    assert trace.sql_validation_errors == []
    assert trace.attempts == [{"attempt": 1, "valid": True}]
