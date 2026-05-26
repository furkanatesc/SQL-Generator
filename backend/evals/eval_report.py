from typing import Any


def build_eval_report(results: list[dict[str, Any]]) -> dict[str, Any]:
    passed_count = sum(1 for result in results if result["passed"])
    failed_count = len(results) - passed_count

    failed_cases = [
        {
            "id": result["id"],
            "expected_type": result["expected_type"],
            "reason": result["reason"],
        }
        for result in results
        if result["passed"] is False
    ]

    return {
        "total": len(results),
        "passed": passed_count,
        "failed": failed_count,
        "pass_rate": passed_count / len(results) if results else 0.0,
        "results": results,
        "failed_cases": failed_cases,
    }
