from typing import Any
from app.eval.models import EvalCheckResult, GoldenCase
from app.trace.models import NL2SQLTrace

def check_sql_valid(trace: NL2SQLTrace) -> EvalCheckResult:
    return EvalCheckResult(
        name="sql_valid",
        passed=trace.sql_valid is True,
        message="" if trace.sql_valid is True else "SQL was not valid",
        details={"sql_valid": trace.sql_valid, "error_type": trace.error_type},
    )

def check_expected_tables(trace: NL2SQLTrace, case: GoldenCase) -> EvalCheckResult:
    selected = {t.upper() for t in trace.selected_tables}
    expected = {t.upper() for t in case.expected_tables}
    missing = sorted(expected - selected)

    return EvalCheckResult(
        name="expected_tables",
        passed=not missing,
        message="" if not missing else f"Missing expected tables: {missing}",
        details={"expected": sorted(expected), "selected": sorted(selected), "missing": missing},
    )

def check_required_sql_fragments(trace: NL2SQLTrace, case: GoldenCase) -> EvalCheckResult:
    sql = (trace.generated_sql or "").upper()
    missing = [frag for frag in case.required_sql_fragments if frag.upper() not in sql]
    
    return EvalCheckResult(
        name="required_sql_fragments",
        passed=not missing,
        message="" if not missing else f"Missing required SQL fragments: {missing}",
        details={"required": case.required_sql_fragments, "missing": missing},
    )

def check_forbidden_sql_fragments(trace: NL2SQLTrace, case: GoldenCase) -> EvalCheckResult:
    sql = (trace.generated_sql or "").upper()
    present = [frag for frag in case.forbidden_sql_fragments if frag.upper() in sql]
    
    return EvalCheckResult(
        name="forbidden_sql_fragments",
        passed=not present,
        message="" if not present else f"Found forbidden SQL fragments: {present}",
        details={"forbidden": case.forbidden_sql_fragments, "present": present},
    )
