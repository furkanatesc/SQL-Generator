"""Schema-sync persistence (Sprint 30.3).

Stores per-connection schema snapshots (provided in the request — inert, no live
introspection) and detects structural drift vs the connection's previous
snapshot, reusing the Phase 9 drift engine. Append-only history.
"""
from __future__ import annotations

import datetime
import json
import uuid
from typing import Optional

from app.database import get_db_connection
from app.schema.schema_signature import (
    normalize_structure,
    compute_schema_signature,
    diff_structures,
)


def _now() -> str:
    return datetime.datetime.utcnow().isoformat()


def create_schema_sync(connection_id: str, schema) -> dict:
    if not isinstance(schema, dict) or not isinstance(schema.get("tables"), dict):
        raise ValueError("schema must be an object with a 'tables' mapping")
    new_norm = normalize_structure(schema)
    signature = compute_schema_signature(new_norm)
    prev = get_latest_for_connection(connection_id)
    if prev is None:
        # Baseline sync: diff against an empty structure so drift shows every
        # table/column as "added" — keeping `drifted=True` consistent with the
        # drift payload (no flag/payload disagreement on the first snapshot).
        previous_signature = None
        drift = diff_structures({}, new_norm).as_dict()
        drifted = True
    else:
        previous_signature = prev["signature"]
        prev_norm = normalize_structure(json.loads(prev["structure_json"]))
        drift = diff_structures(prev_norm, new_norm).as_dict()
        drifted = previous_signature != signature
    sid = uuid.uuid4().hex
    now = _now()
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO schema_syncs (id, connection_id, signature, previous_signature,
                drifted, structure_json, drift_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (sid, connection_id, signature, previous_signature, 1 if drifted else 0,
             json.dumps(schema), json.dumps(drift), now),
        )
        conn.commit()
    return get_schema_sync(sid)


def get_schema_sync(sync_id: str) -> Optional[dict]:
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM schema_syncs WHERE id = ?", (sync_id,)).fetchone()
        return dict(row) if row else None


def get_latest_for_connection(connection_id: str) -> Optional[dict]:
    with get_db_connection() as conn:
        # Order by the monotonic insertion key (sqlite rowid), NOT created_at —
        # coarse utcnow timestamps can tie and the uuid id is not time-ordered,
        # which would pick the wrong "previous" snapshot for drift.
        row = conn.execute(
            "SELECT * FROM schema_syncs WHERE connection_id = ? "
            "ORDER BY rowid DESC LIMIT 1",
            (connection_id,),
        ).fetchone()
        return dict(row) if row else None


def list_schema_syncs(limit: int, offset: int, connection_id: Optional[str] = None) -> list[dict]:
    with get_db_connection() as conn:
        # Order by the monotonic insertion key (sqlite rowid) so pagination is
        # stable even when created_at values tie (see get_latest_for_connection).
        if connection_id is not None:
            rows = conn.execute(
                "SELECT * FROM schema_syncs WHERE connection_id = ? "
                "ORDER BY rowid DESC LIMIT ? OFFSET ?",
                (connection_id, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM schema_syncs ORDER BY rowid DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]


def delete_schema_sync(sync_id: str) -> bool:
    with get_db_connection() as conn:
        cur = conn.execute("DELETE FROM schema_syncs WHERE id = ?", (sync_id,))
        conn.commit()
        return cur.rowcount > 0


def row_to_response_dict(row: dict) -> dict:
    return {
        "id": row["id"],
        "connection_id": row["connection_id"],
        "signature": row["signature"],
        "previous_signature": row["previous_signature"],
        "drifted": bool(row["drifted"]),
        "drift": json.loads(row["drift_json"]),
        "structure": json.loads(row["structure_json"]),
        "created_at": row["created_at"],
    }
