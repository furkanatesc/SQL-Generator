"""Pure queue policy: what counts as transient, how long to back off, what to do on failure
(Sprint 32.5). No I/O, so it is trivially testable and the single place to change semantics.
"""
from typing import Any, Literal, Mapping

TRANSIENT_ERROR_TYPES = frozenset({"llm_api_error"})
DEFAULT_BACKOFF_CAP_SECONDS = 900

FailureDecision = Literal["retry", "dead_letter", "fail"]


def _code(value: Any) -> str:
    return str(getattr(value, "value", value))


def is_transient_failure(result: Mapping[str, Any]) -> bool:
    """A failed pipeline result is transient only if it made at least one attempt and every
    attempt failed solely with upstream LLM errors (timeouts, 5xx, rate limits). Validation,
    schema or input errors are deterministic: retrying would just repeat them."""
    if result.get("success"):
        return False
    attempts = result.get("attempts") or []
    if not attempts:
        return False
    for attempt in attempts:
        types = {_code(err.get("type")) for err in attempt.get("validation_errors") or []}
        if not types or not types <= TRANSIENT_ERROR_TYPES:
            return False
    return True


def backoff_seconds(attempt: int, base: float, cap: float = DEFAULT_BACKOFF_CAP_SECONDS) -> float:
    """Exponential backoff after the `attempt`-th (1-based) failed attempt."""
    return min(cap, base * 2 ** max(0, attempt - 1))


def decide_failure(attempts: int, max_attempts: int, transient: bool) -> FailureDecision:
    if not transient:
        return "fail"
    return "retry" if attempts < max_attempts else "dead_letter"
