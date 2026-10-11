"""Sprint 32.1 — Environment Config Contract.

`app/config_contract.py` is the single machine-readable inventory of every runtime
environment variable. These tests keep it in lock-step with the code (Settings fields
and direct os.getenv reads), the operator docs and the production compose file, and
cover the UNKNOWN_CONFIG_ENV_VAR startup warning for mistyped NL2SQL_* variables.
"""
import ast
import os
import pathlib
import re
from unittest.mock import patch

import pytest
import yaml
from fastapi.testclient import TestClient

from app.config_contract import (
    CONTRACT_VERSION,
    ENV_CONTRACT,
    TEST_HARNESS_ENV_PREFIXES,
    find_unknown_prefixed_env,
    known_env_names,
)
from app.settings import Settings, get_settings
from app.startup_validation import validate_runtime_config

BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
APP_PREFIXED = re.compile(r"^(NL2SQL|SQLGEN|NVIDIA)_[A-Z0-9_]+$")

BY_NAME = {v.name: v for v in ENV_CONTRACT}


def _python_sources():
    return sorted(BACKEND_DIR.joinpath("app").rglob("*.py")) + [BACKEND_DIR / "mcp_server.py"]


def _is_os_environ(node):
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "environ"
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
    )


def _env_reads(tree):
    """Literal names passed to os.getenv / os.environ.get / os.environ[...]."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            func = node.func
            is_getenv = (
                isinstance(func, ast.Attribute)
                and func.attr == "getenv"
                and isinstance(func.value, ast.Name)
                and func.value.id == "os"
            )
            is_environ_get = (
                isinstance(func, ast.Attribute) and func.attr == "get" and _is_os_environ(func.value)
            )
            if is_getenv or is_environ_get:
                yield node.args[0].value
        elif (
            isinstance(node, ast.Subscript)
            and _is_os_environ(node.value)
            and isinstance(node.slice, ast.Constant)
        ):
            yield node.slice.value


@pytest.fixture(scope="module")
def parsed_sources():
    return {p: ast.parse(p.read_text(encoding="utf-8")) for p in _python_sources()}


# --- contract shape ---------------------------------------------------------------

def test_contract_is_versioned_and_unique():
    assert CONTRACT_VERSION == "v1"
    names = [v.name for v in ENV_CONTRACT]
    assert len(names) == len(set(names))
    assert known_env_names() == frozenset(names)
    for v in ENV_CONTRACT:
        assert v.source in {"settings", "direct"}
        assert v.description


def test_settings_fields_match_contract_exactly():
    from_settings = {"NL2SQL_" + field.upper() for field in Settings.model_fields}
    contract_settings = {v.name for v in ENV_CONTRACT if v.source == "settings"}
    assert from_settings == contract_settings


def test_secrets_and_production_requirements():
    assert {v.name for v in ENV_CONTRACT if v.secret} == {"NL2SQL_API_KEY", "NVIDIA_API_KEY"}
    assert {v.name for v in ENV_CONTRACT if v.required_in_production} == {
        "NL2SQL_ENVIRONMENT",
        "NL2SQL_API_KEY",
        "NL2SQL_CORS_ALLOW_ORIGINS",
        "NL2SQL_DEBUG_ENDPOINTS_ENABLED",
    }


# --- code <-> contract drift ---------------------------------------------------------

def test_every_env_read_in_code_is_in_contract(parsed_sources):
    unknown = {}
    for path, tree in parsed_sources.items():
        for name in _env_reads(tree):
            if name in BY_NAME or name.startswith(TEST_HARNESS_ENV_PREFIXES):
                continue
            unknown.setdefault(name, []).append(str(path.relative_to(BACKEND_DIR)))
    assert not unknown, f"env vars read in code but missing from app/config_contract.py: {unknown}"


def test_every_app_prefixed_literal_is_in_contract(parsed_sources):
    # Catches reads the call-shape scan misses (e.g. a multi-line os.getenv(...)).
    unknown = {}
    for path, tree in parsed_sources.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if APP_PREFIXED.match(node.value) and node.value not in BY_NAME:
                    unknown.setdefault(node.value, []).append(str(path.relative_to(BACKEND_DIR)))
    assert not unknown, f"app-prefixed names missing from the contract: {unknown}"


def test_every_direct_contract_entry_is_actually_read(parsed_sources):
    literals = {
        node.value
        for tree in parsed_sources.values()
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    dead = [v.name for v in ENV_CONTRACT if v.source == "direct" and v.name not in literals]
    assert not dead, f"contract lists direct env vars no code reads: {dead}"


# --- contract <-> docs / compose ---------------------------------------------------

def test_every_contract_var_is_documented():
    doc = (REPO_ROOT / "docs" / "env-contract.md").read_text(encoding="utf-8")
    missing = [v.name for v in ENV_CONTRACT if f"`{v.name}`" not in doc]
    assert not missing, f"docs/env-contract.md does not document: {missing}"


def test_production_required_vars_are_pinned_or_required_in_prod_compose():
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"))
    env = compose["services"]["backend"]["environment"]
    for v in ENV_CONTRACT:
        if not v.required_in_production:
            continue
        assert v.name in env, f"{v.name} missing from docker-compose.prod.yml backend env"
        value = str(env[v.name])
        if value.startswith("${"):
            assert value.startswith("${" + v.name + ":?"), f"{v.name} must be pinned or :? required"


def test_prod_compose_backend_env_uses_only_contract_vars():
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"))
    assert set(compose["services"]["backend"]["environment"]) <= known_env_names()


SENTINEL = "sentinel-secret-value-32-1"


@pytest.mark.parametrize("secret_var", [v.name for v in ENV_CONTRACT if v.secret])
def test_secret_values_never_surface_in_diagnostics(monkeypatch, secret_var):
    from app.main import app, verify_api_key

    monkeypatch.setenv(secret_var, SENTINEL)
    get_settings.cache_clear()
    app.dependency_overrides[verify_api_key] = lambda: True
    try:
        client = TestClient(app)
        for path in ("/health", "/ready", "/api/v1/admin/config", "/api/v1/admin/overview"):
            assert SENTINEL not in client.get(path).text, f"{secret_var} leaked via {path}"
    finally:
        app.dependency_overrides.clear()


# --- unknown NL2SQL_* detection ------------------------------------------------------

def test_find_unknown_prefixed_env_flags_typos_only():
    environ = {
        "NL2SQL_DEBUG_ENDPOINT_ENABLED": "false",  # typo (missing S)
        "nl2sql_cors_origins": "x",  # typo, lower-case (pydantic-settings is case-insensitive)
        "NL2SQL_ENVIRONMENT": "production",  # known
        "nl2sql_environment": "production",  # known, different case
        "NL2SQL_API_KEY": "k",  # known direct read
        "POSTGRES_TEST_HOST": "h",  # test harness, not NL2SQL_
        "PATH": "/usr/bin",
        "SQLGEN_UNKNOWN": "x",  # other prefix: out of scope
    }
    assert find_unknown_prefixed_env(environ) == ["NL2SQL_CORS_ORIGINS", "NL2SQL_DEBUG_ENDPOINT_ENABLED"]


def test_find_unknown_prefixed_env_empty_for_clean_env():
    assert find_unknown_prefixed_env({"NL2SQL_ENVIRONMENT": "local", "HOME": "/root"}) == []


def _validate_with(monkeypatch, extra_env):
    for k in [k for k in os.environ if k.upper().startswith("NL2SQL_")]:
        monkeypatch.delenv(k, raising=False)
    for k, v in extra_env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    with patch("app.startup_validation.get_config", return_value="db-key"):
        return {w.code: w for w in validate_runtime_config().warnings}


def test_unknown_env_var_emits_non_critical_warning_naming_it(monkeypatch):
    warnings = _validate_with(monkeypatch, {"NL2SQL_DEBUG_ENDPOINT_ENABLED": "s3cr3t-value"})
    w = warnings.get("UNKNOWN_CONFIG_ENV_VAR")
    assert w is not None
    assert w.severity == "warning"
    assert "NL2SQL_DEBUG_ENDPOINT_ENABLED" in w.message
    assert "s3cr3t-value" not in w.message


def test_unknown_env_warning_does_not_fail_readiness(monkeypatch):
    from app.health import check_readiness

    _validate_with(monkeypatch, {"NL2SQL_TYPO_VAR": "x"})
    with patch("app.startup_validation.get_config", return_value="db-key"):
        assert check_readiness()["critical_warnings_count"] == 0


def test_known_env_vars_do_not_emit_unknown_warning(monkeypatch):
    warnings = _validate_with(
        monkeypatch,
        {"NL2SQL_ENVIRONMENT": "local", "NL2SQL_API_KEY": "k", "NL2SQL_TRACE_DB_PATH": "t.db"},
    )
    assert "UNKNOWN_CONFIG_ENV_VAR" not in warnings
