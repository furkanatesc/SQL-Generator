import pytest
from unittest.mock import patch, MagicMock
from app.schema_pruner import SchemaPruner
from app.schema_candidates import CandidateAggregate, CandidateSignal

def test_rag_score_threshold_rejects_low_score():
    pruner = SchemaPruner()
    mock_schema = {"tables": {"HST_HASTA": {"columns": []}}}
    
    with patch('app.rag_manager.RAGManager') as MockRAG:
        mock_rag = MockRAG.return_value
        mock_rag.search_ddl.return_value = [{"payload": {"table_name": "HST_HASTA"}, "score": 0.71}]
        
        candidates, trace = pruner.resolve_entities({"natural_query": "alakasiz_sorgu"}, mock_schema)
        
        # Should be rejected
        assert not any(c.table == "HST_HASTA" for c in candidates)
        hasta_trace = next((t for t in trace["rag_matches"] if t["table"] == "HST_HASTA"), None)
        assert hasta_trace is not None
        assert hasta_trace["accepted"] is False

def test_rag_score_threshold_accepts_high_score():
    pruner = SchemaPruner()
    mock_schema = {"tables": {"HST_HASTA": {"columns": []}}}
    
    with patch('app.rag_manager.RAGManager') as MockRAG:
        mock_rag = MockRAG.return_value
        mock_rag.search_ddl.return_value = [{"payload": {"table_name": "HST_HASTA"}, "score": 0.72}]
        
        candidates, trace = pruner.resolve_entities({"natural_query": "alakasiz_sorgu"}, mock_schema)
        
        hasta_cand = next((c for c in candidates if c.table == "HST_HASTA"), None)
        assert hasta_cand is not None
        hasta_trace = next((t for t in trace["rag_matches"] if t["table"] == "HST_HASTA"), None)
        assert hasta_trace is not None
        assert hasta_trace["accepted"] is True

def test_signal_aggregation_schema_lexicon_and_rag():
    pruner = SchemaPruner()
    mock_schema = {
        "tables": {
            "HST_DOKTOR": {
                "columns": [{"name": "doktor_id"}],
                "foreign_keys": []
            }
        }
    }
    
    with patch('app.rag_manager.RAGManager') as MockRAG:
        mock_rag = MockRAG.return_value
        # RAG gives a score of 0.80
        mock_rag.search_ddl.return_value = [{"payload": {"table_name": "HST_DOKTOR"}, "score": 0.80}]
        
        # Query will trigger schema_lexicon for "doktor" AND rag
        aqr = {"natural_query": "doktor", "entities": ["doktor"]}
        candidates, trace = pruner.resolve_entities(aqr, mock_schema)
        
        doktor_cand = next(c for c in candidates if c.table == "HST_DOKTOR")
        # Ensure it has both signals
        sources = [s.source for s in doktor_cand.signals]
        assert "schema_lexicon" in sources
        assert "rag" in sources
        
        # Final score should be min(0.85 (lexicon cap) + 0.65 (rag cap), 1.0) => 1.0, 
        # Actually RAG signal is 0.80 -> capped at 0.65. Lexicon signal is 0.80 -> capped at 0.85. 
        # Total = 0.65 + 0.80 = 1.45 -> capped at 1.0.
        assert doktor_cand.score == 1.0

@patch('app.rag_manager.RAGManager')
def test_ver_does_not_select_per_vergiiade(mock_rag):
    pruner = SchemaPruner()
    mock_rag_instance = MagicMock()
    mock_rag_instance.search_ddl.return_value = []
    mock_rag.return_value = mock_rag_instance
    
    mock_schema = {
        "tables": {
            "PER_VERGIIADE": {"columns": [{"name": "id"}]}
        }
    }
    
    aqr = {
        "natural_query": "bana kardiyoloji doktorlarını getiren sorguyu ver",
        "entities": ["bana kardiyoloji doktorlarını getiren sorguyu ver"]
    }
    
    candidates, _ = pruner.resolve_entities(aqr, mock_schema)
    
    # PER_VERGIIADE should not be selected
    assert not any(c.table == "PER_VERGIIADE" for c in candidates)

@patch('app.rag_manager.RAGManager')
def test_doktor_selected_without_rag(mock_rag):
    pruner = SchemaPruner()
    mock_rag_instance = MagicMock()
    mock_rag_instance.search_ddl.return_value = []
    mock_rag.return_value = mock_rag_instance
    
    mock_schema = {
        "tables": {
            "HST_DOKTOR": {
                "columns": [{"name": "doktor_id"}],
                "foreign_keys": []
            }
        }
    }
    
    aqr = {
        "natural_query": "doktor listele",
        "entities": ["doktor listele"]
    }
    
    candidates, _ = pruner.resolve_entities(aqr, mock_schema)
    
    doktor_cand = next((c for c in candidates if c.table == "HST_DOKTOR"), None)
    assert doktor_cand is not None
    assert "schema_lexicon" in [s.source for s in doktor_cand.signals]
