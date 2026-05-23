import pytest
from unittest.mock import MagicMock, patch
from app.schema_pruner import SchemaPruner

@patch('app.rag_manager.RAGManager')
def test_rag_threshold_filters_correctly(MockRAGManager):
    # Setup mock RAG manager
    mock_rag = MockRAGManager.return_value
    
    # Simulate hits: one above threshold, one below, one without score
    mock_rag.search_ddl.return_value = [
        {"payload": {"table_name": "HST_DOKTOR"}, "score": 0.84}, # Accepted
        {"payload": {"table_name": "HST_HASTA"}, "score": 0.60},  # Rejected
        {"payload": {"table_name": "PER_VERGIIADE_MAIN"}}         # Rejected (no score)
    ]
    
    pruner = SchemaPruner()
    
    mock_schema = {
        "tables": {
            "HST_DOKTOR": {"columns": []},
            "HST_HASTA": {"columns": []},
            "PER_VERGIIADE_MAIN": {"columns": []}
        }
    }
    
    aqr = {"natural_query": "doktorları getir"}
    
    candidates = pruner.resolve_entities(aqr, mock_schema)
    
    # Check that HST_DOKTOR is in candidates, but HST_HASTA is not.
    candidate_tables = [c.table for c in candidates]
    assert "HST_DOKTOR" in candidate_tables
    assert "HST_HASTA" not in candidate_tables
    
    # Check trace data for accepted and rejected hits
    rag_traces = pruner.rag_traces
    assert len(rag_traces) == 2  # The one without score is ignored completely
    
    doktor_trace = next(t for t in rag_traces if t["table"] == "HST_DOKTOR")
    assert doktor_trace["raw_score"] == 0.84
    assert doktor_trace["accepted"] is True
    assert doktor_trace["score_mode"] == "similarity_higher_is_better"
    
    hasta_trace = next(t for t in rag_traces if t["table"] == "HST_HASTA")
    assert hasta_trace["raw_score"] == 0.60
    assert hasta_trace["accepted"] is False
