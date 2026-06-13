import time
import random
import logging
from dataclasses import dataclass
from typing import Literal, List, Callable
from app.schema.schema_contract import DatabaseSchema
from app.retrieval.embedding_provider import EmbeddingProvider
from app.retrieval.embedding_cache import EmbeddingCache, EmbeddingRecord, build_cache_key

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Base exception for all embedding-related errors."""
    pass


class EmbeddingRetryableError(EmbeddingError):
    """Exception indicating a transient, retryable error (timeouts, rate limits, 5xx)."""
    pass


class EmbeddingNonRetryableError(EmbeddingError):
    """Exception indicating a permanent, non-retryable error (auth failure, bad requests)."""
    pass


@dataclass(frozen=True)
class EmbeddingInput:
    """
    Structured representation of the schema item summary ready to be embedded.
    """
    id: str
    text: str
    summary_version: str
    schema_hash: str
    object_type: Literal["table", "column", "relationship"]
    object_id: str


def build_embedding_inputs(schema: DatabaseSchema) -> List[EmbeddingInput]:
    """
    Transforms a DatabaseSchema into a list of structured EmbeddingInputs.
    Uses summarize_database_schema from Sprint 21.0 to get deterministic summaries.
    """
    from app.schema.schema_summary import summarize_database_schema, summarize_relationship
    from app.retrieval.embedding_hash import compute_summary_hash

    table_summaries = summarize_database_schema(schema)
    inputs = []

    # 1. Generate table and column inputs
    for table in table_summaries:
        # Table summary input
        table_hash = compute_summary_hash(table.summary_text, table.summary_version)
        inputs.append(EmbeddingInput(
            id=f"table:{table.table_name}",
            text=table.summary_text,
            summary_version=table.summary_version,
            schema_hash=table_hash,
            object_type="table",
            object_id=table.table_name
        ))

        # Column summary inputs
        for col in table.columns:
            col_hash = compute_summary_hash(col.summary_text, col.summary_version)
            inputs.append(EmbeddingInput(
                id=f"column:{table.table_name}.{col.column_name}",
                text=col.summary_text,
                summary_version=col.summary_version,
                schema_hash=col_hash,
                object_type="column",
                object_id=f"{table.table_name}.{col.column_name}"
            ))

    # 2. Generate relationship inputs uniquely from canonical relationships
    all_rels = schema.relationships or []
    if schema.graph and schema.graph.edges:
        if not all_rels:
            all_rels = schema.graph.edges

    relationship_summaries = []
    seen_rels = set()
    for rel in all_rels:
        rel_summary = summarize_relationship(rel)
        rel_key = (
            rel_summary.source_table,
            rel_summary.source_column,
            rel_summary.target_table,
            rel_summary.target_column,
            rel_summary.relationship_type,
            rel_summary.confidence,
        )
        if rel_key not in seen_rels:
            seen_rels.add(rel_key)
            relationship_summaries.append(rel_summary)

    # Apply deterministic stable sorting to unique relationships
    sorted_rels = sorted(
        relationship_summaries,
        key=lambda r: (
            r.source_table,
            r.source_column,
            r.target_table,
            r.target_column,
            r.relationship_type,
            -1.0 if r.confidence is None else r.confidence,
        )
    )

    # Map sorted relationships to EmbeddingInputs
    for rel_summary in sorted_rels:
        confidence_val = rel_summary.confidence if rel_summary.confidence is not None else 'none'
        rel_id = f"relationship:{rel_summary.source_table}.{rel_summary.source_column}->{rel_summary.target_table}.{rel_summary.target_column}|type={rel_summary.relationship_type}|confidence={confidence_val}"
        rel_obj_id = f"{rel_summary.source_table}.{rel_summary.source_column}->{rel_summary.target_table}.{rel_summary.target_column}|type={rel_summary.relationship_type}|confidence={confidence_val}"
        
        rel_hash = compute_summary_hash(rel_summary.summary_text, rel_summary.summary_version)
        inputs.append(EmbeddingInput(
            id=rel_id,
            text=rel_summary.summary_text,
            summary_version=rel_summary.summary_version,
            schema_hash=rel_hash,
            object_type="relationship",
            object_id=rel_obj_id
        ))

    # Check for duplicate input IDs and fail-fast
    input_ids = [inp.id for inp in inputs]
    if len(input_ids) != len(set(input_ids)):
        raise EmbeddingNonRetryableError("Duplicate embedding input ids detected")

    return inputs


def execute_with_retry(func, max_attempts: int = 3, base_delay_ms: float = 200, jitter: bool = True):
    """
    Helper function executing the given callable with exponential backoff and optional jitter.
    Knows only about EmbeddingRetryableError and EmbeddingNonRetryableError.
    """
    attempt = 0
    while attempt < max_attempts:
        try:
            return func()
        except EmbeddingRetryableError as e:
            attempt += 1
            if attempt >= max_attempts:
                raise EmbeddingError(f"Max attempts ({max_attempts}) reached. Last error: {e}") from e
            delay = (base_delay_ms / 1000.0) * (2 ** (attempt - 1))
            if jitter:
                delay += random.uniform(0.01, 0.1)
            logger.warning(f"Embedding transient failure. Retrying in {delay:.3f}s... (Attempt {attempt}/{max_attempts})")
            time.sleep(delay)
        except EmbeddingNonRetryableError as e:
            raise e
        except Exception as e:
            # Wrap any other unexpected errors in EmbeddingNonRetryableError
            raise EmbeddingNonRetryableError(f"Unexpected error during execution: {e}") from e


class EmbeddingPipeline:
    """
    Embedding pipeline orchestrating provider call with caching, invalidation, and retries.
    """
    def __init__(self, provider: EmbeddingProvider, cache: EmbeddingCache = None, clock: Callable[[], float] = time.time):
        self.provider = provider
        self.cache = cache
        self.clock = clock

    def process_schema(self, schema: DatabaseSchema) -> List[EmbeddingRecord]:
        """
        Processes a DatabaseSchema: builds inputs, resolves cache, runs provider for cache misses,
        caches new values, and returns all records.
        """
        inputs = build_embedding_inputs(schema)
        
        # Double check for duplicate input IDs
        input_ids = [inp.id for inp in inputs]
        if len(input_ids) != len(set(input_ids)):
            raise EmbeddingNonRetryableError("Duplicate embedding input ids detected")

        records = []
        uncached_inputs = []
        uncached_keys = []

        # 1. Resolve cache hits
        for inp in inputs:
            key = build_cache_key(
                provider_id=self.provider.provider_id,
                model_id=self.provider.model_id,
                dimension=self.provider.dimension,
                summary_version=inp.summary_version,
                schema_hash=inp.schema_hash,
                object_id=inp.object_id
            )
            
            record = None
            if self.cache:
                record = self.cache.get(key)
                
            if record:
                # Strict validation of cached record against input and provider parameters
                if record.id != inp.id:
                    raise EmbeddingNonRetryableError(f"Cached record ID mismatch: expected {inp.id}, got {record.id}")
                if record.schema_hash != inp.schema_hash:
                    raise EmbeddingNonRetryableError(f"Cached record schema hash mismatch: expected {inp.schema_hash}, got {record.schema_hash}")
                if record.provider_id != self.provider.provider_id:
                    raise EmbeddingNonRetryableError(f"Cached record provider ID mismatch: expected {self.provider.provider_id}, got {record.provider_id}")
                if record.model_id != self.provider.model_id:
                    raise EmbeddingNonRetryableError(f"Cached record model ID mismatch: expected {self.provider.model_id}, got {record.model_id}")
                if record.dimension != self.provider.dimension:
                    raise EmbeddingNonRetryableError(f"Cached record dimension mismatch: expected {self.provider.dimension}, got {record.dimension}")
                if len(record.vector) != self.provider.dimension:
                    raise EmbeddingNonRetryableError(f"Cached record vector length mismatch: expected {self.provider.dimension}, got {len(record.vector)}")
                
                records.append(record)
            else:
                uncached_inputs.append(inp)
                uncached_keys.append(key)

        # 2. Process cache misses
        if uncached_inputs:
            texts = [inp.text for inp in uncached_inputs]
            
            def call_provider():
                return self.provider.embed_texts(texts)

            vectors = execute_with_retry(call_provider)

            # Validate output count
            if len(vectors) != len(uncached_inputs):
                raise EmbeddingNonRetryableError(
                    f"Embedding provider returned {len(vectors)} vectors for {len(uncached_inputs)} inputs"
                )

            # Validate dimensions and create records
            for inp, key, vec in zip(uncached_inputs, uncached_keys, vectors):
                if len(vec) != self.provider.dimension:
                    raise EmbeddingNonRetryableError(
                        f"Embedding dimension mismatch for {inp.id}: "
                        f"expected={self.provider.dimension}, actual={len(vec)}"
                    )

                record = EmbeddingRecord(
                    id=inp.id,
                    text=inp.text,
                    vector=tuple(vec),
                    summary_version=inp.summary_version,
                    schema_hash=inp.schema_hash,
                    provider_id=self.provider.provider_id,
                    model_id=self.provider.model_id,
                    dimension=self.provider.dimension,
                    created_at=self.clock()
                )
                if self.cache:
                    self.cache.set(key, record)
                records.append(record)

        # Validate duplicate record IDs and map back to inputs
        records_map = {}
        for rec in records:
            if rec.id in records_map:
                raise EmbeddingNonRetryableError(f"Duplicate embedding record id: {rec.id}")
            records_map[rec.id] = rec

        return [records_map[inp.id] for inp in inputs]
