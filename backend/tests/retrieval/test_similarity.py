import pytest
from app.retrieval.similarity import cosine_similarity
from app.retrieval.embedding_pipeline import EmbeddingNonRetryableError

def test_cosine_similarity_identical_vectors_returns_1():
    v1 = (1.0, 2.0, 3.0)
    v2 = (1.0, 2.0, 3.0)
    assert pytest.approx(cosine_similarity(v1, v2), abs=1e-6) == 1.0

def test_cosine_similarity_opposite_vectors_returns_negative_1():
    v1 = (1.0, 2.0, 3.0)
    v2 = (-1.0, -2.0, -3.0)
    assert pytest.approx(cosine_similarity(v1, v2), abs=1e-6) == -1.0

def test_cosine_similarity_orthogonal_vectors_returns_0():
    v1 = (1.0, 0.0)
    v2 = (0.0, 1.0)
    assert pytest.approx(cosine_similarity(v1, v2), abs=1e-6) == 0.0

def test_cosine_similarity_rejects_dimension_mismatch():
    v1 = (1.0, 2.0)
    v2 = (1.0, 2.0, 3.0)
    with pytest.raises(EmbeddingNonRetryableError, match="Dimension mismatch"):
        cosine_similarity(v1, v2)

def test_cosine_similarity_rejects_zero_vector():
    v1 = (0.0, 0.0, 0.0)
    v2 = (1.0, 2.0, 3.0)
    with pytest.raises(EmbeddingNonRetryableError, match="Zero norm vector detected"):
        cosine_similarity(v1, v2)
        
    v3 = (1.0, 2.0, 3.0)
    v4 = (0.0, 0.0, 0.0)
    with pytest.raises(EmbeddingNonRetryableError, match="Zero norm vector detected"):
        cosine_similarity(v3, v4)
