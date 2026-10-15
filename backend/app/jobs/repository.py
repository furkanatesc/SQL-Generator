"""Job claim / heartbeat / recovery and persistent job logs (Sprint 32.4).

All functions use the app database (`app.database.get_db_connection`). Claiming takes the
SQLite write lock up front (`BEGIN IMMEDIATE`) so two workers can never claim the same job.
Timestamps follow the existing `jobs` convention: naive UTC `isoformat()`.
"""
import datetime as dt
from typing import Any, Dict, List, Optional, Sequence

from app import database


def _now() -> str:
    return dt.datetime.utcnow().isoformat()


def _ago(seconds: float) -> str:
    return (dt.datetime.utcnow() - dt.timedelta(seconds=seconds)).isoformat()


def claim_next_job(worker_id: str) -> Optional[Dict[str, Any]]:
    """Atomically move the oldest `pending` job to `processing` for `worker_id`."""
    conn = database.get_db_connection()
    try:
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT id FROM jobs WHERE status = 'pending' ORDER BY created_at, rowid LIMIT 1"
        ).fetchone()
        if row is None:
            conn.execute("COMMIT")
            return None
        now = _now()
        conn.execute(
            "UPDATE jobs SET status = 'processing', worker_id = ?, claimed_at = ?, heartbeat_at = ?, "
            "updated_at = ? WHERE id = ? AND status = 'pending'",
            (worker_id, now, now, now, row["id"]),
        )
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    return database.get_job(row["id"])


def touch_heartbeat(job_id: str, worker_id: str) -> bool:
    with database.get_db_connection() as conn:
        cur = conn.execute(
            "UPDATE jobs SET heartbeat_at = ? WHERE id = ? AND worker_id = ? AND status = 'processing'",
            (_now(), job_id, worker_id),
        )
        conn.commit()
        return cur.rowcount == 1


ABANDONED_MESSAGE = (
    "Job interrupted: its worker stopped before completion (no heartbeat). Please resubmit."
)
RESTART_MESSAGE = "Job interrupted: the API process restarted before it completed. Please resubmit."


def fail_abandoned_jobs(
    statuses: Sequence[str],
    older_than_seconds: Optional[float] = None,
    message: str = ABANDONED_MESSAGE,
) -> List[str]:
    """Mark matching jobs `failed`; returns their ids (sorted)."""
    placeholders = ", ".join("?" for _ in statuses)
    where = f"status IN ({placeholders})"
    params: List[Any] = list(statuses)
    if older_than_seconds is not None:
        where += " AND COALESCE(heartbeat_at, updated_at) < ?"
        params.append(_ago(older_than_seconds))
    with database.get_db_connection() as conn:
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE")
        ids = sorted(r["id"] for r in conn.execute(f"SELECT id FROM jobs WHERE {where}", params))
        if ids:
            id_marks = ", ".join("?" for _ in ids)
            conn.execute(
                f"UPDATE jobs SET status = 'failed', error_message = ?, updated_at = ? "
                f"WHERE id IN ({id_marks}) AND {where}",
                [message, _now(), *ids, *params],
            )
        conn.execute("COMMIT")
    return ids


def count_stalled_pending(older_than_seconds: float) -> int:
    with database.get_db_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status = 'pending' AND created_at < ?",
            (_ago(older_than_seconds),),
        ).fetchone()
        return row[0]


def append_job_log(job_id: str, message: str, step: Optional[int] = None) -> int:
    with database.get_db_connection() as conn:
        cur = conn.execute(
            "INSERT INTO job_logs (job_id, step, message, created_at) VALUES (?, ?, ?, ?)",
            (job_id, step, message, _now()),
        )
        conn.commit()
        return cur.lastrowid


def list_job_logs(job_id: str, after_id: int = 0) -> List[Dict[str, Any]]:
    with database.get_db_connection() as conn:
        rows = conn.execute(
            "SELECT id, job_id, step, message, created_at FROM job_logs "
            "WHERE job_id = ? AND id > ? ORDER BY id",
            (job_id, after_id),
        ).fetchall()
        return [dict(r) for r in rows]
