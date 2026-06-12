import json
import os
import copy
from unittest.mock import MagicMock
import pytest

from app.schema.schema_adapter import from_legacy_schema
from app.schema.schema_contract import DatabaseSchema, TableSchema, ColumnSchema
from app.retrieval.embedding_provider import FakeEmbeddingProvider
from app.retrieval.embedding_cache import InMemoryEmbeddingCache
from app.retrieval.embedding_pipeline import EmbeddingPipeline, build_embedding_inputs

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")
GOLDEN_SCHEMA_PATH = os.path.join(FIXTURES_DIR, "schema", "context_selection_golden_schema.json")


def load_golden_schema() -> DatabaseSchema:
    with open(GOLDEN_SCHEMA_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return from_legacy_schema(raw, dialect="sqlite")


def test_build_embedding_inputs():
    """
    Verifies that build_embedding_inputs correctly parses a DatabaseSchema
    into EmbeddingInput structures with appropriate metadata, types, and summary_version.
    """
    schema = load_golden_schema()
    inputs = build_embedding_inputs(schema)

    # 1. Total inputs generated should cover tables, columns, and relationships
    assert len(inputs) > 0

    # 2. Check metadata on a table input
    table_input = next(inp for inp in inputs if inp.object_type == "table" and inp.object_id == "customers")
    assert table_input.summary_version == "schema_summary_v1"
    assert "TABLE customers" in table_input.text
    assert table_input.id == "table:customers"
    assert len(table_input.schema_hash) == 64  # SHA-256 length

    # 3. Check metadata on a column input
    col_input = next(inp for inp in inputs if inp.object_type == "column" and inp.object_id == "customers.email")
    assert col_input.summary_version == "schema_summary_v1"
    assert "COLUMN customers.email" in col_input.text
    assert col_input.id == "column:customers.email"
    assert len(col_input.schema_hash) == 64

    # 4. Check metadata on a relationship input
    rel_input = next(inp for inp in inputs if inp.object_type == "relationship")
    assert rel_input.summary_version == "schema_summary_v1"
    assert "RELATIONSHIP" in rel_input.text
    assert rel_input.id.startswith("relationship:")
    assert len(rel_input.schema_hash) == 64


def test_embedding_pipeline_integration_and_cache_invalidation():
    """
    Integration smoke test running the full pipeline:
    DatabaseSchema -> Input Builder -> Pipeline -> Cache -> Record Output.
    Verifies cache hit correctness and cache invalidation under schema drift.
    """
    schema = load_golden_schema()
    
    # Setup offline components
    provider = FakeEmbeddingProvider(dimension=128)
    # Spy on the provider's embed_texts call using unittest.mock
    original_embed_texts = provider.embed_texts
    provider.embed_texts = MagicMock(side_effect=original_embed_texts)
    
    cache = InMemoryEmbeddingCache()
    pipeline = EmbeddingPipeline(provider=provider, cache=cache)

    # === RUN 1: Cache Miss / Initial Run ===
    records = pipeline.process_schema(schema)
    
    # Assert output shape and correctness
    assert len(records) > 0
    for rec in records:
        assert len(rec.vector) == 128
        assert rec.summary_version == "schema_summary_v1"
        assert rec.provider_id == "fake_provider"
        assert rec.model_id == "fake_model"
        assert len(rec.schema_hash) == 64

    # The provider should be called exactly once to batch embed all uncached texts
    assert provider.embed_texts.call_count == 1
    initial_call_count = provider.embed_texts.call_count

    # === RUN 2: Cache Hit ===
    records_cache = pipeline.process_schema(schema)
    
    assert len(records_cache) == len(records)
    # No new provider calls should be made since all inputs are cached
    assert provider.embed_texts.call_count == initial_call_count

    # === RUN 3: Schema Drift / Cache Invalidation ===
    # Create a copy of the schema and mutate a single table structure
    drifted_schema = copy.deepcopy(schema)
    # Add a column to the 'customers' table
    customers_table = next(t for t in drifted_schema.tables if t.name == "customers")
    customers_table.columns.append(ColumnSchema(name="phone_number", data_type="VARCHAR"))

    records_drifted = pipeline.process_schema(drifted_schema)
    
    # Total records should reflect the new column
    assert len(records_drifted) > len(records)
    # The provider should have been called again (call_count incremented)
    # to embed only the newly mutated/added components
    assert provider.embed_texts.call_count == initial_call_count + 1

    # === RUN 4: Provider/Model Invalidation ===
    # Create a new pipeline with a different model_id but same cache
    new_provider = FakeEmbeddingProvider(model_id="fake_model_v2", dimension=128)
    new_provider.embed_texts = MagicMock(side_effect=new_provider.embed_texts)
    new_pipeline = EmbeddingPipeline(provider=new_provider, cache=cache)

    records_new_model = new_pipeline.process_schema(schema)
    # Cache key changes on model_id signature, causing complete cache miss
    assert len(records_new_model) == len(records)
    assert new_provider.embed_texts.call_count == 1
