"""Sprint 32.4 — Background Job Worker.

Jobs can run in the API process (`NL2SQL_JOB_EXECUTION_MODE=inline`, default) or in a
separate worker process (`worker`) that claims `pending` rows from the `jobs` table. Job logs
are persisted to `job_logs`; orphaned/stale jobs are failed instead of hanging forever.
"""
import datetime as dt
import os
import sqlite3
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.settings import DEV_DEFAULT_API_KEY, get_settings


@pytest.fixture
def fresh_db(monkeypatch, tmp_path):
    from app.database import init_db, set_config

    monkeypatch.setenv("SQLGEN_DB_PATH", str(tmp_path / "app.db"))
    get_settings.cache_clear()
    init_db()
    set_config("nvidia_api_key", "real-nvidia-key")
    return tmp_path / "app.db"


def _raw(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _old(seconds):
    return (dt.datetime.utcnow() - dt.timedelta(seconds=seconds)).isoformat()


def _pipeline_mock(result=None, side_effect=None):
    """Patch target for app.sql_pipeline.SQLGenerationPipeline."""
    instance = MagicMock()

    def run(**kwargs):
        kwargs["log_callback"]("şema yüklendi", 1)
        if side_effect:
            side_effect(kwargs)
        return result or {"success": True, "generated_sql": "SELECT 1", "error": None}

    instance.run_pipeline.side_effect = run
    return MagicMock(return_value=instance)


# --- migration v2 + runner ---------------------------------------------------------

def test_app_migration_v2_adds_worker_columns_and_job_logs(fresh_db):
    conn = _raw(fresh_db)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)")}
    assert {"worker_id", "claimed_at", "heartbeat_at"} <= cols
    assert {r["name"] for r in conn.execute("PRAGMA table_info(job_logs)")} >= {
        "id", "job_id", "step", "message", "created_at"
    }
    versions = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
    assert versions == [1, 2]


def test_v1_database_is_upgraded_to_v2(tmp_path):
    from app.migrations import APP_MIGRATIONS, migrate

    conn = _raw(tmp_path / "old.db")
    migrate(conn, APP_MIGRATIONS[:1])
    conn.execute("INSERT INTO jobs (id, status, created_at, updated_at) VALUES ('j', 'completed', 't', 't')")
    conn.commit()
    s = migrate(conn, APP_MIGRATIONS)
    assert s.applied == [2] and s.error is None
    assert conn.execute("SELECT status FROM jobs WHERE id = 'j'").fetchone()[0] == "completed"


def test_runner_skips_migration_applied_by_another_process(tmp_path):
    # Two processes computed the same pending list; the loser must skip, not fail.
    from app.migrations import runner
    from app.migrations.runner import Migration, MigrationStatus, migrate

    def add_col(conn):
        conn.execute("ALTER TABLE t ADD COLUMN c TEXT")

    reg = (Migration(1, "t", lambda c: c.execute("CREATE TABLE t (id INTEGER)")), Migration(2, "c", add_col))
    conn = _raw(tmp_path / "x.db")
    migrate(conn, reg)
    real_inspect = runner.inspect
    calls = {"n": 0}

    def stale_then_real(c, m):
        calls["n"] += 1
        if calls["n"] == 1:
            return MigrationStatus(current=1, latest=2, pending=[2], ahead=False)
        return real_inspect(c, m)

    with patch.object(runner, "inspect", side_effect=stale_then_real):
        s = migrate(conn, reg)
    assert s.error is None and s.applied == [] and s.current == 2


# --- repository ---------------------------------------------------------------------

def test_claim_takes_oldest_pending_once(fresh_db):
    from app.database import create_job
    from app.jobs.repository import claim_next_job

    create_job("a", natural_query="q1")
    create_job("b", natural_query="q2")
    first = claim_next_job("w1")
    second = claim_next_job("w2")
    assert (first["id"], second["id"]) == ("a", "b")
    assert first["status"] == "processing" and first["worker_id"] == "w1"
    assert first["claimed_at"] and first["heartbeat_at"]
    assert claim_next_job("w3") is None


def test_concurrent_claims_never_share_a_job(fresh_db):
    from app.database import create_job
    from app.jobs.repository import claim_next_job

    for i in range(20):
        create_job(f"j{i:02d}", natural_query="q")
    claimed, lock = [], threading.Lock()

    def worker(name):
        while (job := claim_next_job(name)) is not None:
            with lock:
                claimed.append(job["id"])

    threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(claimed) == [f"j{i:02d}" for i in range(20)]


def test_touch_heartbeat_only_for_owner(fresh_db):
    from app.database import create_job, get_job
    from app.jobs.repository import claim_next_job, touch_heartbeat

    create_job("a", natural_query="q")
    claim_next_job("w1")
    conn = _raw(fresh_db)
    conn.execute("UPDATE jobs SET heartbeat_at = ? WHERE id = 'a'", (_old(500),))
    conn.commit()
    assert touch_heartbeat("a", "other") is False
    assert touch_heartbeat("a", "w1") is True
    assert get_job("a")["heartbeat_at"] > _old(10)


def test_fail_abandoned_jobs_by_status_and_age(fresh_db):
    from app.database import create_job, get_job
    from app.jobs.repository import fail_abandoned_jobs

    create_job("fresh", natural_query="q")
    create_job("stale", natural_query="q")
    create_job("done", natural_query="q")
    conn = _raw(fresh_db)
    conn.execute("UPDATE jobs SET status='processing', heartbeat_at=? WHERE id='stale'", (_old(900),))
    conn.execute("UPDATE jobs SET status='processing', heartbeat_at=? WHERE id='fresh'", (_old(5),))
    conn.execute("UPDATE jobs SET status='completed' WHERE id='done'")
    conn.commit()

    assert fail_abandoned_jobs(("processing",), older_than_seconds=300) == ["stale"]
    assert get_job("stale")["status"] == "failed" and get_job("stale")["error_message"]
    assert get_job("fresh")["status"] == "processing"
    assert get_job("done")["status"] == "completed"


def test_job_logs_append_and_list_after(fresh_db):
    from app.jobs.repository import append_job_log, list_job_logs

    append_job_log("a", "bir", 1)
    append_job_log("b", "başka", 1)
    append_job_log("a", "iki", 2)
    logs = list_job_logs("a")
    assert [(l["message"], l["step"]) for l in logs] == [("bir", 1), ("iki", 2)]
    assert [l["message"] for l in list_job_logs("a", after_id=logs[0]["id"])] == ["iki"]


# --- executor + inline wrapper ------------------------------------------------------

def test_execute_job_persists_logs_and_result(fresh_db):
    from app.database import create_job, get_job
    from app.jobs.executor import execute_job
    from app.jobs.repository import list_job_logs

    create_job("a", natural_query="q")
    seen = []
    with patch("app.sql_pipeline.SQLGenerationPipeline", _pipeline_mock()), \
         patch("app.trace.dependencies.get_trace_store"):
        execute_job("a", on_log=seen.append)
    job = get_job("a")
    assert job["status"] == "completed" and job["result_sql"] == "SELECT 1"
    messages = [l["message"] for l in list_job_logs("a")]
    assert "şema yüklendi" in messages and len(messages) == 2
    assert [e["message"] for e in seen] == messages


def test_inline_wrapper_keeps_sse_cache_and_eof(fresh_db):
    from app import main as app_main
    from app.database import create_job

    create_job("inline-1", natural_query="q")
    q = __import__("queue").Queue()
    app_main.job_queues["inline-1"] = [q]
    try:
        with patch("app.sql_pipeline.SQLGenerationPipeline", _pipeline_mock()), \
             patch("app.trace.dependencies.get_trace_store"):
            app_main.process_job_pipeline("inline-1")
    finally:
        app_main.job_queues.pop("inline-1", None)
    assert [e["message"] for e in app_main.job_logs_cache["inline-1"]][0] == "şema yüklendi"
    items = []
    while not q.empty():
        items.append(q.get())
    assert items[-1] == "EOF"


# --- worker ---------------------------------------------------------------------------

def _worker(**kw):
    from app.jobs.worker import JobWorker

    kw.setdefault("poll_seconds", 0.01)
    kw.setdefault("stale_seconds", 300)
    return JobWorker(worker_id="test-worker", **kw)


def test_worker_run_once_executes_pending_job(fresh_db):
    from app.database import create_job, get_job

    create_job("a", natural_query="q")
    w = _worker()
    with patch("app.sql_pipeline.SQLGenerationPipeline", _pipeline_mock()), \
         patch("app.trace.dependencies.get_trace_store"):
        assert w.run_once() is True
        assert w.run_once() is False
    job = get_job("a")
    assert job["status"] == "completed" and job["worker_id"] == "test-worker"


def test_worker_records_failure(fresh_db):
    from app.database import create_job, get_job

    create_job("a", natural_query="q")
    result = {"success": False, "generated_sql": "", "error": "LLM down", "error_code": None}
    with patch("app.sql_pipeline.SQLGenerationPipeline", _pipeline_mock(result=result)), \
         patch("app.trace.dependencies.get_trace_store"):
        _worker().run_once()
    assert get_job("a")["status"] == "failed" and get_job("a")["error_message"] == "LLM down"


def test_worker_respects_cancellation(fresh_db):
    from app.database import create_job, get_job, update_job_status

    create_job("a", natural_query="q")
    cancel = lambda kwargs: update_job_status("a", "cancelled")  # noqa: E731
    with patch("app.sql_pipeline.SQLGenerationPipeline", _pipeline_mock(side_effect=cancel)), \
         patch("app.trace.dependencies.get_trace_store"):
        _worker().run_once()
    assert get_job("a")["status"] == "cancelled"


def test_worker_heartbeats_while_running(fresh_db):
    from app.database import create_job, get_job

    create_job("a", natural_query="q")
    beats = []

    def slow(kwargs):
        time.sleep(0.35)
        beats.append(get_job("a")["heartbeat_at"])

    with patch("app.sql_pipeline.SQLGenerationPipeline", _pipeline_mock(side_effect=slow)), \
         patch("app.trace.dependencies.get_trace_store"):
        _worker(heartbeat_seconds=0.05).run_once()
    assert beats[0] > get_job("a")["claimed_at"]


def test_worker_fails_stale_processing_jobs(fresh_db):
    from app.database import create_job, get_job

    create_job("dead", natural_query="q")
    conn = _raw(fresh_db)
    conn.execute(
        "UPDATE jobs SET status='processing', worker_id='gone', heartbeat_at=? WHERE id='dead'", (_old(900),)
    )
    conn.commit()
    assert _worker(stale_seconds=300).run_once() is False
    job = get_job("dead")
    assert job["status"] == "failed" and "worker" in job["error_message"].lower()


def test_worker_run_forever_stops_on_event(fresh_db):
    stop = threading.Event()
    w = _worker()
    t = threading.Thread(target=w.run_forever, args=(stop,))
    t.start()
    time.sleep(0.05)
    stop.set()
    t.join(timeout=2)
    assert not t.is_alive()


def test_worker_liveness_file_and_healthcheck(fresh_db, tmp_path):
    from app.jobs.worker import healthcheck

    alive = tmp_path / "alive"
    assert healthcheck(str(alive), max_age_seconds=60) is False
    _worker(liveness_path=str(alive)).run_once()
    assert healthcheck(str(alive), max_age_seconds=60) is True
    old = time.time() - 600
    os.utime(alive, (old, old))
    assert healthcheck(str(alive), max_age_seconds=60) is False


# --- API modes -------------------------------------------------------------------------

def _client(monkeypatch, mode):
    monkeypatch.setenv("NL2SQL_JOB_EXECUTION_MODE", mode)
    get_settings.cache_clear()
    from app.main import app

    return TestClient(app)


def test_worker_mode_endpoint_only_enqueues(monkeypatch, fresh_db):
    from app.database import get_job

    client = _client(monkeypatch, "worker")
    with patch("app.main.process_job_pipeline") as inline:
        r = client.post("/api/jobs/without-file", json={"natural_query": "kaç hasta var"},
                        headers={"X-API-Key": DEV_DEFAULT_API_KEY})
    assert r.status_code == 200
    assert not inline.called
    assert get_job(r.json()["job"]["id"])["status"] == "pending"


def test_inline_mode_endpoint_runs_in_process(monkeypatch, fresh_db):
    client = _client(monkeypatch, "inline")
    with patch("app.main.process_job_pipeline") as inline:
        r = client.post("/api/jobs/without-file", json={"natural_query": "kaç hasta var"},
                        headers={"X-API-Key": DEV_DEFAULT_API_KEY})
    assert r.status_code == 200 and inline.called


def test_worker_mode_sse_replays_persisted_logs(monkeypatch, fresh_db):
    from app.database import create_job, update_job_status
    from app.jobs.repository import append_job_log

    create_job("s1", natural_query="q")
    append_job_log("s1", "worker log satırı", 2)
    update_job_status("s1", "completed", result_sql="SELECT 1")
    client = _client(monkeypatch, "worker")
    r = client.get("/api/jobs/s1/stream", headers={"X-API-Key": DEV_DEFAULT_API_KEY})
    assert r.status_code == 200
    import json

    events = [json.loads(line[len("data: "):]) for line in r.text.splitlines() if line.startswith("data: ")]
    assert [(e["message"], e["step"]) for e in events] == [("worker log satırı", 2)]


def test_inline_startup_fails_orphaned_jobs(monkeypatch, fresh_db):
    from app.database import create_job, get_job
    from app.jobs.startup import recover_jobs_on_api_startup

    create_job("orphan-p", natural_query="q")
    create_job("orphan-r", natural_query="q")
    conn = _raw(fresh_db)
    conn.execute("UPDATE jobs SET status='processing' WHERE id='orphan-r'")
    conn.commit()

    monkeypatch.setenv("NL2SQL_JOB_EXECUTION_MODE", "worker")
    get_settings.cache_clear()
    assert recover_jobs_on_api_startup() == []  # worker mode: the worker owns recovery
    monkeypatch.setenv("NL2SQL_JOB_EXECUTION_MODE", "inline")
    get_settings.cache_clear()
    assert sorted(recover_jobs_on_api_startup()) == ["orphan-p", "orphan-r"]
    assert get_job("orphan-p")["status"] == "failed"


def _startup_warnings(monkeypatch, mode):
    monkeypatch.setenv("NL2SQL_JOB_EXECUTION_MODE", mode)
    get_settings.cache_clear()
    from app.startup_validation import validate_runtime_config

    with patch("app.startup_validation.get_config", return_value="db-key"):
        return {w.code: w for w in validate_runtime_config().warnings}


def test_job_queue_stalled_warning(monkeypatch, fresh_db):
    from app.database import create_job

    create_job("waiting", natural_query="q")
    conn = _raw(fresh_db)
    conn.execute("UPDATE jobs SET created_at = ? WHERE id = 'waiting'", (_old(3600),))
    conn.commit()
    w = _startup_warnings(monkeypatch, "worker")
    assert w["JOB_QUEUE_STALLED"].severity == "warning"
    assert "JOB_QUEUE_STALLED" not in _startup_warnings(monkeypatch, "inline")


def test_invalid_execution_mode_is_rejected(monkeypatch):
    from pydantic import ValidationError
    from app.settings import Settings

    monkeypatch.setenv("NL2SQL_JOB_EXECUTION_MODE", "celery")
    with pytest.raises(ValidationError):
        Settings()
