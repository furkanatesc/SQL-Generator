import pytest
from app.schema_pruner import CandidateAggregate, CandidateSignal, SOURCE_CAPS

def test_single_signal_uses_cap():
    agg = CandidateAggregate(table="TEST_TABLE")
    
    # exact_column_match cap is 0.60, but signal is 0.90
    agg.add_signal(CandidateSignal(source="exact_column_match", score=0.90, reason="test"))
    
    assert agg.score == 0.60
    
def test_multiple_signals_same_source_use_max():
    agg = CandidateAggregate(table="TEST_TABLE")
    
    agg.add_signal(CandidateSignal(source="exact_column_match", score=0.40, reason="col1"))
    agg.add_signal(CandidateSignal(source="exact_column_match", score=0.60, reason="col2"))
    agg.add_signal(CandidateSignal(source="exact_column_match", score=0.50, reason="col3"))
    
    # Should take the max (0.60), and cap it (0.60).
    assert agg.score == 0.60

def test_multiple_signals_different_sources_are_summed():
    agg = CandidateAggregate(table="TEST_TABLE")
    
    # rag cap is 0.65. signal is 0.50 -> 0.50
    agg.add_signal(CandidateSignal(source="rag", score=0.50, reason="semantic"))
    
    # exact_column_match cap is 0.60. signal is 0.40 -> 0.40
    agg.add_signal(CandidateSignal(source="exact_column_match", score=0.40, reason="col"))
    
    # Total = 0.50 + 0.40 = 0.90
    assert agg.score == 0.90

def test_total_score_cannot_exceed_one():
    agg = CandidateAggregate(table="TEST_TABLE")
    
    agg.add_signal(CandidateSignal(source="exact_table_match", score=1.00, reason="table"))
    agg.add_signal(CandidateSignal(source="rag", score=0.60, reason="rag"))
    
    assert agg.score == 1.00

def test_to_dict_format():
    agg = CandidateAggregate(table="TEST_TABLE")
    agg.add_signal(CandidateSignal(source="rag", score=0.50, reason="semantic"))
    
    data = agg.to_dict()
    assert data["table"] == "TEST_TABLE"
    assert data["final_score"] == 0.50
    assert len(data["signals"]) == 1
    assert data["signals"][0]["source"] == "rag"
    assert data["signals"][0]["score"] == 0.50
