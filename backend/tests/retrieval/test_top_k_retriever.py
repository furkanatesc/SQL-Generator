import pytest
from app.retrieval.embedding_cache import EmbeddingRecord
from app.retrieval.retrieval_contract import RetrievalQuery
from app.retrieval.top_k_retriever import InMemoryTopKRetriever
from app.retrieval.embedding_pipeline import EmbeddingNonRetryableError

def build_mock_record(rec_id: str, vector: tuple, dimension: int = 3) -> EmbeddingRecord:
    return EmbeddingRecord(
        id=rec_id,
        text=f"Summary of {rec_id}",
        vector=vector,
        summary_version="schema_summary_v1",
        schema_hash="fake_hash",
        provider_id="fake_provider",
        model_id="fake_model",
        dimension=dimension,
        created_at=12345.67
    )

def test_retriever_rejects_k_zero():
    retriever = InMemoryTopKRetriever()
    query = RetrievalQuery(query_text="test", query_vector=(1.0, 0.0), k=0)
    record = build_mock_record("table:test", (1.0, 0.0), dimension=2)
    with pytest.raises(EmbeddingNonRetryableError, match="k must be greater than zero"):
        retriever.retrieve(query, [record])

def test_retriever_rejects_negative_k():
    retriever = InMemoryTopKRetriever()
    query = RetrievalQuery(query_text="test", query_vector=(1.0, 0.0), k=-5)
    record = build_mock_record("table:test", (1.0, 0.0), dimension=2)
    with pytest.raises(EmbeddingNonRetryableError, match="k must be greater than zero"):
        retriever.retrieve(query, [record])

def test_retriever_rejects_empty_allowed_object_types():
    retriever = InMemoryTopKRetriever()
    query = RetrievalQuery(query_text="test", query_vector=(1.0, 0.0), k=2, allowed_object_types=())
    record = build_mock_record("table:test", (1.0, 0.0), dimension=2)
    with pytest.raises(EmbeddingNonRetryableError, match="allowed_object_types cannot be empty"):
        retriever.retrieve(query, [record])

def test_retriever_rejects_query_dimension_mismatch():
    retriever = InMemoryTopKRetriever()
    query = RetrievalQuery(query_text="test", query_vector=(1.0, 0.0, 0.0), k=2) # size 3
    record = build_mock_record("table:test", (1.0, 0.0), dimension=2) # size 2
    with pytest.raises(EmbeddingNonRetryableError, match="Dimension mismatch between query and record"):
        retriever.retrieve(query, [record])

def test_retriever_rejects_record_dimension_mismatch():
    retriever = InMemoryTopKRetriever()
    query = RetrievalQuery(query_text="test", query_vector=(1.0, 0.0), k=2)
    # record with actual vector size 3 but metadata dimension 2
    record = build_mock_record("table:test", (1.0, 0.0, 0.0), dimension=2)
    with pytest.raises(EmbeddingNonRetryableError, match="Dimension mismatch in record table:test: expected=2, actual=3"):
        retriever.retrieve(query, [record])

def test_retriever_rejects_duplicate_candidate_ids():
    retriever = InMemoryTopKRetriever()
    query = RetrievalQuery(query_text="test", query_vector=(1.0, 0.0), k=2)
    record1 = build_mock_record("table:test", (1.0, 0.0), dimension=2)
    record2 = build_mock_record("table:test", (0.0, 1.0), dimension=2)
    with pytest.raises(EmbeddingNonRetryableError, match="Duplicate candidate ID detected in records: table:test"):
        retriever.retrieve(query, [record1, record2])

def test_retriever_rejects_zero_vector_query():
    retriever = InMemoryTopKRetriever()
    query = RetrievalQuery(query_text="test", query_vector=(0.0, 0.0), k=2)
    record = build_mock_record("table:test", (1.0, 0.0), dimension=2)
    with pytest.raises(EmbeddingNonRetryableError, match="Query vector cannot be a zero-norm vector"):
        retriever.retrieve(query, [record])

def test_retriever_returns_top_k_by_score_desc():
    retriever = InMemoryTopKRetriever()
    query = RetrievalQuery(query_text="test", query_vector=(1.0, 0.0), k=2)
    
    # record1 has score 1.0 (exact match)
    record1 = build_mock_record("table:best", (1.0, 0.0), dimension=2)
    # record2 has score 0.0 (orthogonal)
    record2 = build_mock_record("table:worst", (0.0, 1.0), dimension=2)
    # record3 has score 0.707
    record3 = build_mock_record("table:mid", (0.707, 0.707), dimension=2)
    
    result = retriever.retrieve(query, [record2, record1, record3])
    
    assert result.k_requested == 2
    assert result.k_returned == 2
    assert len(result.candidates) == 2
    
    assert result.candidates[0].id == "table:best"
    assert result.candidates[0].rank == 1
    assert pytest.approx(result.candidates[0].score, abs=1e-3) == 1.0
    
    assert result.candidates[1].id == "table:mid"
    assert result.candidates[1].rank == 2
    assert pytest.approx(result.candidates[1].score, abs=1e-3) == 0.707

def test_retriever_uses_id_ascending_tie_break():
    retriever = InMemoryTopKRetriever()
    query = RetrievalQuery(query_text="test", query_vector=(1.0, 0.0), k=3)
    
    # All records have identical score of 1.0
    record_b = build_mock_record("table:b", (1.0, 0.0), dimension=2)
    record_c = build_mock_record("table:c", (1.0, 0.0), dimension=2)
    record_a = build_mock_record("table:a", (1.0, 0.0), dimension=2)
    
    result = retriever.retrieve(query, [record_c, record_b, record_a])
    
    assert result.k_returned == 3
    assert result.candidates[0].id == "table:a"
    assert result.candidates[1].id == "table:b"
    assert result.candidates[2].id == "table:c"

def test_retriever_returns_less_than_k_when_records_are_fewer():
    retriever = InMemoryTopKRetriever()
    query = RetrievalQuery(query_text="test", query_vector=(1.0, 0.0), k=10) # k=10
    record = build_mock_record("table:test", (1.0, 0.0), dimension=2) # only 1 record
    
    result = retriever.retrieve(query, [record])
    assert result.k_requested == 10
    assert result.k_returned == 1
    assert len(result.candidates) == 1
    assert result.candidates[0].id == "table:test"

def test_retriever_filters_by_allowed_object_types():
    retriever = InMemoryTopKRetriever()
    
    record_table = build_mock_record("table:customers", (1.0, 0.0), dimension=2)
    record_column = build_mock_record("column:customers.id", (0.0, 1.0), dimension=2)
    record_relationship = build_mock_record("relationship:orders.cust->cust.id", (1.0, 0.0), dimension=2)
    
    # Query allows only table and relationship
    query = RetrievalQuery(
        query_text="test",
        query_vector=(1.0, 0.0),
        k=5,
        allowed_object_types=("table", "relationship")
    )
    
    result = retriever.retrieve(query, [record_table, record_column, record_relationship])
    
    # column:customers.id must be filtered out
    assert result.k_returned == 2
    assert {c.id for c in result.candidates} == {"table:customers", "relationship:orders.cust->cust.id"}

def test_retriever_preserves_record_metadata():
    retriever = InMemoryTopKRetriever()
    query = RetrievalQuery(query_text="test", query_vector=(1.0, 0.0), k=1)
    
    record = EmbeddingRecord(
        id="table:customers",
        text="customers table summary info",
        vector=(1.0, 0.0),
        summary_version="schema_summary_v1_custom",
        schema_hash="hash_value_123",
        provider_id="provider_abc",
        model_id="model_xyz",
        dimension=2,
        created_at=9999.99
    )
    
    result = retriever.retrieve(query, [record])
    assert result.k_returned == 1
    
    candidate = result.candidates[0]
    assert candidate.id == "table:customers"
    assert candidate.object_id == "customers"
    assert candidate.object_type == "table"
    assert candidate.text == "customers table summary info"
    assert candidate.summary_version == "schema_summary_v1_custom"
    assert candidate.schema_hash == "hash_value_123"
    assert candidate.provider_id == "provider_abc"
    assert candidate.model_id == "model_xyz"
    assert candidate.dimension == 2
    assert candidate.rank == 1

def test_retriever_assigns_rank_starting_from_1():
    retriever = InMemoryTopKRetriever()
    query = RetrievalQuery(query_text="test", query_vector=(1.0, 0.0), k=5)
    
    records = [
        build_mock_record("table:a", (1.0, 0.0), dimension=2),
        build_mock_record("table:b", (0.9, 0.1), dimension=2),
        build_mock_record("table:c", (0.8, 0.2), dimension=2)
    ]
    
    result = retriever.retrieve(query, records)
    assert result.k_returned == 3
    assert result.candidates[0].rank == 1
    assert result.candidates[1].rank == 2
    assert result.candidates[2].rank == 3
