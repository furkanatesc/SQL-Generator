"""Sprint 32.5 — Queue System.

Queue semantics on top of the 32.4 `jobs`-table queue: retry with exponential backoff for
transient failures (worker mode), dead-letter when attempts are exhausted, priority, a global
concurrency cap and an operator surface (`/api/v1/admin/queue`, `.../jobs/{id}/requeue`).
"""
import datetime as dt
import sqlite3
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.errors.codes import ErrorCode
from app.settings import DEV_DEFAULT_API_KEY, get_settings

HEADERS = {"X-API-Key": DEV_DEFAULT_API_KEY}


@pytest.fixture
def fresh_db(monkeypatch, tmp_path):
    from app.database import init_db, set_config

    monkeypatch.setenv("SQLGEN_DB_PATH", str(tmp_path / "app.db"))
    get_settings.cache_clear()
    init_db()
    set_config("nvidia_api_key", "real-nvidia-key")
    return tmp_path / "app.db"


def _sql(db, query, params=()):
    conn = sqlite3.connect(str(db))
    conn.execute(query, params)
    conn.commit()
    conn.close()


def _iso(delta_seconds):
    return (dt.datetime.utcnow() + dt.timedelta(seconds=delta_seconds)).isoformat()


LLM_DOWN = {
    "success": False, "generated_sql": "", "error": "SQL üretimi başarısız oldu. 3 deneme yapıldı.",
    "error_code": ErrorCode.SQL_GENERATION_EXHAUSTED,
    "attempts": [{"validation_errors": [{"type": ErrorCode.LLM_API_ERROR}]} for _ in range(3)],
}
INVALID_SQL = {
    "success": False, "generated_sql": "", "error": "geçersiz SQL",
    "error_code": ErrorCode.SQL_GENERATION_EXHAUSTED,
    "attempts": [{"validation_errors": [{"type": ErrorCode.SYNTAX_ERROR}]}],
}
OK = {"success": True, "generated_sql": "SELECT 1", "error": None, "attempts": [{"validation_errors": []}]}


def _pipeline(*results):
    instance = MagicMock()
    instance.run_pipeline.side_effect = list(results)
    return MagicMock(return_value=instance)


def _worker(**kw):
    from app.jobs.worker import JobWorker

    kw.setdefault("poll_seconds", 0.01)
    kw.setdefault("stale_seconds", 300)
    kw.setdefault("max_attempts", 3)
    kw.setdefault("retry_backoff_seconds", 30)
    return JobWorker(worker_id="w", **kw)


def _run(worker, *results):
    with patch("app.sql_pipeline.SQLGenerationPipeline", _pipeline(*results)), \
         patch("app.trace.dependencies.get_trace_store"):
        return worker.run_once()


def _make_due(db, job_id):
    _sql(db, "UPDATE jobs SET next_attempt_at = ? WHERE id = ?", (_iso(-1), job_id))


# --- policy (pure) ---------------------------------------------------------------------

def test_transient_only_when_every_attempt_is_an_llm_api_error():
    from app.jobs.queue_policy import is_transient_failure

    assert is_transient_failure(LLM_DOWN) is True
    assert is_transient_failure(INVALID_SQL) is False
    assert is_transient_failure(OK) is False
    assert is_transient_failure({"success": False, "attempts": []}) is False
    mixed = {"success": False, "attempts": [
        {"validation_errors": [{"type": "llm_api_error"}]},
        {"validation_errors": [{"type": "syntax_error"}]},
    ]}
    assert is_transient_failure(mixed) is False
    as_strings = {"success": False, "attempts": [{"validation_errors": [{"type": "llm_api_error"}]}]}
    assert is_transient_failure(as_strings) is True


def test_backoff_is_exponential_and_capped():
    from app.jobs.queue_policy import backoff_seconds

    assert [backoff_seconds(n, 30) for n in (1, 2, 3, 4)] == [30, 60, 120, 240]
    assert backoff_seconds(20, 30) == 900
    assert backoff_seconds(3, 30, cap=100) == 100


@pytest.mark.parametrize(
    "attempts, max_attempts, transient, expected",
    [(1, 3, True, "retry"), (2, 3, True, "retry"), (3, 3, True, "dead_letter"),
     (1, 1, True, "dead_letter"), (1, 3, False, "fail"), (3, 3, False, "fail")],
)
def test_decide_failure(attempts, max_attempts, transient, expected):
    from app.jobs.queue_policy import decide_failure

    assert decide_failure(attempts, max_attempts, transient) == expected


# --- migration v3 ------------------------------------------------------------------------

def test_migration_v3_adds_queue_columns(fresh_db):
    conn = sqlite3.connect(str(fresh_db))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    assert {"priority", "attempts", "next_attempt_at", "dead_lettered_at"} <= cols
    assert [r[0] for r in conn.execute("SELECT version FROM schema_migrations")] == [1, 2, 3]


def test_v2_database_upgrades_with_defaults(tmp_path):
    from app.migrations import APP_MIGRATIONS, migrate

    conn = sqlite3.connect(str(tmp_path / "v2.db"))
    migrate(conn, APP_MIGRATIONS[:2])
    conn.execute("INSERT INTO jobs (id, status, created_at, updated_at) VALUES ('j', 'pending', 't', 't')")
    conn.commit()
    assert migrate(conn, APP_MIGRATIONS).applied == [3]
    assert conn.execute("SELECT priority, attempts FROM jobs WHERE id='j'").fetchone() == (0, 0)


# --- claim -------------------------------------------------------------------------------

def test_claim_orders_by_priority_then_age_and_counts_attempts(fresh_db):
    from app.database import create_job
    from app.jobs.repository import claim_next_job

    create_job("old-low", natural_query="q")
    create_job("new-high", natural_query="q", priority=5)
    create_job("new-low", natural_query="q")
    order = [claim_next_job("w")["id"] for _ in range(3)]
    assert order == ["new-high", "old-low", "new-low"]
    conn = sqlite3.connect(str(fresh_db))
    assert {r[0] for r in conn.execute("SELECT attempts FROM jobs")} == {1}


def test_claim_skips_jobs_waiting_for_backoff(fresh_db):
    from app.database import create_job
    from app.jobs.repository import claim_next_job

    create_job("later", natural_query="q")
    _sql(fresh_db, "UPDATE jobs SET next_attempt_at = ? WHERE id = 'later'", (_iso(60),))
    assert claim_next_job("w") is None
    _make_due(fresh_db, "later")
    assert claim_next_job("w")["id"] == "later"


def test_claim_respects_global_concurrency_cap(fresh_db):
    from app.database import create_job
    from app.jobs.repository import claim_next_job

    for i in range(3):
        create_job(f"j{i}", natural_query="q")
    assert claim_next_job("w1", max_concurrent=2) is not None
    assert claim_next_job("w2", max_concurrent=2) is not None
    assert claim_next_job("w3", max_concurrent=2) is None
    assert claim_next_job("w3", max_concurrent=0) is not None  # 0 = unlimited


# --- worker retry / dead-letter -------------------------------------------------------------

def test_transient_failure_is_retried_then_succeeds(fresh_db):
    from app.database import create_job, get_job

    create_job("a", natural_query="q")
    w = _worker()
    assert _run(w, LLM_DOWN) is True
    job = get_job("a")
    assert job["status"] == "pending" and job["attempts"] == 1
    assert job["next_attempt_at"] > _iso(20)  # ~30 s backoff
    assert job["worker_id"] is None and job["error_message"]  # last error kept for visibility
    assert _run(w) is False  # still backing off
    _make_due(fresh_db, "a")
    assert _run(w, OK) is True
    job = get_job("a")
    assert job["status"] == "completed" and job["attempts"] == 2 and job["dead_lettered_at"] is None


def test_exhausted_transient_failure_is_dead_lettered(fresh_db):
    from app.database import create_job, get_job

    create_job("a", natural_query="q")
    w = _worker(max_attempts=2)
    _run(w, LLM_DOWN)
    _make_due(fresh_db, "a")
    _run(w, LLM_DOWN)
    job = get_job("a")
    assert job["status"] == "failed" and job["attempts"] == 2
    assert job["dead_lettered_at"] and job["error_code"] == "sql_generation_exhausted"


def test_deterministic_failure_is_not_retried(fresh_db):
    from app.database import create_job, get_job

    create_job("a", natural_query="q")
    _run(_worker(), INVALID_SQL)
    job = get_job("a")
    assert job["status"] == "failed" and job["attempts"] == 1 and job["dead_lettered_at"] is None


def test_missing_llm_key_is_not_retried(fresh_db):
    from app.database import create_job, get_job, set_config

    set_config("nvidia_api_key", "")
    create_job("a", natural_query="q")
    with patch("app.jobs.executor.resolve_secret", return_value=None):
        _run(_worker())
    assert get_job("a")["status"] == "failed" and get_job("a")["dead_lettered_at"] is None


def test_stale_job_is_requeued_then_dead_lettered(fresh_db):
    from app.database import create_job, get_job

    create_job("a", natural_query="q")
    _sql(fresh_db, "UPDATE jobs SET status='processing', attempts=1, worker_id='gone', heartbeat_at=? WHERE id='a'",
         (_iso(-900),))
    w = _worker(max_attempts=2)
    w.run_once()
    job = get_job("a")
    assert job["status"] == "pending" and job["next_attempt_at"] and job["worker_id"] is None

    _sql(fresh_db, "UPDATE jobs SET status='processing', attempts=2, heartbeat_at=? WHERE id='a'", (_iso(-900),))
    w.run_once()
    job = get_job("a")
    assert job["status"] == "failed" and job["dead_lettered_at"]


def test_inline_mode_never_retries(fresh_db):
    from app.database import create_job, get_job
    from app.jobs.executor import execute_job

    create_job("a", natural_query="q")
    with patch("app.sql_pipeline.SQLGenerationPipeline", _pipeline(LLM_DOWN)), \
         patch("app.trace.dependencies.get_trace_store"):
        execute_job("a")
    assert get_job("a")["status"] == "failed"


# --- API ---------------------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch, fresh_db):
    monkeypatch.setenv("NL2SQL_JOB_EXECUTION_MODE", "worker")
    get_settings.cache_clear()
    from app.main import app

    return TestClient(app)


def test_priority_is_accepted_and_validated(client):
    from app.database import get_job

    r = client.post("/api/jobs/without-file", json={"natural_query": "q", "priority": 7}, headers=HEADERS)
    assert r.status_code == 200
    assert get_job(r.json()["job"]["id"])["priority"] == 7
    r = client.post("/api/jobs/without-file", json={"natural_query": "q"}, headers=HEADERS)
    assert get_job(r.json()["job"]["id"])["priority"] == 0
    assert client.post("/api/jobs/without-file", json={"natural_query": "q", "priority": 11},
                       headers=HEADERS).status_code == 422


def test_queue_stats(client, fresh_db):
    from app.database import create_job

    create_job("p1", natural_query="q")
    create_job("p2", natural_query="q")
    create_job("f1", natural_query="q")
    _sql(fresh_db, "UPDATE jobs SET next_attempt_at=? WHERE id='p2'", (_iso(60),))
    _sql(fresh_db, "UPDATE jobs SET status='failed', dead_lettered_at=? WHERE id='f1'", (_iso(0),))
    r = client.get("/api/v1/admin/queue", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["execution_mode"] == "worker"
    assert data["counts"]["pending"] == 2 and data["counts"]["failed"] == 1
    assert data["retry_scheduled"] == 1 and data["dead_lettered"] == 1
    assert data["oldest_pending_age_seconds"] >= 0
    assert data["max_attempts"] == 3 and data["max_concurrent"] == 0


def test_requeue_failed_job(client, fresh_db):
    from app.database import create_job, get_job

    create_job("f1", natural_query="q")
    _sql(fresh_db, "UPDATE jobs SET status='failed', attempts=3, dead_lettered_at=?, error_message='x', "
                   "error_code='sql_generation_exhausted', next_attempt_at=? WHERE id='f1'", (_iso(0), _iso(0)))
    r = client.post("/api/v1/admin/jobs/f1/requeue", headers=HEADERS)
    assert r.status_code == 200 and r.json()["data"]["status"] == "pending"
    job = get_job("f1")
    assert (job["attempts"], job["dead_lettered_at"], job["error_message"], job["error_code"],
            job["next_attempt_at"]) == (0, None, None, None, None)


def test_requeue_rejects_unknown_and_non_failed(client, fresh_db):
    from app.database import create_job

    create_job("p1", natural_query="q")
    assert client.post("/api/v1/admin/jobs/nope/requeue", headers=HEADERS).status_code == 404
    r = client.post("/api/v1/admin/jobs/p1/requeue", headers=HEADERS)
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT"


def test_admin_queue_routes_require_api_key(client):
    assert client.get("/api/v1/admin/queue").status_code == 403
    assert client.post("/api/v1/admin/jobs/x/requeue").status_code == 403


def test_backoff_pending_is_not_counted_as_stalled(monkeypatch, fresh_db):
    from app.database import create_job
    from app.jobs.repository import count_stalled_pending

    create_job("waiting", natural_query="q")
    _sql(fresh_db, "UPDATE jobs SET created_at=?, next_attempt_at=? WHERE id='waiting'", (_iso(-3600), _iso(60)))
    assert count_stalled_pending(300) == 0
    _sql(fresh_db, "UPDATE jobs SET next_attempt_at=? WHERE id='waiting'", (_iso(-3600),))
    assert count_stalled_pending(300) == 1


def test_queue_settings_are_validated(monkeypatch):
    from pydantic import ValidationError
    from app.settings import Settings

    for name, bad in (("NL2SQL_JOB_MAX_ATTEMPTS", "0"), ("NL2SQL_JOB_RETRY_BACKOFF_SECONDS", "0"),
                      ("NL2SQL_JOB_MAX_CONCURRENT", "-1")):
        monkeypatch.setenv(name, bad)
        with pytest.raises(ValidationError):
            Settings()
        monkeypatch.delenv(name)
