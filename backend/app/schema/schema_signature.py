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


from dataclasses import dataclass


@dataclass(frozen=True)
class StructuralDrift:
    added_tables: tuple = ()
    removed_tables: tuple = ()
    added_columns: tuple = ()      # (table, column)
    removed_columns: tuple = ()    # (table, column)
    changed_columns: tuple = ()    # (table, column, old_type, new_type)
    added_fks: tuple = ()          # (table, column, ref_table, ref_col)
    removed_fks: tuple = ()        # (table, column, ref_table, ref_col)

    @property
    def has_drift(self):
        return any((self.added_tables, self.removed_tables, self.added_columns,
                    self.removed_columns, self.changed_columns,
                    self.added_fks, self.removed_fks))

    def as_dict(self):
        return {
            "added_tables": list(self.added_tables),
            "removed_tables": list(self.removed_tables),
            "added_columns": [{"table": t, "column": c} for (t, c) in self.added_columns],
            "removed_columns": [{"table": t, "column": c} for (t, c) in self.removed_columns],
            "changed_columns": [
                {"table": t, "column": c, "old_type": o, "new_type": n}
                for (t, c, o, n) in self.changed_columns
            ],
            "added_fks": [
                {"table": t, "column": c, "referenced_table": rt, "referenced_column": rc}
                for (t, c, rt, rc) in self.added_fks
            ],
            "removed_fks": [
                {"table": t, "column": c, "referenced_table": rt, "referenced_column": rc}
                for (t, c, rt, rc) in self.removed_fks
            ],
        }


def _col_maps(entry):
    # column name -> (type, pk, nullable)
    return {n: (t, pk, nl) for (n, t, pk, nl) in entry["columns"]}


def diff_structures(old_norm, new_norm):
    old_t, new_t = set(old_norm), set(new_norm)
    added_tables = tuple(sorted(new_t - old_t))
    removed_tables = tuple(sorted(old_t - new_t))

    added_columns, removed_columns, changed_columns = [], [], []
    added_fks, removed_fks = [], []
    for t in sorted(old_t & new_t):
        old_cols, new_cols = _col_maps(old_norm[t]), _col_maps(new_norm[t])
        for c in sorted(set(new_cols) - set(old_cols)):
            added_columns.append((t, c))
        for c in sorted(set(old_cols) - set(new_cols)):
            removed_columns.append((t, c))
        for c in sorted(set(old_cols) & set(new_cols)):
            if old_cols[c] != new_cols[c]:
                changed_columns.append((t, c, old_cols[c][0], new_cols[c][0]))
        old_fks, new_fks = set(old_norm[t]["foreign_keys"]), set(new_norm[t]["foreign_keys"])
        for (col, rt, rc) in sorted(new_fks - old_fks):
            added_fks.append((t, col, rt, rc))
        for (col, rt, rc) in sorted(old_fks - new_fks):
            removed_fks.append((t, col, rt, rc))

    return StructuralDrift(
        added_tables=added_tables, removed_tables=removed_tables,
        added_columns=tuple(added_columns), removed_columns=tuple(removed_columns),
        changed_columns=tuple(changed_columns),
        added_fks=tuple(added_fks), removed_fks=tuple(removed_fks),
    )
