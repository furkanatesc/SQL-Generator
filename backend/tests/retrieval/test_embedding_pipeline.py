import json
import os
import copy
from unittest.mock import MagicMock
import pytest

from app.schema.schema_adapter import from_legacy_schema
from app.schema.schema_contract import DatabaseSchema, TableSchema, ColumnSchema, RelationshipSchema, RelationshipType
from app.retrieval.embedding_provider import FakeEmbeddingProvider
from app.retrieval.embedding_cache import InMemoryEmbeddingCache
from app.retrieval.embedding_pipeline import EmbeddingPipeline, build_embedding_inputs, EmbeddingNonRetryableError

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
    Uses exact count matching to replace weak assertions.
    """
    schema = load_golden_schema()
    inputs = build_embedding_inputs(schema)

    # 1. Total inputs generated should cover tables (8), columns (31), and relationships (6)
    # 8 + 31 + 6 = 45 inputs
    assert len(inputs) == 45

    table_inputs = [inp for inp in inputs if inp.object_type == "table"]
    column_inputs = [inp for inp in inputs if inp.object_type == "column"]
    relationship_inputs = [inp for inp in inputs if inp.object_type == "relationship"]

    assert len(table_inputs) == 8
    assert len(column_inputs) == 31
    assert len(relationship_inputs) == 6

    # Verify subset of expected ids is exactly matched (observability / contract safeguard)
    expected_required_ids = {
        "table:customers",
        "column:customers.email",
        "relationship:orders.customer_id->customers.id|type=explicit|confidence=none",
    }
    assert expected_required_ids <= {inp.id for inp in inputs}

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


def test_relationship_embedding_inputs_are_unique_even_when_relationship_appears_in_two_table_summaries():
    """
    Verifies that relationship inputs are unique and decoupled from the table loop.
    A relationship should produce exactly one EmbeddingInput globally.
    """
    schema = DatabaseSchema(
        dialect="sqlite",
        tables=[
            TableSchema(name="customers", columns=[ColumnSchema(name="id", data_type="INTEGER", primary_key=True)]),
            TableSchema(name="orders", columns=[ColumnSchema(name="customer_id", data_type="INTEGER")])
        ],
        relationships=[
            RelationshipSchema(
                source_table="orders",
                source_column="customer_id",
                target_table="customers",
                target_column="id",
                relationship_type=RelationshipType.EXPLICIT,
                confidence=1.0
            )
        ]
    )
    
    inputs = build_embedding_inputs(schema)
    # Expected: 2 tables, 2 columns, 1 unique relationship = 5 inputs
    assert len(inputs) == 5
    
    rels = [inp for inp in inputs if inp.object_type == "relationship"]
    assert len(rels) == 1
    assert rels[0].id == "relationship:orders.customer_id->customers.id|type=explicit|confidence=1.0"


def test_relationship_embedding_ids_include_type_and_confidence_to_prevent_collision():
    """
    Verifies that identical relationship endpoints with different types or confidences
    generate unique IDs and object IDs instead of colliding.
    """
    schema = DatabaseSchema(
        dialect="sqlite",
        tables=[
            TableSchema(name="customers", columns=[ColumnSchema(name="id", data_type="INTEGER", primary_key=True)]),
            TableSchema(name="orders", columns=[ColumnSchema(name="customer_id", data_type="INTEGER")])
        ],
        relationships=[
            RelationshipSchema(
                source_table="orders",
                source_column="customer_id",
                target_table="customers",
                target_column="id",
                relationship_type=RelationshipType.EXPLICIT,
                confidence=1.0
            ),
            RelationshipSchema(
                source_table="orders",
                source_column="customer_id",
                target_table="customers",
                target_column="id",
                relationship_type=RelationshipType.IMPLICIT,
                confidence=0.72
            )
        ]
    )
    inputs = build_embedding_inputs(schema)
    relationship_inputs = [inp for inp in inputs if inp.object_type == "relationship"]
    
    assert len(relationship_inputs) == 2
    assert len({inp.id for inp in relationship_inputs}) == 2
    assert len({inp.object_id for inp in relationship_inputs}) == 2
    
    ids = {inp.id for inp in relationship_inputs}
    assert "relationship:orders.customer_id->customers.id|type=explicit|confidence=1.0" in ids
    assert "relationship:orders.customer_id->customers.id|type=implicit|confidence=0.72" in ids


def test_relationship_embedding_input_order_is_stable_for_shuffled_relationships():
    """
    Verifies that the relationship inputs list is deterministically and stably sorted
    regardless of how relationships are ordered inside the schema object.
    """
    rel1 = RelationshipSchema(
        source_table="orders",
        source_column="customer_id",
        target_table="customers",
        target_column="id",
        relationship_type=RelationshipType.EXPLICIT,
        confidence=1.0
    )
    rel2 = RelationshipSchema(
        source_table="payments",
        source_column="order_id",
        target_table="orders",
        target_column="id",
        relationship_type=RelationshipType.EXPLICIT,
        confidence=0.9
    )
    
    schema_a = DatabaseSchema(
        dialect="sqlite",
        tables=[
            TableSchema(name="customers", columns=[ColumnSchema(name="id", data_type="INTEGER", primary_key=True)]),
            TableSchema(name="orders", columns=[ColumnSchema(name="id", data_type="INTEGER", primary_key=True), ColumnSchema(name="customer_id", data_type="INTEGER")]),
            TableSchema(name="payments", columns=[ColumnSchema(name="order_id", data_type="INTEGER")])
        ],
        relationships=[rel1, rel2]
    )
    
    schema_b = DatabaseSchema(
        dialect="sqlite",
        tables=[
            TableSchema(name="customers", columns=[ColumnSchema(name="id", data_type="INTEGER", primary_key=True)]),
            TableSchema(name="orders", columns=[ColumnSchema(name="id", data_type="INTEGER", primary_key=True), ColumnSchema(name="customer_id", data_type="INTEGER")]),
            TableSchema(name="payments", columns=[ColumnSchema(name="order_id", data_type="INTEGER")])
        ],
        relationships=[rel2, rel1]
    )
    
    ids_a = [inp.id for inp in build_embedding_inputs(schema_a)]
    ids_b = [inp.id for inp in build_embedding_inputs(schema_b)]
    
    assert ids_a == ids_b


def test_embedding_pipeline_integration_and_cache_invalidation():
    """
    Integration smoke test running the full pipeline:
    DatabaseSchema -> Input Builder -> Pipeline -> Cache -> Record Output.
    Verifies cache hit correctness and exact cache invalidation content under schema drift.
    """
    schema = load_golden_schema()
    
    # Setup offline components
    provider = FakeEmbeddingProvider(dimension=128)
    original_embed_texts = provider.embed_texts
    provider.embed_texts = MagicMock(side_effect=original_embed_texts)
    
    cache = InMemoryEmbeddingCache()
    pipeline = EmbeddingPipeline(provider=provider, cache=cache)

    # === RUN 1: Cache Miss / Initial Run ===
    records = pipeline.process_schema(schema)
    
    # Assert output shape and correctness
    assert len(records) == 45
    for rec in records:
        assert len(rec.vector) == 128
        assert isinstance(rec.vector, tuple)
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
    customers_table = next(t for t in drifted_schema.tables if t.name == "customers")
    customers_table.columns.append(ColumnSchema(name="phone_number", data_type="VARCHAR"))

    records_drifted = pipeline.process_schema(drifted_schema)
    
    # Total records should reflect the new column
    assert len(records_drifted) == 46
    # The provider should have been called again (call_count incremented)
    assert provider.embed_texts.call_count == initial_call_count + 1

    # Assert exact cache-miss texts sent to the provider
    miss_texts = provider.embed_texts.call_args_list[-1].args[0]
    assert any("COLUMN customers.phone_number" in t for t in miss_texts)
    assert any("TABLE customers" in t for t in miss_texts)
    assert not any("COLUMN customers.email" in t for t in miss_texts)

    # === RUN 4: Provider/Model Invalidation ===
    new_provider = FakeEmbeddingProvider(model_id="fake_model_v2", dimension=128)
    new_provider.embed_texts = MagicMock(side_effect=new_provider.embed_texts)
    new_pipeline = EmbeddingPipeline(provider=new_provider, cache=cache)

    records_new_model = new_pipeline.process_schema(schema)
    assert len(records_new_model) == 45
    assert new_provider.embed_texts.call_count == 1


def test_pipeline_rejects_provider_vector_count_mismatch():
    """
    Verifies that pipeline rejects output if the provider returns fewer/more vectors than requested.
    """
    schema = load_golden_schema()
    provider = FakeEmbeddingProvider(dimension=128)
    provider.embed_texts = MagicMock(return_value=[[0.0]*128] * 44) # 44 vectors instead of 45
    
    pipeline = EmbeddingPipeline(provider=provider)
    with pytest.raises(EmbeddingNonRetryableError, match="Embedding provider returned 44 vectors for 45 inputs"):
        pipeline.process_schema(schema)


def test_pipeline_rejects_provider_dimension_mismatch():
    """
    Verifies that pipeline rejects output if a vector's dimension does not match the provider's dimension.
    """
    schema = load_golden_schema()
    provider = FakeEmbeddingProvider(dimension=128)
    provider.embed_texts = MagicMock(return_value=[[0.0]*64] * 45) # 64 dimension instead of 128
    
    pipeline = EmbeddingPipeline(provider=provider)
    with pytest.raises(EmbeddingNonRetryableError, match="Embedding dimension mismatch for"):
        pipeline.process_schema(schema)


def test_pipeline_clock_injection():
    """
    Verifies clock injection behaves deterministically.
    """
    schema = load_golden_schema()
    provider = FakeEmbeddingProvider(dimension=128)
    dummy_clock = MagicMock(return_value=987654.321)
    
    pipeline = EmbeddingPipeline(provider=provider, clock=dummy_clock)
    records = pipeline.process_schema(schema)
    
    assert len(records) == 45
    for rec in records:
        assert rec.created_at == 987654.321
    assert dummy_clock.call_count == 45


def test_pipeline_rejects_corrupt_cached_record_with_wrong_schema_hash():
    """
    Verifies that pipeline validates cached record fields and rejects records with mismatched schema hashes.
    """
    schema = load_golden_schema()
    provider = FakeEmbeddingProvider(dimension=128)
    cache = InMemoryEmbeddingCache()
    pipeline = EmbeddingPipeline(provider=provider, cache=cache)
    
    # Run once to populate cache
    pipeline.process_schema(schema)
    
    # Mutate a cached record to corrupt its schema hash
    inputs = build_embedding_inputs(schema)
    corrupt_inp = inputs[0]
    from app.retrieval.embedding_cache import build_cache_key, EmbeddingRecord
    key = build_cache_key(
        provider_id=provider.provider_id,
        model_id=provider.model_id,
        dimension=provider.dimension,
        summary_version=corrupt_inp.summary_version,
        schema_hash=corrupt_inp.schema_hash,
        object_id=corrupt_inp.object_id
    )
    
    cached_rec = cache.get(key)
    corrupt_rec = EmbeddingRecord(
        id=cached_rec.id,
        text=cached_rec.text,
        vector=cached_rec.vector,
        summary_version=cached_rec.summary_version,
        schema_hash="corrupt_hash_val",  # changed
        provider_id=cached_rec.provider_id,
        model_id=cached_rec.model_id,
        dimension=cached_rec.dimension,
        created_at=cached_rec.created_at
    )
    cache.set(key, corrupt_rec)
    
    with pytest.raises(EmbeddingNonRetryableError, match="Cached record schema hash mismatch"):
        pipeline.process_schema(schema)


def test_pipeline_rejects_corrupt_cached_record_with_wrong_dimension():
    """
    Verifies that pipeline validates cached record fields and rejects records with mismatched dimensions.
    """
    schema = load_golden_schema()
    provider = FakeEmbeddingProvider(dimension=128)
    cache = InMemoryEmbeddingCache()
    pipeline = EmbeddingPipeline(provider=provider, cache=cache)
    
    # Run once to populate cache
    pipeline.process_schema(schema)
    
    # Mutate a cached record to corrupt its dimension metadata
    inputs = build_embedding_inputs(schema)
    corrupt_inp = inputs[0]
    from app.retrieval.embedding_cache import build_cache_key, EmbeddingRecord
    key = build_cache_key(
        provider_id=provider.provider_id,
        model_id=provider.model_id,
        dimension=provider.dimension,
        summary_version=corrupt_inp.summary_version,
        schema_hash=corrupt_inp.schema_hash,
        object_id=corrupt_inp.object_id
    )
    
    cached_rec = cache.get(key)
    corrupt_rec = EmbeddingRecord(
        id=cached_rec.id,
        text=cached_rec.text,
        vector=cached_rec.vector + (0.0,), # wrong vector size
        summary_version=cached_rec.summary_version,
        schema_hash=cached_rec.schema_hash,
        provider_id=cached_rec.provider_id,
        model_id=cached_rec.model_id,
        dimension=cached_rec.dimension + 1, # wrong dimension
        created_at=cached_rec.created_at
    )
    cache.set(key, corrupt_rec)
    
    with pytest.raises(EmbeddingNonRetryableError, match="Cached record dimension mismatch"):
        pipeline.process_schema(schema)


def test_nvidia_provider_dimension_metadata_is_enforced_by_pipeline():
    """
    Verifies that the pipeline enforces the NVIDIA provider dimension metadata check on mock responses.
    """
    from app.retrieval.nvidia_embedding_provider import NVIDIAEmbeddingProvider
    provider = NVIDIAEmbeddingProvider(api_key="fake")
    provider.embed_texts = MagicMock(side_effect=lambda texts: [[0.0] * 999] * len(texts))
    
    schema = DatabaseSchema(
        dialect="sqlite",
        tables=[
            TableSchema(name="customers", columns=[ColumnSchema(name="id", data_type="INTEGER", primary_key=True)])
        ]
    )
    
    pipeline = EmbeddingPipeline(provider=provider)
    with pytest.raises(EmbeddingNonRetryableError, match="Embedding dimension mismatch"):
        pipeline.process_schema(schema)
