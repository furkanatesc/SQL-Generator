import time
import random
import logging
from dataclasses import dataclass
from typing import Literal, List, Optional
from app.schema.schema_contract import DatabaseSchema
from app.retrieval.embedding_provider import EmbeddingProvider
from app.retrieval.embedding_cache import EmbeddingCache, EmbeddingRecord, build_cache_key

logger = logging.getLogger("embedding_pipeline")


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
    object_type: Literal["database", "table", "column", "relationship"]
    object_id: str


def build_embedding_inputs(schema: DatabaseSchema) -> List[EmbeddingInput]:
    """
    Transforms a DatabaseSchema into a list of structured EmbeddingInputs.
    Uses summarize_database_schema from Sprint 21.0 to get deterministic summaries.
    """
    from app.schema.schema_summary import summarize_database_schema
    from app.retrieval.embedding_hash import compute_summary_hash

    table_summaries = summarize_database_schema(schema)
    inputs = []

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

        # Relationship summary inputs
        for rel in table.relationships:
            rel_hash = compute_summary_hash(rel.summary_text, rel.summary_version)
            inputs.append(EmbeddingInput(
                id=f"relationship:{rel.source_table}.{rel.source_column}->{rel.target_table}.{rel.target_column}",
                text=rel.summary_text,
                summary_version=rel.summary_version,
                schema_hash=rel_hash,
                object_type="relationship",
                object_id=f"{rel.source_table}.{rel.source_column}->{rel.target_table}.{rel.target_column}"
            ))

    return inputs


def execute_with_retry(func, max_attempts: int = 3, base_delay_ms: float = 200, jitter: bool = True):
    """
    Helper function executing the given callable with exponential backoff and optional jitter.
    Classifies errors into retryable vs non-retryable.
    """
    attempt = 0
    while attempt < max_attempts:
        try:
            try:
                return func()
            except Exception as e:
                # Classify the raw exception into an EmbeddingError
                import requests
                if isinstance(e, EmbeddingError):
                    raise e
                if isinstance(e, requests.exceptions.Timeout):
                    raise EmbeddingRetryableError(f"Timeout occurred: {e}") from e
                if isinstance(e, requests.exceptions.HTTPError):
                    status_code = e.response.status_code if e.response is not None else 500
                    if status_code == 429 or 500 <= status_code < 600:
                        raise EmbeddingRetryableError(f"HTTP transient error {status_code}: {e}") from e
                    raise EmbeddingNonRetryableError(f"HTTP non-retryable error {status_code}: {e}") from e
                if isinstance(e, requests.exceptions.RequestException):
                    raise EmbeddingRetryableError(f"Network request error: {e}") from e

                # Fallback text checking for standard errors
                err_msg = str(e).lower()
                if any(term in err_msg for term in ["timeout", "rate limit", "too many requests", "500", "503"]):
                    raise EmbeddingRetryableError(f"Transient error classified: {e}") from e

                raise EmbeddingNonRetryableError(f"Non-retryable unexpected error: {e}") from e
                
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


class EmbeddingPipeline:
    """
    Embedding pipeline orchestrating provider call with caching, invalidation, and retries.
    """
    def __init__(self, provider: EmbeddingProvider, cache: EmbeddingCache = None):
        self.provider = provider
        self.cache = cache

    def process_schema(self, schema: DatabaseSchema) -> List[EmbeddingRecord]:
        """
        Processes a DatabaseSchema: builds inputs, resolves cache, runs provider for cache misses,
        caches new values, and returns all records.
        """
        inputs = build_embedding_inputs(schema)
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

            for inp, key, vec in zip(uncached_inputs, uncached_keys, vectors):
                record = EmbeddingRecord(
                    id=inp.id,
                    text=inp.text,
                    vector=vec,
                    summary_version=inp.summary_version,
                    schema_hash=inp.schema_hash,
                    provider_id=self.provider.provider_id,
                    model_id=self.provider.model_id,
                    dimension=self.provider.dimension,
                    created_at=time.time()
                )
                if self.cache:
                    self.cache.set(key, record)
                records.append(record)

        return records
