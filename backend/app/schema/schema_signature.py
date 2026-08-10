"""Pure structural schema signature (Sprint 28.7).

Deterministic, stdlib-only, side-effect-free. Turns an extracted schema
({"tables": {...}, "graph": {...}}, as produced by
SchemaManager.extract_schema_metadata) into a canonical, order-independent
structure and hashes it. Used to detect raw DB structural drift that 28.6's
self-contained cache fingerprint cannot see.

Purity: no clocks, no I/O, no heavy app.* imports.
"""
import hashlib

SCHEMA_SIGNATURE_VERSION = "v1"

_UNIT = "\x1f"   # field separator inside a record
_REC = "\x1e"    # record separator inside a group
_GRP = "\x1d"    # group separator inside a table


def normalize_structure(schema):
    """Canonical, dialect-agnostic, order-independent structure."""
    tables = (schema or {}).get("tables", {}) or {}
    normalized = {}
    for tname, tmeta in tables.items():
        tmeta = tmeta or {}
        cols = tuple(sorted(
            (
                str(c.get("name", "")),
                str(c.get("type", "")),
                bool(c.get("primary_key", False)),
                bool(c.get("nullable", True)),
            )
            for c in (tmeta.get("columns", []) or [])
        ))
        fks = tuple(sorted(
            (
                str(fk.get("column", "")),
                str(fk.get("referenced_table", "")),
                str(fk.get("referenced_column", "")),
            )
            for fk in (tmeta.get("foreign_keys", []) or [])
        ))
        normalized[str(tname)] = {"columns": cols, "foreign_keys": fks}
    return normalized


def _canonical_str(normalized):
    parts = []
    for tname in sorted(normalized.keys()):
        entry = normalized[tname]
        col_str = _REC.join(
            _UNIT.join((n, t, "1" if pk else "0", "1" if nl else "0"))
            for (n, t, pk, nl) in entry["columns"]
        )
        fk_str = _REC.join(
            _UNIT.join((c, rt, rc)) for (c, rt, rc) in entry["foreign_keys"]
        )
        parts.append(_GRP.join((tname, col_str, fk_str)))
    return "\n".join(parts)


def compute_schema_signature(normalized, *, version=SCHEMA_SIGNATURE_VERSION):
    payload = version + "\n" + _canonical_str(normalized)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
