"""Sprint 32.2 — Secrets Management.

`app/secret_resolver.py` is the single place secrets are read: `<NAME>_FILE` (Docker secrets
convention) wins over the plain `<NAME>` env var. These tests cover the resolver, the call
sites wired to it (auth, LLM key, trace redaction) and the secret-source startup warnings.
"""
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config_contract import ENV_CONTRACT
from app.secret_resolver import (
    MAX_SECRET_FILE_BYTES,
    SECRET_FILE_VARS,
    known_secret_values,
    resolve_secret,
    resolve_secret_detail,
)
from app.settings import get_settings

SENTINEL = "sentinel-file-secret-32-2"


def _write(tmp_path, content, name="secret"):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return str(path)


# --- resolver ------------------------------------------------------------------

def test_secret_file_vars_cover_exactly_the_contract_secrets():
    assert set(SECRET_FILE_VARS) == {v.name for v in ENV_CONTRACT if v.secret}
    for name, file_var in SECRET_FILE_VARS.items():
        assert file_var == name + "_FILE"


def test_env_value_is_used_when_no_file_var():
    r = resolve_secret_detail("NL2SQL_API_KEY", {"NL2SQL_API_KEY": "env-key"})
    assert (r.source, r.value, r.error, r.conflict) == ("env", "env-key", None, False)


def test_missing_and_empty_env_resolve_to_none():
    assert resolve_secret_detail("NL2SQL_API_KEY", {}).source == "none"
    r = resolve_secret_detail("NL2SQL_API_KEY", {"NL2SQL_API_KEY": "", "NL2SQL_API_KEY_FILE": ""})
    assert (r.source, r.value) == ("none", None)


def test_file_value_is_stripped(tmp_path):
    path = _write(tmp_path, "  file-key\r\n")
    assert resolve_secret("NVIDIA_API_KEY", {"NVIDIA_API_KEY_FILE": path}) == "file-key"


def test_file_wins_over_env_and_flags_conflict(tmp_path):
    path = _write(tmp_path, "file-key\n")
    r = resolve_secret_detail(
        "NL2SQL_API_KEY", {"NL2SQL_API_KEY": "env-key", "NL2SQL_API_KEY_FILE": path}
    )
    assert (r.source, r.value, r.conflict) == ("file", "file-key", True)


@pytest.mark.parametrize(
    "content, error",
    [("", "empty"), ("  \n", "empty"), ("x" * (MAX_SECRET_FILE_BYTES + 1), "too_large")],
    ids=["empty", "whitespace", "too_large"],
)
def test_bad_file_content_is_an_error_without_env_fallback(tmp_path, content, error):
    path = _write(tmp_path, content)
    r = resolve_secret_detail(
        "NL2SQL_API_KEY", {"NL2SQL_API_KEY": "env-key", "NL2SQL_API_KEY_FILE": path}
    )
    assert (r.source, r.value, r.error) == ("file", None, error)


def test_missing_file_is_unreadable(tmp_path):
    r = resolve_secret_detail("NL2SQL_API_KEY", {"NL2SQL_API_KEY_FILE": str(tmp_path / "nope")})
    assert (r.source, r.value, r.error) == ("file", None, "unreadable")


def test_directory_is_unreadable(tmp_path):
    r = resolve_secret_detail("NL2SQL_API_KEY", {"NL2SQL_API_KEY_FILE": str(tmp_path)})
    assert r.error == "unreadable"


def test_unknown_secret_name_raises():
    with pytest.raises(KeyError):
        resolve_secret("SOME_OTHER_KEY", {})


def test_repr_never_contains_the_value(tmp_path):
    path = _write(tmp_path, SENTINEL)
    r = resolve_secret_detail("NL2SQL_API_KEY", {"NL2SQL_API_KEY_FILE": path})
    assert SENTINEL not in repr(r) and SENTINEL not in str(r)


def test_defaults_to_process_environment(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY_FILE", raising=False)
    monkeypatch.setenv("NVIDIA_API_KEY", "process-env-key")
    assert resolve_secret("NVIDIA_API_KEY") == "process-env-key"


def test_known_secret_values_collects_all_resolved(tmp_path):
    path = _write(tmp_path, "file-api-key")
    environ = {"NL2SQL_API_KEY_FILE": path, "NVIDIA_API_KEY": "env-nvidia"}
    assert known_secret_values(environ) == {"file-api-key", "env-nvidia"}


# --- call sites ------------------------------------------------------------------

@pytest.fixture
def file_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("NL2SQL_API_KEY", raising=False)
    monkeypatch.setenv("NL2SQL_API_KEY_FILE", _write(tmp_path, SENTINEL + "\n"))
    return SENTINEL


def test_verify_api_key_accepts_file_based_key(file_api_key):
    from app.auth import verify_api_key

    with patch("app.auth.get_config", return_value=None):
        assert verify_api_key(api_key_h=file_api_key, api_key_q=None) == file_api_key
        with pytest.raises(Exception) as exc:
            verify_api_key(api_key_h="wrong", api_key_q=None)
    assert exc.value.status_code == 403


def test_verify_api_key_db_key_still_wins(file_api_key):
    from app.auth import verify_api_key

    with patch("app.auth.get_config", return_value="db-key"):
        assert verify_api_key(api_key_h="db-key", api_key_q=None) == "db-key"
        with pytest.raises(Exception):
            verify_api_key(api_key_h=file_api_key, api_key_q=None)


def test_unreadable_key_file_is_not_configured(monkeypatch, tmp_path):
    from app.auth import verify_api_key

    monkeypatch.setenv("NL2SQL_API_KEY", "env-key")
    monkeypatch.setenv("NL2SQL_API_KEY_FILE", str(tmp_path / "missing"))
    with patch("app.auth.get_config", return_value=None):
        with pytest.raises(Exception) as exc:
            verify_api_key(api_key_h="env-key", api_key_q=None)
    assert exc.value.status_code == 500


def test_llm_key_reads_file(monkeypatch, tmp_path):
    from app.llm_client import get_nvidia_api_key

    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setenv("NVIDIA_API_KEY_FILE", _write(tmp_path, "nvidia-from-file"))
    assert get_nvidia_api_key() == "nvidia-from-file"


@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
def test_pipeline_redacts_file_based_secret(_prompt, monkeypatch, tmp_path):
    # The value lives only in the file, so the legacy KEY/SECRET env scan cannot see it.
    import json
    from unittest.mock import MagicMock

    from app.sql_pipeline import SQLGenerationPipeline

    file_secret = "nvidia-file-only-secret-32-2"
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setenv("NVIDIA_API_KEY_FILE", _write(tmp_path, file_secret))
    llm = MagicMock()
    llm.generate_sql.side_effect = Exception(f"upstream echoed {file_secret} back")
    trace_store = MagicMock()
    del trace_store.save_legacy
    pipeline = SQLGenerationPipeline(trace_store=trace_store, llm_provider=llm)

    with patch("app.sql_pipeline.SchemaPruner.prune_schema", return_value={"tables": {}}):
        result = pipeline.run_pipeline(job_id="t", natural_query="q", max_attempts=1)

    trace = trace_store.save.call_args[0][0]
    assert file_secret not in json.dumps(result, default=str)
    assert file_secret not in json.dumps(getattr(trace, "__dict__", trace), default=str)


# --- startup warnings -------------------------------------------------------------

def _warnings(monkeypatch, env, db_key=None):
    for k in [k for k in os.environ if k.upper().startswith(("NL2SQL_", "NVIDIA_"))]:
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    from app.startup_validation import validate_runtime_config

    with patch("app.startup_validation.get_config", return_value=db_key):
        return {w.code: w for w in validate_runtime_config().warnings}


def test_file_key_satisfies_api_key_configured(monkeypatch, tmp_path):
    w = _warnings(monkeypatch, {"NL2SQL_API_KEY_FILE": _write(tmp_path, "k")})
    assert "API_KEY_NOT_CONFIGURED" not in w
    assert "SECRET_FILE_UNREADABLE" not in w


def test_unreadable_secret_file_is_critical_and_names_var_only(monkeypatch, tmp_path):
    missing = str(tmp_path / "missing-secret-path")
    w = _warnings(monkeypatch, {"NVIDIA_API_KEY_FILE": missing}, db_key="db-key")
    assert w["SECRET_FILE_UNREADABLE"].severity == "critical"
    assert "NVIDIA_API_KEY_FILE" in w["SECRET_FILE_UNREADABLE"].message
    assert "missing-secret-path" not in w["SECRET_FILE_UNREADABLE"].message


def test_source_conflict_is_a_warning(monkeypatch, tmp_path):
    w = _warnings(
        monkeypatch,
        {"NL2SQL_API_KEY": "env-key", "NL2SQL_API_KEY_FILE": _write(tmp_path, "file-key")},
    )
    assert w["SECRET_SOURCE_CONFLICT"].severity == "warning"
    assert "NL2SQL_API_KEY" in w["SECRET_SOURCE_CONFLICT"].message
    assert "env-key" not in w["SECRET_SOURCE_CONFLICT"].message


def test_db_key_shadowing_env_key_is_a_warning(monkeypatch):
    w = _warnings(monkeypatch, {"NL2SQL_API_KEY": "env-key"}, db_key="db-key")
    assert w["API_KEY_ENV_SHADOWED"].severity == "warning"
    for value in ("env-key", "db-key"):
        assert value not in w["API_KEY_ENV_SHADOWED"].message


def test_no_shadow_warning_when_keys_match_or_one_side_missing(monkeypatch):
    assert "API_KEY_ENV_SHADOWED" not in _warnings(monkeypatch, {"NL2SQL_API_KEY": "same"}, db_key="same")
    assert "API_KEY_ENV_SHADOWED" not in _warnings(monkeypatch, {}, db_key="db-key")
    assert "API_KEY_ENV_SHADOWED" not in _warnings(monkeypatch, {"NL2SQL_API_KEY": "k"})


def test_insecure_default_detected_from_file(monkeypatch, tmp_path):
    from app.settings import DEV_DEFAULT_API_KEY

    w = _warnings(
        monkeypatch,
        {"NL2SQL_ENVIRONMENT": "production", "NL2SQL_API_KEY_FILE": _write(tmp_path, DEV_DEFAULT_API_KEY)},
    )
    assert "API_KEY_INSECURE_DEFAULT" in w


# --- no leak ---------------------------------------------------------------------

def test_file_secret_never_surfaces_in_diagnostics(file_api_key):
    from app.main import app, verify_api_key

    get_settings.cache_clear()
    app.dependency_overrides[verify_api_key] = lambda: True
    try:
        client = TestClient(app)
        for path in ("/health", "/ready", "/api/v1/admin/config", "/api/v1/admin/overview"):
            assert SENTINEL not in client.get(path).text, f"file secret leaked via {path}"
    finally:
        app.dependency_overrides.clear()
