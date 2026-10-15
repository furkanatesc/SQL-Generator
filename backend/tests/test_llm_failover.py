"""Sprint 32.10 — LLM Failover.

Typed LLM errors, a model chain (primary + NL2SQL_LLM_FALLBACK_MODELS on the same NIM endpoint)
with failover on transient / model-unavailable errors (never on 401/403), and a per-model
circuit breaker so a dead model is skipped instead of costing every call its full retry budget.
"""
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.settings import DEV_DEFAULT_API_KEY, get_settings


def _resp(status, content="SELECT 1"):
    r = MagicMock()
    r.status_code = status
    r.text = "upstream says no"
    r.json.return_value = {"choices": [{"message": {"content": content}}]}
    return r


@pytest.fixture(autouse=True)
def no_sleep_and_fresh_breakers(monkeypatch):
    from app.llm import failover

    monkeypatch.setattr("app.llm_client.time.sleep", lambda s: None)
    monkeypatch.delenv("NL2SQL_LLM_FALLBACK_MODELS", raising=False)
    get_settings.cache_clear()
    failover.reset_circuits()
    yield
    failover.reset_circuits()


# --- typed errors -------------------------------------------------------------------------------

@pytest.mark.parametrize("status", [429, 500, 503])
def test_retryable_statuses_raise_transient_after_retries(status):
    from app.llm_client import LLMTransientError, NVIDIAClient

    with patch("app.llm_client.requests.post", return_value=_resp(status)) as post:
        with pytest.raises(LLMTransientError) as exc:
            NVIDIAClient(model="m/one").generate_sql("p", api_key="k")
    assert exc.value.status == status and post.call_count == 4
    assert str(status) in str(exc.value)  # message kept for the llm_api_error classification


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_client_errors_are_typed_and_not_retried(status):
    from app.llm_client import LLMClientError, NVIDIAClient

    with patch("app.llm_client.requests.post", return_value=_resp(status)) as post:
        with pytest.raises(LLMClientError) as exc:
            NVIDIAClient(model="m/one").generate_sql("p", api_key="k")
    assert exc.value.status == status and post.call_count == 1


def test_network_errors_become_transient():
    from app.llm_client import LLMTransientError, NVIDIAClient

    with patch("app.llm_client.requests.post", side_effect=requests.ConnectionError("down")):
        with pytest.raises(LLMTransientError):
            NVIDIAClient(model="m/one").generate_sql("p", api_key="k")


def test_llm_errors_are_still_exceptions():
    from app.llm_client import LLMClientError, LLMError, LLMTransientError

    assert issubclass(LLMTransientError, LLMError) and issubclass(LLMClientError, LLMError)
    assert issubclass(LLMError, Exception)


def test_explicit_model_overrides_config():
    from app.llm_client import NVIDIAClient

    assert NVIDIAClient(model="org/explicit").model == "org/explicit"


# --- chain --------------------------------------------------------------------------------------

def test_chain_is_primary_then_deduplicated_fallbacks(monkeypatch):
    from app.llm.failover import model_chain

    monkeypatch.setenv("NL2SQL_LLM_FALLBACK_MODELS", " meta/b , meta/c,meta/b,, ")
    get_settings.cache_clear()
    with patch("app.llm.failover._primary_model", return_value="meta/a"):
        assert model_chain() == ["meta/a", "meta/b", "meta/c"]
    with patch("app.llm.failover._primary_model", return_value="meta/b"):
        assert model_chain() == ["meta/b", "meta/c"]


def _client(models, responses):
    """FailoverLLMClient whose per-model clients return/raise from `responses[model]` (a list)."""
    from app.llm.failover import FailoverLLMClient

    calls = []

    def factory(model):
        c = MagicMock()

        def gen(prompt, api_key=None):
            calls.append(model)
            outcome = responses[model].pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        c.generate_sql.side_effect = gen
        c.model = model
        return c

    return FailoverLLMClient(models=models, client_factory=factory), calls


def test_primary_success_uses_no_fallback():
    client, calls = _client(["a", "b"], {"a": ["SELECT 1"], "b": []})
    assert client.generate_sql("p") == "SELECT 1"
    assert calls == ["a"] and client.last_model == "a"


def test_transient_error_fails_over_to_next_model():
    from app.llm_client import LLMTransientError

    client, calls = _client(["a", "b"], {"a": [LLMTransientError(503, "x")], "b": ["SELECT 2"]})
    assert client.generate_sql("p") == "SELECT 2"
    assert calls == ["a", "b"] and client.last_model == "b"


def test_model_unavailable_fails_over():
    from app.llm_client import LLMClientError

    client, calls = _client(["a", "b"], {"a": [LLMClientError(404, "no such model")], "b": ["SELECT 3"]})
    assert client.generate_sql("p") == "SELECT 3"


@pytest.mark.parametrize("status", [401, 403])
def test_auth_errors_do_not_fail_over(status):
    from app.llm_client import LLMClientError

    client, calls = _client(["a", "b"], {"a": [LLMClientError(status, "bad key")], "b": ["SELECT 9"]})
    with pytest.raises(LLMClientError):
        client.generate_sql("p")
    assert calls == ["a"]


def test_non_llm_errors_propagate_without_failover():
    client, calls = _client(["a", "b"], {"a": [ValueError("NVIDIA API Key bulunamadı")], "b": ["SELECT 9"]})
    with pytest.raises(ValueError):
        client.generate_sql("p")
    assert calls == ["a"]


def test_whole_chain_down_raises_last_error():
    from app.llm_client import LLMTransientError

    client, calls = _client(["a", "b"], {"a": [LLMTransientError(503, "a")], "b": [LLMTransientError(502, "b")]})
    with pytest.raises(LLMTransientError) as exc:
        client.generate_sql("p")
    assert exc.value.status == 502 and calls == ["a", "b"]


# --- circuit breaker -------------------------------------------------------------------------------

def test_breaker_opens_half_opens_and_closes():
    from app.llm.failover import CircuitBreaker

    b = CircuitBreaker(failure_threshold=2, reset_seconds=60)
    assert b.state(0) == "closed" and b.available(0)
    b.record_failure(0)
    assert b.state(1) == "closed"
    b.record_failure(1)
    assert b.state(2) == "open" and not b.available(2)
    assert b.retry_in(2) == pytest.approx(59)
    assert b.state(61) == "half_open" and b.available(61)
    b.record_failure(61)  # trial failed -> open again
    assert b.state(62) == "open"
    b.record_success()
    assert b.state(62) == "closed" and b.consecutive_failures == 0


def test_open_circuit_skips_model(monkeypatch):
    from app.llm import failover
    from app.llm_client import LLMTransientError

    monkeypatch.setenv("NL2SQL_LLM_CIRCUIT_FAILURES", "2")
    get_settings.cache_clear()
    responses = {"a": [LLMTransientError(503, "x"), LLMTransientError(503, "x")], "b": ["S1", "S2", "S3"]}
    client, calls = _client(["a", "b"], responses)
    client.generate_sql("p")
    client.generate_sql("p")  # second failure of "a" opens its circuit
    calls.clear()
    assert client.generate_sql("p") == "S3"
    assert calls == ["b"]  # "a" skipped entirely
    assert failover.circuit_snapshot(["a", "b"])[0]["state"] == "open"


def test_all_circuits_open_still_tries_the_soonest(monkeypatch):
    from app.llm import failover
    from app.llm_client import LLMTransientError

    monkeypatch.setenv("NL2SQL_LLM_CIRCUIT_FAILURES", "1")
    get_settings.cache_clear()
    client, calls = _client(["a", "b"], {"a": [LLMTransientError(503, "x"), "RECOVERED"],
                                          "b": [LLMTransientError(503, "y")]})
    with pytest.raises(LLMTransientError):
        client.generate_sql("p")
    assert failover.all_circuits_open(["a", "b"])
    calls.clear()
    assert client.generate_sql("p") == "RECOVERED"  # never locks up completely
    assert calls == ["a"]


# --- wiring -----------------------------------------------------------------------------------------

def test_pipeline_default_client_is_failover():
    from app.llm.failover import FailoverLLMClient
    from app.sql_pipeline import SQLGenerationPipeline

    pipeline = SQLGenerationPipeline(schema_manager=MagicMock())
    assert isinstance(pipeline._get_nvidia_client(), FailoverLLMClient)
    injected = MagicMock()
    assert SQLGenerationPipeline(schema_manager=MagicMock(), nvidia_client=injected)._get_nvidia_client() is injected


def test_admin_llm_endpoint(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setenv("NL2SQL_LLM_FALLBACK_MODELS", "meta/fallback-1")
    get_settings.cache_clear()
    r = TestClient(app).get("/api/v1/admin/llm", headers={"X-API-Key": DEV_DEFAULT_API_KEY})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["chain"][-1]["model"] == "meta/fallback-1"
    assert all(m["state"] == "closed" for m in data["chain"])
    assert data["failure_threshold"] == 3 and data["reset_seconds"] == 60
    assert TestClient(app).get("/api/v1/admin/llm").status_code == 403


def test_ready_reports_open_circuits_as_degraded(monkeypatch):
    from app.health import build_component_checks
    from app.llm import failover

    monkeypatch.setenv("NL2SQL_LLM_CIRCUIT_FAILURES", "1")
    get_settings.cache_clear()
    with patch("app.llm.failover.model_chain", return_value=["a"]), \
         patch("app.health.resolve_secret", return_value="k"):
        assert build_component_checks([], True)["llm"].status == "ok"
        failover.get_breaker("a").record_failure(failover._now())
        check = build_component_checks([], True)["llm"]
    assert (check.status, check.reason) == ("degraded", "llm_circuits_open")


def test_failover_settings_validated_and_in_contract(monkeypatch):
    from pydantic import ValidationError

    from app.config_contract import known_env_names
    from app.settings import Settings

    assert {"NL2SQL_LLM_FALLBACK_MODELS", "NL2SQL_LLM_CIRCUIT_FAILURES",
            "NL2SQL_LLM_CIRCUIT_RESET_SECONDS"} <= known_env_names()
    for name, bad in (("NL2SQL_LLM_CIRCUIT_FAILURES", "0"), ("NL2SQL_LLM_CIRCUIT_RESET_SECONDS", "0")):
        monkeypatch.setenv(name, bad)
        with pytest.raises(ValidationError):
            Settings()
        monkeypatch.delenv(name)
