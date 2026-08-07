"""Schema cache invalidation fingerprint — PURE (Sprint 28.6).

Deterministic SHA-256 over the inputs the cached schema depends on. Injected/
used by SchemaManager.load_schema (no I/O here). Bump SCHEMA_CACHE_VERSION when
the extraction logic or cache format changes to invalidate all existing caches.
"""
import hashlib

SCHEMA_CACHE_VERSION = "v1"

_SEP = "\x1f"  # unit separator — cannot collide with JSON config content


def compute_cache_fingerprint(*, db_type, hidden_tables_raw, hidden_columns_raw,
                              embedding_model, cache_version=SCHEMA_CACHE_VERSION) -> str:
    payload = _SEP.join([
        cache_version or "",
        db_type or "",
        hidden_tables_raw or "",
        hidden_columns_raw or "",
        embedding_model or "",
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
