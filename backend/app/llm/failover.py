"""LLM model failover with per-model circuit breakers (Sprint 32.10).

The chain is the configured primary model followed by `NL2SQL_LLM_FALLBACK_MODELS`
(comma-separated NIM model ids on the same endpoint and key). A call moves to the next model on
a transient error (429/5xx/network, after the client's own retries) or when the model is
unavailable (400/404); it never fails over on 401/403 (the key is the problem for every model)
or on non-LLM errors. A model with `NL2SQL_LLM_CIRCUIT_FAILURES` consecutive failures is skipped
for `NL2SQL_LLM_CIRCUIT_RESET_SECONDS`, then gets one trial call (half-open). If every circuit
is open, the model whose circuit reopens soonest is still tried, so the chain never locks up.
Circuit state is per process.
"""
import logging
import threading
import time
from typing import Callable, Dict, List, Optional

from app.llm_client import LLMClientError, LLMError, LLMTransientError, NVIDIAClient, configured_llm_model

logger = logging.getLogger(__name__)

NO_FAILOVER_STATUSES = frozenset({401, 403})


def _now() -> float:
    return time.monotonic()


class CircuitBreaker:
    def __init__(self, failure_threshold: int, reset_seconds: float):
        self.failure_threshold = failure_threshold
        self.reset_seconds = reset_seconds
        self.consecutive_failures = 0
        self.opened_at: Optional[float] = None
        self._lock = threading.Lock()

    def state(self, now: float) -> str:
        with self._lock:
            return self._state(now)

    def _state(self, now: float) -> str:
        if self.opened_at is None:
            return "closed"
        return "half_open" if now >= self.opened_at + self.reset_seconds else "open"

    def available(self, now: float) -> bool:
        return self.state(now) != "open"

    def retry_in(self, now: float) -> float:
        with self._lock:
            if self.opened_at is None:
                return 0.0
            return max(0.0, self.opened_at + self.reset_seconds - now)

    def record_success(self) -> None:
        with self._lock:
            self.consecutive_failures = 0
            self.opened_at = None

    def record_failure(self, now: float) -> None:
        with self._lock:
            self.consecutive_failures += 1
            if self.opened_at is not None or self.consecutive_failures >= self.failure_threshold:
                self.opened_at = now  # (re)open; a failed half-open trial restarts the timer

    def configure(self, failure_threshold: int, reset_seconds: float) -> None:
        with self._lock:
            self.failure_threshold = failure_threshold
            self.reset_seconds = reset_seconds


_lock = threading.Lock()
_breakers: Dict[str, CircuitBreaker] = {}


def reset_circuits() -> None:
    with _lock:
        _breakers.clear()


def get_breaker(model: str) -> CircuitBreaker:
    from app.settings import get_settings

    settings = get_settings()
    with _lock:
        breaker = _breakers.get(model)
        if breaker is None:
            breaker = _breakers[model] = CircuitBreaker(settings.llm_circuit_failures,
                                                        settings.llm_circuit_reset_seconds)
        else:
            breaker.configure(settings.llm_circuit_failures, settings.llm_circuit_reset_seconds)
        return breaker


def _primary_model() -> str:
    return configured_llm_model()


def model_chain() -> List[str]:
    from app.settings import get_settings

    chain: List[str] = []
    candidates = [_primary_model()] + get_settings().llm_fallback_models.split(",")
    for model in (m.strip() for m in candidates):
        if model and model not in chain:
            chain.append(model)
    return chain


def circuit_snapshot(models: Optional[List[str]] = None) -> List[dict]:
    now = _now()
    out = []
    for model in models if models is not None else model_chain():
        b = get_breaker(model)
        out.append({
            "model": model,
            "state": b.state(now),
            "consecutive_failures": b.consecutive_failures,
            "retry_in_seconds": round(b.retry_in(now), 1),
        })
    return out


def all_circuits_open(models: Optional[List[str]] = None) -> bool:
    now = _now()
    chain = models if models is not None else model_chain()
    return bool(chain) and all(get_breaker(m).state(now) == "open" for m in chain)


class FailoverLLMClient:
    """Drop-in for `NVIDIAClient.generate_sql(prompt, api_key)` used by the pipeline."""

    def __init__(self, models: Optional[List[str]] = None,
                 client_factory: Callable[[str], NVIDIAClient] = lambda model: NVIDIAClient(model=model)):
        self._models = models
        self._factory = client_factory
        self.last_model: Optional[str] = None

    @property
    def models(self) -> List[str]:
        return self._models if self._models is not None else model_chain()

    @property
    def model(self) -> str:
        """The model of the last successful call (NVIDIAProvider reports it), else the primary."""
        return self.last_model or self.models[0]

    def generate_sql(self, prompt: str, api_key: Optional[str] = None) -> str:
        chain = self.models
        now = _now()
        candidates = [m for m in chain if get_breaker(m).available(now)]
        if not candidates:
            candidates = [min(chain, key=lambda m: get_breaker(m).retry_in(now))]
            logger.warning("all LLM circuits are open; trying %s", candidates[0])

        last_error: Optional[LLMError] = None
        for model in candidates:
            breaker = get_breaker(model)
            try:
                sql = self._factory(model).generate_sql(prompt, api_key=api_key)
            except LLMClientError as exc:
                if exc.status in NO_FAILOVER_STATUSES:
                    raise
                breaker.record_failure(_now())
                logger.warning("LLM model %s unavailable (HTTP %s); failing over", model, exc.status)
                last_error = exc
                continue
            except LLMTransientError as exc:
                breaker.record_failure(_now())
                logger.warning("LLM model %s failed transiently (%s); failing over", model, exc.status or "network")
                last_error = exc
                continue
            breaker.record_success()
            self.last_model = model
            if model != chain[0]:
                logger.warning("LLM call served by fallback model %s (primary %s)", model, chain[0])
            return sql
        assert last_error is not None
        raise last_error
