"""Query-run feedback persistence (Sprint 30.6).

Append-only feedback attached to a 30.4 query_run (verdict + optional category/
note/corrected_sql). Distinct from the legacy 27.3 job-scoped feedback
(app/feedback/ + database.py job-feedback functions), which is untouched.
"""
from __future__ import annotations

import datetime
import uuid
from typing import Optional

from app.database import get_db_connection


def _now() -> str:
    return datetime.datetime.utcnow().isoformat()


def create_feedback(query_run_id: str, verdict: str, category: Optional[str],
                    note: Optional[str], corrected_sql: Optional[str]) -> dict:
    fid = uuid.uuid4().hex
    now = _now()
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO query_run_feedback (id, query_run_id, verdict, category,
                note, corrected_sql, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (fid, query_run_id, verdict, category, note, corrected_sql, now),
        )
        conn.commit()
    return get_feedback(fid)


def get_feedback(feedback_id: str) -> Optional[dict]:
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM query_run_feedback WHERE id = ?", (feedback_id,)
        ).fetchone()
        return dict(row) if row else None


def list_feedback(limit: int, offset: int, query_run_id: Optional[str] = None,
                  verdict: Optional[str] = None) -> list[dict]:
    clauses, params = [], []
    if query_run_id is not None:
        clauses.append("query_run_id = ?")
        params.append(query_run_id)
    if verdict is not None:
        clauses.append("verdict = ?")
        params.append(verdict)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    params.extend([limit, offset])
    with get_db_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM query_run_feedback{where} ORDER BY rowid DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def delete_feedback(feedback_id: str) -> bool:
    with get_db_connection() as conn:
        cur = conn.execute("DELETE FROM query_run_feedback WHERE id = ?", (feedback_id,))
        conn.commit()
        return cur.rowcount > 0


def row_to_response_dict(row: dict) -> dict:
    return {
        "id": row["id"],
        "query_run_id": row["query_run_id"],
        "verdict": row["verdict"],
        "category": row["category"],
        "note": row["note"],
        "corrected_sql": row["corrected_sql"],
        "created_at": row["created_at"],
    }
