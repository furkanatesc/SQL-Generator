from typing import Dict, Any
from app.eval.models import EvalCheckResult, EvalCaseResult, EvalSuiteResult

def check_result_to_dict(check: EvalCheckResult) -> Dict[str, Any]:
    return {
        "name": check.name,
        "passed": check.passed,
        "message": check.message,
        "details": check.details,
    }

def case_result_to_dict(result: EvalCaseResult) -> Dict[str, Any]:
    return {
        "case_id": result.case_id,
        "passed": result.passed,
        "generated_sql": result.generated_sql,
        "error_type": result.error_type,
        "checks": [check_result_to_dict(c) for c in result.checks]
    }

def suite_result_to_dict(result: EvalSuiteResult) -> Dict[str, Any]:
    return {
        "profile": result.profile,
        "summary": {
            "total_cases": result.total_cases,
            "passed": result.passed,
            "failed": result.failed,
            "pass_rate": result.pass_rate
        },
        "results": [case_result_to_dict(r) for r in result.results]
    }
