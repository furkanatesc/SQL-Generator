"""Job claim / heartbeat / recovery and persistent job logs (Sprint 32.4).

All functions use the app database (`app.database.get_db_connection`). Claiming takes the
SQLite write lock up front (`BEGIN IMMEDIATE`) so two workers can never claim the same job.
Timestamps follow the existing `jobs` convention: naive UTC `isoformat()`.
"""
import datetime as dt
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app import database


def _now() -> str:
    return dt.datetime.utcnow().isoformat()


def _ago(seconds: float) -> str:
    return (dt.datetime.utcnow() - dt.timedelta(seconds=seconds)).isoformat()


def claim_next_job(worker_id: str, max_concurrent: int = 0) -> Optional[Dict[str, Any]]:
    """Atomically move the next due `pending` job to `processing` for `worker_id`.

    Order: highest `priority`, then oldest. Jobs still backing off (`next_attempt_at` in the
    future) are skipped. With `max_concurrent > 0` nothing is claimed while that many jobs are
    already `processing` across all workers (Sprint 32.5).
    """
    conn = database.get_db_connection()
    try:
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE")
        now = _now()
        if max_concurrent > 0:
            running = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'processing'").fetchone()[0]
            if running >= max_concurrent:
                conn.execute("COMMIT")
                return None
        row = conn.execute(
            "SELECT id FROM jobs WHERE status = 'pending' "
            "AND (next_attempt_at IS NULL OR next_attempt_at <= ?) "
            "ORDER BY priority DESC, created_at, rowid LIMIT 1",
            (now,),
        ).fetchone()
        if row is None:
            conn.execute("COMMIT")
            return None
        conn.execute(
            "UPDATE jobs SET status = 'processing', worker_id = ?, claimed_at = ?, heartbeat_at = ?, "
            "attempts = attempts + 1, next_attempt_at = NULL, updated_at = ? "
            "WHERE id = ? AND status = 'pending'",
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
    """Pending jobs that have been due for longer than the threshold (a job backing off
    is due at `next_attempt_at`, not at `created_at`)."""
    with database.get_db_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status = 'pending' "
            "AND COALESCE(next_attempt_at, created_at) < ?",
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


# --- Sprint 32.5: retry / dead-letter / requeue / stats ---------------------------------

_CLEAR_CLAIM = "worker_id = NULL, claimed_at = NULL, heartbeat_at = NULL"


def _in(seconds: float) -> str:
    return (dt.datetime.utcnow() + dt.timedelta(seconds=seconds)).isoformat()


def schedule_retry(job_id: str, delay_seconds: float, error_message: Optional[str],
                   error_code: Optional[str]) -> None:
    """Back to `pending`, due after `delay_seconds`; the last error stays visible."""
    with database.get_db_connection() as conn:
        conn.execute(
            f"UPDATE jobs SET status = 'pending', next_attempt_at = ?, error_message = ?, error_code = ?, "
            f"{_CLEAR_CLAIM}, updated_at = ? WHERE id = ?",
            (_in(delay_seconds), error_message, error_code, _now(), job_id),
        )
        conn.commit()


def dead_letter(job_id: str, error_message: Optional[str], error_code: Optional[str]) -> None:
    """Retries exhausted: `failed` plus a `dead_lettered_at` marker."""
    now = _now()
    with database.get_db_connection() as conn:
        conn.execute(
            "UPDATE jobs SET status = 'failed', dead_lettered_at = ?, error_message = ?, error_code = ?, "
            "next_attempt_at = NULL, updated_at = ? WHERE id = ?",
            (now, error_message, error_code, now, job_id),
        )
        conn.commit()


def recover_stale_jobs(stale_seconds: float, max_attempts: int,
                       backoff_base: float) -> Tuple[List[str], List[str]]:
    """`processing` jobs whose worker stopped heartbeating (a transient failure): requeue with
    backoff while attempts remain, otherwise dead-letter. Returns (requeued, dead_lettered)."""
    from app.jobs.queue_policy import backoff_seconds, decide_failure

    requeued: List[str] = []
    dead: List[str] = []
    with database.get_db_connection() as conn:
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            "SELECT id, attempts FROM jobs WHERE status = 'processing' "
            "AND COALESCE(heartbeat_at, updated_at) < ? ORDER BY id",
            (_ago(stale_seconds),),
        ).fetchall()
        now = _now()
        for row in rows:
            attempts = row["attempts"] or 1
            if decide_failure(attempts, max_attempts, transient=True) == "retry":
                conn.execute(
                    f"UPDATE jobs SET status = 'pending', next_attempt_at = ?, error_message = ?, "
                    f"{_CLEAR_CLAIM}, updated_at = ? WHERE id = ?",
                    (_in(backoff_seconds(attempts, backoff_base)), ABANDONED_MESSAGE, now, row["id"]),
                )
                requeued.append(row["id"])
            else:
                conn.execute(
                    "UPDATE jobs SET status = 'failed', dead_lettered_at = ?, error_message = ?, "
                    "updated_at = ? WHERE id = ?",
                    (now, ABANDONED_MESSAGE, now, row["id"]),
                )
                dead.append(row["id"])
        conn.execute("COMMIT")
    return requeued, dead


def requeue_job(job_id: str) -> Optional[bool]:
    """Operator requeue of a `failed` job. None: unknown job; False: not `failed`."""
    with database.get_db_connection() as conn:
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None or row["status"] != "failed":
            conn.execute("COMMIT")
            return None if row is None else False
        conn.execute(
            "UPDATE jobs SET status = 'pending', attempts = 0, next_attempt_at = NULL, "
            "dead_lettered_at = NULL, error_message = NULL, error_code = NULL, result_sql = NULL, "
            f"{_CLEAR_CLAIM}, updated_at = ? WHERE id = ?",
            (_now(), job_id),
        )
        conn.execute("COMMIT")
    return True


JOB_STATUSES = ("pending", "processing", "completed", "failed", "cancelled")


def queue_stats() -> Dict[str, Any]:
    now = _now()
    with database.get_db_connection() as conn:
        counts = {status: 0 for status in JOB_STATUSES}
        for row in conn.execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status"):
            counts[row["status"]] = row["n"]
        retry_scheduled = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status = 'pending' AND next_attempt_at > ?", (now,)
        ).fetchone()[0]
        dead_lettered = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status = 'failed' AND dead_lettered_at IS NOT NULL"
        ).fetchone()[0]
        oldest = conn.execute(
            "SELECT MIN(COALESCE(next_attempt_at, created_at)) FROM jobs WHERE status = 'pending' "
            "AND (next_attempt_at IS NULL OR next_attempt_at <= ?)",
            (now,),
        ).fetchone()[0]
    oldest_age = None
    if oldest:
        try:
            oldest_age = max(0.0, (dt.datetime.utcnow() - dt.datetime.fromisoformat(oldest)).total_seconds())
        except ValueError:
            oldest_age = None
    return {
        "counts": counts,
        "retry_scheduled": retry_scheduled,
        "dead_lettered": dead_lettered,
        "oldest_pending_age_seconds": oldest_age,
    }
