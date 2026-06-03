from app.eval.models import EvalCheckResult, GoldenCase
from app.trace.models import NL2SQLTrace
from app.eval.sql_columns import extract_sql_columns

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

def check_required_sql_features(trace: NL2SQLTrace, case: GoldenCase) -> EvalCheckResult:
    from app.eval.sql_features import extract_sql_features
    detected = extract_sql_features(trace.generated_sql or "")
    required = set(case.required_sql_features)
    missing = sorted(list(required - detected))
    
    return EvalCheckResult(
        name="required_sql_features",
        passed=not missing,
        message="" if not missing else f"Missing required SQL features: {missing}",
        details={"required": sorted(list(required)), "detected": sorted(list(detected)), "missing": missing},
    )

def check_forbidden_sql_features(trace: NL2SQLTrace, case: GoldenCase) -> EvalCheckResult:
    from app.eval.sql_features import extract_sql_features
    detected = extract_sql_features(trace.generated_sql or "")
    forbidden = set(case.forbidden_sql_features)
    present = sorted(list(forbidden.intersection(detected)))
    
    return EvalCheckResult(
        name="forbidden_sql_features",
        passed=not present,
        message="" if not present else f"Found forbidden SQL features: {present}",
        details={"forbidden": sorted(list(forbidden)), "detected": sorted(list(detected)), "present": present},
    )


def check_expected_sql_equivalence(trace: NL2SQLTrace, case: GoldenCase) -> EvalCheckResult:
    if not case.expected_sql:
        return EvalCheckResult(
            name="expected_sql_equivalence",
            passed=True,
            message="",
            details={"expected_sql": None, "generated_sql": trace.generated_sql},
        )

    generated_sql = trace.generated_sql or ""
    
    from evals.sql_normalizer import sql_equivalent
    passed = sql_equivalent(generated_sql, case.expected_sql)

    return EvalCheckResult(
        name="expected_sql_equivalence",
        passed=passed,
        message="" if passed else "Generated SQL is not equivalent to expected_sql",
        details={
            "expected_sql": case.expected_sql,
            "generated_sql": generated_sql,
        },
    )


def check_expected_columns(trace: NL2SQLTrace, case: GoldenCase) -> EvalCheckResult:
    if not case.expected_columns:
        return EvalCheckResult(
            name="expected_columns",
            passed=True,
            message="",
            details={"expected_columns": [], "extracted_columns": []},
        )

    generated_sql = trace.generated_sql or ""
    dialect = getattr(case, "dialect", None) or case.metadata.get("dialect", "postgres")
    extracted = extract_sql_columns(generated_sql, dialect=dialect)
    expected = {col.upper() for col in case.expected_columns}

    missing = []
    for exp_col in expected:
        if exp_col in extracted:
            continue

        matched = False
        if "." in exp_col:
            bare_name = exp_col.split(".")[-1]
            if bare_name in extracted:
                matched = True
        else:
            for ext_col in extracted:
                if ext_col.endswith(f".{exp_col}"):
                    matched = True
                    break

        if not matched:
            missing.append(exp_col)

    passed = not missing
    msg = ""
    if missing:
        msg = f"Missing expected columns: {sorted(missing)}"
        if generated_sql and not extracted:
            msg += " (Failed to parse SQL or no columns extracted)"

    return EvalCheckResult(
        name="expected_columns",
        passed=passed,
        message=msg,
        details={
            "expected": sorted(list(expected)),
            "extracted": sorted(list(extracted)),
            "missing": sorted(missing),
        },
    )

