"""Query-history read surface (Sprint 30.5).

Read-only history / analytics over the 30.4 query_runs ledger, joined to
connections for workspace scoping. No table of its own, no writes. Every filter
value is a bound parameter (injection-safe); only fixed column names are
interpolated.
"""
from __future__ import annotations

from typing import Optional

from app.database import get_db_connection

_STATUSES = ("recorded", "succeeded", "failed")

_BASE = "FROM query_runs qr LEFT JOIN connections c ON qr.connection_id = c.id"


def _escape_like(s: str) -> str:
    """Escape LIKE metacharacters so a free-text query matches them literally
    (used with `ESCAPE '\\'`). Order matters: escape the escape char first."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _where(connection_id, workspace_id, status, since, until, q) -> tuple[str, list]:
    clauses, params = [], []
    if connection_id is not None:
        clauses.append("qr.connection_id = ?")
        params.append(connection_id)
    if workspace_id is not None:
        clauses.append("c.workspace_id = ?")
        params.append(workspace_id)
    if status is not None:
        clauses.append("qr.status = ?")
        params.append(status)
    if since is not None:
        clauses.append("qr.created_at >= ?")
        params.append(since)
    if until is not None:
        clauses.append("qr.created_at <= ?")
        params.append(until)
    if q is not None:
        clauses.append("qr.sql LIKE ? ESCAPE '\\'")
        params.append(f"%{_escape_like(q)}%")
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def list_history(limit: int, offset: int, connection_id: Optional[str] = None,
                 workspace_id: Optional[str] = None, status: Optional[str] = None,
                 since: Optional[str] = None, until: Optional[str] = None,
                 q: Optional[str] = None) -> list[dict]:
    where, params = _where(connection_id, workspace_id, status, since, until, q)
    sql = (
        "SELECT qr.id, qr.connection_id, c.workspace_id, qr.sql, qr.status, "
        f"qr.row_count, qr.created_at {_BASE}{where} "
        "ORDER BY qr.rowid DESC LIMIT ? OFFSET ?"
    )
    with get_db_connection() as conn:
        rows = conn.execute(sql, [*params, limit, offset]).fetchall()
        return [dict(r) for r in rows]


def summary(connection_id: Optional[str] = None, workspace_id: Optional[str] = None,
            status: Optional[str] = None, since: Optional[str] = None,
            until: Optional[str] = None, q: Optional[str] = None) -> dict:
    where, params = _where(connection_id, workspace_id, status, since, until, q)
    by_status = {s: 0 for s in _STATUSES}
    with get_db_connection() as conn:
        rows = conn.execute(
            f"SELECT qr.status AS status, COUNT(*) AS n {_BASE}{where} GROUP BY qr.status",
            params,
        ).fetchall()
    total = 0
    for r in rows:
        by_status[r["status"]] = int(r["n"])
        total += int(r["n"])
    return {"total": total, "by_status": by_status}
