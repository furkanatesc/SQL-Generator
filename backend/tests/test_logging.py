"""Sprint 32.9 — Logging.

One `configure_logging()` for the API, worker and CLIs: configurable level and text/JSON format,
request_id/job_id context on every record, secret redaction, uvicorn routed through the same
handler. Before this, `app.*` INFO records were silently dropped in the API process.
"""
import io
import json
import logging
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.logging_config import configure_logging, job_id_var, log_context, request_id_var
from app.settings import DEV_DEFAULT_API_KEY, get_settings


@pytest.fixture
def capture():
    """Install the SQLGen handler on an in-memory stream; restore the default afterwards."""
    stream = io.StringIO()
    installed = []

    def install(fmt="json", level="INFO"):
        stream.seek(0)
        stream.truncate()
        installed.append(configure_logging(level=level, fmt=fmt, stream=stream))
        return stream

    yield install
    root = logging.getLogger()
    for h in installed:
        if h in root.handlers:
            root.removeHandler(h)
    configure_logging()


def _lines(stream):
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


def test_json_lines_with_core_fields(capture):
    s = capture("json")
    logging.getLogger("app.demo").info("hello %s", "world")
    [rec] = _lines(s)
    assert rec["message"] == "hello world" and rec["level"] == "INFO" and rec["logger"] == "app.demo"
    assert rec["ts"].endswith("+00:00")


def test_embedded_json_event_is_merged(capture):
    s = capture("json")
    logging.getLogger("app.request_logging").info(json.dumps({"event": "http_request", "status_code": 200}))
    [rec] = _lines(s)
    assert rec["event"] == "http_request" and rec["status_code"] == 200 and "message" not in rec


def test_context_fields(capture):
    s = capture("json")
    with log_context(request_id="req-1", job_id="job-9"):
        logging.getLogger("app.demo").warning("inside")
    logging.getLogger("app.demo").warning("outside")
    inside, outside = _lines(s)
    assert (inside["request_id"], inside["job_id"]) == ("req-1", "job-9")
    assert "request_id" not in outside and request_id_var.get() is None and job_id_var.get() is None


def test_text_format_shows_context(capture):
    s = capture("text")
    with log_context(request_id="req-7"):
        logging.getLogger("app.demo").info("plain")
    line = s.getvalue().strip()
    assert "INFO app.demo [req=req-7] plain" in line


def test_level_filters(capture):
    s = capture("json", level="WARNING")
    logging.getLogger("app.demo").info("dropped")
    logging.getLogger("app.demo").warning("kept")
    assert [r["message"] for r in _lines(s)] == ["kept"]


def test_exception_is_logged(capture):
    s = capture("json")
    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("app.demo").exception("failed")
    [rec] = _lines(s)
    assert "ValueError: boom" in rec["exc_info"]


def test_redacts_patterns_known_secrets_and_tracebacks(capture, monkeypatch, tmp_path):
    secret_file = tmp_path / "k"
    secret_file.write_text("file-held-secret-123")
    monkeypatch.setenv("NVIDIA_API_KEY_FILE", str(secret_file))
    s = capture("json")
    log = logging.getLogger("app.demo")
    log.warning("calling with api_key=abc123 and token nvapi-XYZ")
    log.warning("upstream echoed %s", "file-held-secret-123")
    try:
        raise RuntimeError("leak file-held-secret-123")
    except RuntimeError:
        log.exception("crash")
    out = s.getvalue()
    for secret in ("abc123", "nvapi-XYZ", "file-held-secret-123"):
        assert secret not in out
    assert "[REDACTED]" in out


def test_redaction_keeps_json_events_valid(capture):
    s = capture("json")
    logging.getLogger("app.request_logging").info(
        json.dumps({"event": "http_request", "path": "/api/jobs?api_key=leaky", "status_code": 403})
    )
    [rec] = _lines(s)  # still one valid JSON object, merged
    assert rec["event"] == "http_request" and rec["status_code"] == 403
    assert "leaky" not in rec["path"] and "[REDACTED]" in rec["path"]


def test_request_id_flows_into_logs_inside_a_request(capture, monkeypatch):
    from app.main import app  # importing app.main configures logging; capture after it

    s = capture("json")

    seen = {}

    def spy_list_jobs(**kwargs):
        logging.getLogger("app.demo").info("listing jobs")
        seen["rid"] = request_id_var.get()
        return []

    with patch("app.main.list_jobs", spy_list_jobs):
        r = TestClient(app).get("/api/jobs", headers={"X-API-Key": DEV_DEFAULT_API_KEY, "X-Request-ID": "rid-42"})
    assert r.status_code == 200 and seen["rid"] == "rid-42"
    records = _lines(s)
    assert any(rec.get("message") == "listing jobs" and rec.get("request_id") == "rid-42" for rec in records)
    http = [rec for rec in records if rec.get("event") == "http_request"]
    assert http and http[-1]["request_id"] == "rid-42"


def test_executor_sets_job_context(capture, monkeypatch, tmp_path):
    from unittest.mock import MagicMock

    from app.database import create_job, init_db, set_config

    monkeypatch.setenv("SQLGEN_DB_PATH", str(tmp_path / "app.db"))
    get_settings.cache_clear()
    init_db()
    set_config("nvidia_api_key", "real-key")
    create_job("job-ctx", natural_query="q")
    s = capture("json")

    instance = MagicMock()

    def run(**kwargs):
        logging.getLogger("app.sql_pipeline").info("inside pipeline")
        return {"success": True, "generated_sql": "SELECT 1", "error": None, "attempts": []}

    instance.run_pipeline.side_effect = run
    from app.jobs.executor import execute_job

    with patch("app.sql_pipeline.SQLGenerationPipeline", MagicMock(return_value=instance)), \
         patch("app.trace.dependencies.get_trace_store"):
        execute_job("job-ctx", request_id="req-from-api")
    rec = next(r for r in _lines(s) if r.get("message") == "inside pipeline")
    assert rec["job_id"] == "job-ctx" and rec["request_id"] == "req-from-api"
    assert job_id_var.get() is None


def test_uvicorn_routed_and_access_quieted(capture):
    capture("json")
    assert logging.getLogger("uvicorn.error").propagate is True
    assert logging.getLogger("uvicorn.access").level == logging.WARNING


def test_configure_is_idempotent_and_keeps_foreign_handlers(capture):
    root = logging.getLogger()
    foreign = logging.NullHandler()
    root.addHandler(foreign)
    try:
        capture("json")
        capture("text")
        ours = [h for h in root.handlers if getattr(h, "_sqlgen_handler", False)]
        assert len(ours) == 1 and foreign in root.handlers
    finally:
        root.removeHandler(foreign)


def test_log_settings_validated_and_in_contract(monkeypatch):
    from pydantic import ValidationError

    from app.config_contract import known_env_names
    from app.settings import Settings

    assert {"NL2SQL_LOG_LEVEL", "NL2SQL_LOG_FORMAT"} <= known_env_names()
    monkeypatch.setenv("NL2SQL_LOG_FORMAT", "xml")
    with pytest.raises(ValidationError):
        Settings()
    monkeypatch.setenv("NL2SQL_LOG_FORMAT", "json")
    monkeypatch.setenv("NL2SQL_LOG_LEVEL", "LOUD")
    with pytest.raises(ValidationError):
        Settings()
