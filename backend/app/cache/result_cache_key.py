"""Pure deterministic result-cache key (Sprint 28.9).

sha256 over version + dialect + schema_signature + normalized query. stdlib-only,
side-effect-free. The schema_signature (Sprint 28.7) binds a cached SQL to the schema
shape it was generated against, so a structural schema change invalidates the key.
"""
import hashlib

RESULT_CACHE_KEY_VERSION = "v1"
_UNIT = "\x1f"


def normalize_query(q):
    """Deterministic minimal normalization (no semantic risk): casefold + collapse whitespace."""
    if q is None:
        return ""
    return " ".join(str(q).casefold().split())


def compute_result_cache_key(natural_query, dialect, schema_signature,
                             *, version=RESULT_CACHE_KEY_VERSION):
    payload = _UNIT.join([
        version,
        dialect or "",
        schema_signature or "",
        normalize_query(natural_query),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
