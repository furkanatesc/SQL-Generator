"""Sprint 32.0 — production API-key hardening.

`init_db` used to seed the public dev key into `configs.api_key` unconditionally, and
`verify_api_key` prefers the DB key over `NL2SQL_API_KEY`. In production that silently
ignored the operator's key and let the publicly known dev key authenticate (caught by
the CI `prod-compose-smoke` job). Production-like environments now skip the seed, and
startup validation flags the dev default as a critical (readiness-failing) warning.
"""
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.auth import verify_api_key
from app.database import get_config, init_db
from app.settings import DEV_DEFAULT_API_KEY, get_settings
from app.startup_validation import validate_runtime_config


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLGEN_DB_PATH", str(tmp_path / "fresh.db"))
    return tmp_path


def _codes(result):
    return {w.code: w for w in result.warnings}


# --- init_db seeding ------------------------------------------------------------

@pytest.mark.parametrize("environment", ["production", "prod-eu", "PRODUCTION"])
def test_init_db_does_not_seed_dev_key_in_production(fresh_db, monkeypatch, environment):
    monkeypatch.setenv("NL2SQL_ENVIRONMENT", environment)
    get_settings.cache_clear()
    init_db()
    assert get_config("api_key") is None


@pytest.mark.parametrize("environment", ["local", "ci"])
def test_init_db_still_seeds_dev_key_outside_production(fresh_db, monkeypatch, environment):
    monkeypatch.setenv("NL2SQL_ENVIRONMENT", environment)
    get_settings.cache_clear()
    init_db()
    assert get_config("api_key") == DEV_DEFAULT_API_KEY


def test_production_auth_uses_operator_key_not_dev_default(fresh_db, monkeypatch):
    monkeypatch.setenv("NL2SQL_ENVIRONMENT", "production")
    monkeypatch.setenv("NL2SQL_API_KEY", "operator-secret")
    get_settings.cache_clear()
    init_db()

    assert verify_api_key("operator-secret", None) == "operator-secret"
    with pytest.raises(HTTPException) as exc:
        verify_api_key(DEV_DEFAULT_API_KEY, None)
    assert exc.value.status_code == 403


# --- startup validation ---------------------------------------------------------

def _validate(monkeypatch, *, environment, db_key, env_key):
    monkeypatch.setenv("NL2SQL_ENVIRONMENT", environment)
    if env_key is None:
        monkeypatch.delenv("NL2SQL_API_KEY", raising=False)
    else:
        monkeypatch.setenv("NL2SQL_API_KEY", env_key)
    get_settings.cache_clear()
    with patch("app.startup_validation.get_config", return_value=db_key):
        return validate_runtime_config()


@pytest.mark.parametrize(
    "db_key,env_key",
    [(DEV_DEFAULT_API_KEY, None), (DEV_DEFAULT_API_KEY, "operator-secret"), (None, DEV_DEFAULT_API_KEY)],
)
def test_dev_default_effective_key_is_critical_in_production(monkeypatch, db_key, env_key):
    result = _validate(monkeypatch, environment="production", db_key=db_key, env_key=env_key)
    warning = _codes(result).get("API_KEY_INSECURE_DEFAULT")
    assert warning is not None and warning.severity == "critical"
    assert result.ok is False
    # Must not leak the secret itself or the config key name.
    assert DEV_DEFAULT_API_KEY not in warning.message
    assert "api_key" not in warning.message.lower()


def test_operator_key_in_production_is_not_flagged(monkeypatch):
    result = _validate(monkeypatch, environment="production", db_key=None, env_key="operator-secret")
    assert "API_KEY_INSECURE_DEFAULT" not in _codes(result)


def test_dev_default_is_allowed_outside_production(monkeypatch):
    result = _validate(monkeypatch, environment="local", db_key=DEV_DEFAULT_API_KEY, env_key=None)
    assert "API_KEY_INSECURE_DEFAULT" not in _codes(result)
