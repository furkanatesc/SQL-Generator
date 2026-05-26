from typing import Any, Callable


def _extract_actual(result: dict) -> dict:
    attempts = result.get("attempts", [])
    final_attempt = attempts[-1] if attempts else {}
    errors = final_attempt.get("validation_errors", [])
    err = errors[0] if errors else {}

    return {
        "success": result.get("success"),
        "generated_sql": result.get("generated_sql", ""),
        "error_type": err.get("type"),
        "stage": err.get("stage"),
    }


def _evaluate_case(case: dict, result: dict) -> tuple[bool, str | None, dict]:
    expected = case["expected"]
    actual = _extract_actual(result)

    if expected["type"] == "success":
        if actual["success"] is not True:
            return False, "Expected success but pipeline failed", actual

        sql = (actual["generated_sql"] or "").upper()
        for fragment in expected.get("sql_contains", []):
            if fragment.upper() not in sql:
                return False, f"Missing SQL fragment: {fragment}", actual

        return True, None, actual

    if actual["success"] is not False:
        return False, "Expected failure but pipeline succeeded", actual

    if actual["error_type"] != expected.get("error_type"):
        return False, f"Expected error_type={expected.get('error_type')} got {actual['error_type']}", actual

    if actual["stage"] != expected.get("stage"):
        return False, f"Expected stage={expected.get('stage')} got {actual['stage']}", actual

    if expected["type"] == "guardrail_failure":
        expected_public_sql = expected.get("public_generated_sql")
        if actual["generated_sql"] != expected_public_sql:
            return False, "Guardrail public generated_sql policy mismatch", actual

    return True, None, actual


def run_eval_cases(cases: list[dict], *, pipeline_factory: Callable[[dict], Any]) -> dict:
    results = []
    for case in sorted(cases, key=lambda c: c["id"]):
        pipeline = pipeline_factory(case)
        pipeline_result = pipeline.run_pipeline(
            job_id=case["id"],
            natural_query=case["natural_query"],
            dialect=case["dialect"],
            max_attempts=case.get("max_attempts", 1),
        )

        passed, reason, actual = _evaluate_case(case, pipeline_result)
        results.append({
            "id": case["id"],
            "expected_type": case["expected"]["type"],
            "passed": passed,
            "reason": reason,
            "actual": actual,
        })

    passed_count = sum(1 for r in results if r["passed"])
    return {
        "total": len(results),
        "passed": passed_count,
        "failed": len(results) - passed_count,
        "results": results,
    }
