import json
import os
import pytest
from app.schema.schema_adapter import from_legacy_schema
from app.schema.schema_contract import DatabaseSchema
from app.retrieval.embedding_provider import FakeEmbeddingProvider
from app.retrieval.embedding_cache import InMemoryEmbeddingCache
from app.retrieval.embedding_pipeline import EmbeddingPipeline
from app.retrieval.retrieval_contract import RetrievalQuery
from app.retrieval.top_k_retriever import InMemoryTopKRetriever

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")
GOLDEN_SCHEMA_PATH = os.path.join(FIXTURES_DIR, "schema", "context_selection_golden_schema.json")


def load_golden_schema() -> DatabaseSchema:
    with open(GOLDEN_SCHEMA_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return from_legacy_schema(raw, dialect="sqlite")


def test_embedding_pipeline_to_top_k_retrieval_smoke():
    """
    E2E offline smoke test:
    Loads a golden schema, runs the embedding pipeline with FakeEmbeddingProvider (seeded, deterministic),
    embeds a sample user query, queries the InMemoryTopKRetriever, and asserts deterministic top-5 candidates.
    """
    # 1. Load schema
    schema = load_golden_schema()
    
    # 2. Build EmbeddingRecords
    provider = FakeEmbeddingProvider(dimension=128)
    cache = InMemoryEmbeddingCache()
    pipeline = EmbeddingPipeline(provider=provider, cache=cache)
    records = pipeline.process_schema(schema)
    
    assert len(records) == 45
    
    # 3. Embed query text with same FakeEmbeddingProvider
    query_text = "List customers with unpaid orders"
    query_vector_batch = provider.embed_texts([query_text])
    query_vector = tuple(query_vector_batch[0])
    
    assert len(query_vector) == 128
    
    # 4. Perform Top-5 retrieval
    retriever = InMemoryTopKRetriever()
    query = RetrievalQuery(
        query_text=query_text,
        query_vector=query_vector,
        k=5,
        allowed_object_types=("table", "column", "relationship")
    )
    
    result = retriever.retrieve(query, records)
    
    # 5. Assert result metadata
    assert result.query_text == query_text
    assert result.k_requested == 5
    assert result.k_returned == 5
    assert len(result.candidates) == 5
    assert result.retrieval_version == "top_k_retrieval_v1"
    
    # 6. Assert sorting and rank indices
    previous_score = 2.0  # max possible cosine is 1.0
    for idx, candidate in enumerate(result.candidates):
        assert candidate.rank == idx + 1
        assert candidate.score <= previous_score
        previous_score = candidate.score
        
        # 7. Assert candidate metadata is fully preserved
        assert candidate.summary_version == "schema_summary_v1"
        assert len(candidate.schema_hash) == 64
        assert candidate.provider_id == "fake_provider"
        assert candidate.model_id == "fake_model"
        assert candidate.dimension == 128
