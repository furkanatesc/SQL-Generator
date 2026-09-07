"""Query-run persistence (Sprint 30.4).

Inert ledger of SQL runs against a connection. Records the SQL and an optional
provided outcome (result rows or an execution error — the payload a future live
executor would produce). Opens no live DB connection, resolves no secret.
Append-only history.
"""
from __future__ import annotations

import datetime
import json
import uuid
from typing import Optional

from app.database import get_db_connection


def _now() -> str:
    return datetime.datetime.utcnow().isoformat()


def create_query_run(connection_id: str, sql: str, result: Optional[dict] = None) -> dict:
    columns_json = rows_json = None
    truncated = row_count = duration_ms = execution_error = None
    if result is None:
        status = "recorded"
    elif result.get("execution_error"):
        status = "failed"
        execution_error = result["execution_error"]
        duration_ms = result.get("duration_ms")
    else:
        status = "succeeded"
        rows = result.get("rows", []) or []
        columns_json = json.dumps(result.get("columns", []) or [])
        rows_json = json.dumps(rows)
        truncated = 1 if result.get("truncated") else 0
        row_count = len(rows)
        duration_ms = result.get("duration_ms")
    rid = uuid.uuid4().hex
    now = _now()
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO query_runs (id, connection_id, sql, status, row_count,
                columns_json, rows_json, truncated, execution_error, duration_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (rid, connection_id, sql, status, row_count, columns_json, rows_json,
             truncated, execution_error, duration_ms, now),
        )
        conn.commit()
    return get_query_run(rid)


def get_query_run(run_id: str) -> Optional[dict]:
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM query_runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None


def list_query_runs(limit: int, offset: int, connection_id: Optional[str] = None,
                    status: Optional[str] = None) -> list[dict]:
    clauses, params = [], []
    if connection_id is not None:
        clauses.append("connection_id = ?")
        params.append(connection_id)
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    params.extend([limit, offset])
    with get_db_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM query_runs{where} ORDER BY rowid DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def delete_query_run(run_id: str) -> bool:
    with get_db_connection() as conn:
        cur = conn.execute("DELETE FROM query_runs WHERE id = ?", (run_id,))
        conn.commit()
        return cur.rowcount > 0


def row_to_response_dict(row: dict) -> dict:
    result = None
    if row["status"] == "succeeded":
        result = {
            "columns": json.loads(row["columns_json"]) if row["columns_json"] else [],
            "rows": json.loads(row["rows_json"]) if row["rows_json"] else [],
            "truncated": bool(row["truncated"]),
            "duration_ms": row["duration_ms"],
        }
    return {
        "id": row["id"],
        "connection_id": row["connection_id"],
        "sql": row["sql"],
        "status": row["status"],
        "row_count": row["row_count"],
        "result": result,
        "execution_error": row["execution_error"],
        "created_at": row["created_at"],
    }
