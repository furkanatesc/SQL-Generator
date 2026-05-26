from copy import deepcopy
from typing import Any


DEFAULT_RELEASE_GATE_POLICY: dict[str, Any] = {
    "min_pass_rate": 1.0,
    "max_failed": 0,
    "require_non_empty": True,
}


def evaluate_release_gate(
    report: dict[str, Any],
    *,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    effective_policy = deepcopy(DEFAULT_RELEASE_GATE_POLICY)
    if policy:
        effective_policy.update(policy)

    total = report["total"]
    passed = report["passed"]
    failed = report["failed"]
    pass_rate = report["pass_rate"]

    reason = None

    if effective_policy["require_non_empty"] and total == 0:
        reason = "No eval cases were run"
    elif pass_rate < effective_policy["min_pass_rate"]:
        reason = "Pass rate below threshold"
    elif failed > effective_policy["max_failed"]:
        reason = "Failed case count above threshold"

    gate_passed = reason is None

    return {
        "gate_passed": gate_passed,
        "reason": reason,
        "policy": {
            "min_pass_rate": effective_policy["min_pass_rate"],
            "max_failed": effective_policy["max_failed"],
            "require_non_empty": effective_policy["require_non_empty"],
        },
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": pass_rate,
        },
        "failed_cases": report["failed_cases"],
    }
