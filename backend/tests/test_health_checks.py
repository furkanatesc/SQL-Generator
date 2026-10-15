"""Sprint 32.7 — Health Checks.

`/ready` gains per-component `checks` (status ok|degraded|fail + a short reason code) derived from
one startup-validation run plus direct database / disk / LLM-key probes. `degraded` never fails
readiness; any `fail` does. The worker healthcheck now also requires database access.
"""
import os
import sqlite3
from collections import namedtuple
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.settings import get_settings

DiskUsage = namedtuple("DiskUsage", "total used free")
MB = 1024 * 1024


class _W:
    def __init__(self, code, severity):
        self.code, self.severity, self.message = code, severity, ""


def _result(*warnings):
    class R:
        pass

    r = R()
    r.warnings = list(warnings)
    return r


@pytest.fixture
def ready(monkeypatch):
    """Call /ready with the given warnings, free disk space and LLM key presence."""
    from app.main import app

    client = TestClient(app)

    def call(*warnings, free_mb=10_000, llm_key="k", min_free_mb=None):
        if min_free_mb is not None:
            monkeypatch.setenv("NL2SQL_HEALTH_MIN_FREE_DISK_MB", str(min_free_mb))
        get_settings.cache_clear()
        monkeypatch.setattr("app.health.validate_runtime_config", lambda: _result(*warnings))
        monkeypatch.setattr("app.health.shutil.disk_usage", lambda p: DiskUsage(100_000 * MB, 0, free_mb * MB))
        monkeypatch.setattr("app.health.resolve_secret", lambda name: llm_key)
        monkeypatch.setattr("app.health.get_config", lambda key: None)
        return client.get("/ready")

    return call


def test_healthy_reports_every_component_ok(ready):
    r = ready()
    assert r.status_code == 200
    checks = r.json()["checks"]
    assert set(checks) == {"database", "migrations", "api_key", "secrets", "upload_dir", "job_queue",
                           "disk", "llm", "config"}
    assert all(c == {"status": "ok", "reason": None} for c in checks.values())


@pytest.mark.parametrize(
    "code, component, reason",
    [
        ("DB_MIGRATIONS_PENDING", "migrations", "db_migrations_pending"),
        ("DB_SCHEMA_AHEAD", "migrations", "db_schema_ahead"),
        ("API_KEY_NOT_CONFIGURED", "api_key", "api_key_not_configured"),
        ("API_KEY_INSECURE_DEFAULT", "api_key", "api_key_insecure_default"),
        ("SECRET_FILE_UNREADABLE", "secrets", "secret_file_unreadable"),
        ("UPLOAD_DIR_NOT_WRITABLE", "upload_dir", "upload_dir_not_writable"),
        ("CORS_WILDCARD_IN_PRODUCTION", "config", "cors_wildcard_in_production"),
    ],
)
def test_critical_warnings_fail_their_component(ready, code, component, reason):
    r = ready(_W(code, "critical"))
    assert r.status_code == 503
    assert r.json()["checks"][component] == {"status": "fail", "reason": reason}


@pytest.mark.parametrize(
    "code, component",
    [("API_KEY_ENV_SHADOWED", "api_key"), ("SECRET_SOURCE_CONFLICT", "secrets"),
     ("JOB_QUEUE_STALLED", "job_queue"), ("UNKNOWN_CONFIG_ENV_VAR", "config")],
)
def test_non_critical_warnings_degrade_without_failing_readiness(ready, code, component):
    r = ready(_W(code, "warning"))
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.json()["checks"][component] == {"status": "degraded", "reason": code.lower()}


def test_fail_outranks_degraded_in_one_component(ready):
    r = ready(_W("API_KEY_ENV_SHADOWED", "warning"), _W("API_KEY_INSECURE_DEFAULT", "critical"))
    assert r.json()["checks"]["api_key"] == {"status": "fail", "reason": "api_key_insecure_default"}


def test_database_unreachable(ready, monkeypatch):
    def boom():
        raise sqlite3.OperationalError("locked")

    monkeypatch.setattr("app.health.get_db_connection", boom)
    r = ready()
    assert r.status_code == 503 and r.json()["database_reachable"] is False
    assert r.json()["checks"]["database"] == {"status": "fail", "reason": "unreachable"}


def test_low_disk_space_fails_readiness(ready):
    r = ready(free_mb=50, min_free_mb=100)
    assert r.status_code == 503 and r.json()["status"] == "unhealthy"
    assert r.json()["checks"]["disk"] == {"status": "fail", "reason": "low_disk_space"}
    # the legacy boolean fields stay as they were
    assert r.json()["database_reachable"] is True and r.json()["critical_warnings_count"] == 0


def test_disk_nearly_full_is_degraded(ready):
    r = ready(free_mb=150, min_free_mb=100)
    assert r.status_code == 200
    assert r.json()["checks"]["disk"] == {"status": "degraded", "reason": "disk_space_low_soon"}


def test_disk_check_can_be_disabled(ready):
    r = ready(free_mb=0, min_free_mb=0)
    assert r.status_code == 200
    assert r.json()["checks"]["disk"] == {"status": "ok", "reason": "disabled"}


def test_missing_llm_key_is_degraded(ready):
    r = ready(llm_key=None)
    assert r.status_code == 200
    assert r.json()["checks"]["llm"] == {"status": "degraded", "reason": "llm_key_not_configured"}


def test_ready_body_leaks_no_paths_or_values(ready, tmp_path):
    r = ready(_W("SECRET_FILE_UNREADABLE", "critical"), free_mb=50, min_free_mb=100)
    body = r.text.lower()
    for forbidden in ("sqlgen.db", "/run/secrets", "uploads/", str(tmp_path).lower(), "\\\\"):
        assert forbidden not in body


def test_health_min_free_disk_setting_is_validated(monkeypatch):
    from pydantic import ValidationError

    from app.settings import Settings

    monkeypatch.setenv("NL2SQL_HEALTH_MIN_FREE_DISK_MB", "-5")
    with pytest.raises(ValidationError):
        Settings()


# --- worker healthcheck --------------------------------------------------------------------------

def test_worker_healthcheck_requires_database(tmp_path, monkeypatch):
    from app.jobs import worker

    alive = tmp_path / "alive"
    alive.write_text("")
    assert worker.healthcheck(str(alive)) is True

    def boom():
        raise sqlite3.OperationalError("unreachable")

    monkeypatch.setattr("app.database.get_db_connection", boom)
    assert worker.healthcheck(str(alive)) is False
