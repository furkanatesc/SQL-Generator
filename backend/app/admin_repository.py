"""Admin read surface (Sprint 30.7).

Read-only COUNT(*) over the Phase 11 resource tables for the admin overview.
No writes.
"""
from __future__ import annotations

from app.database import get_db_connection

# Fixed table names (no user input) — interpolation is safe.
_RESOURCE_TABLES = (
    "workspaces",
    "connections",
    "schema_syncs",
    "query_runs",
    "query_run_feedback",
)


def resource_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    with get_db_connection() as conn:
        for table in _RESOURCE_TABLES:
            row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
            counts[table] = int(row["n"])
    return counts
