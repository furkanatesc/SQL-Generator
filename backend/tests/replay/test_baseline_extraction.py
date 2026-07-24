"""Baseline cikarimi testleri (Sprint 27.4 T2)."""
from app.replay import extract_baseline


def _payload(spans):
    return {
        "version": "end_to_end_trace_v1",
        "trace_id": "trace_abc",
        "request_id": "req_1",
        "terminal_status": "completed",
        "terminal_stage": "execution",
        "job_id": "job-1",
        "dialect": "postgres",
        "nl_query_sha256": "deadbeef",
        "total_duration_ms": 10,
        "spans": spans,
    }


def _retrieval_span(tables, status="ok"):
    return {
        "stage": "retrieval", "status": status, "duration_ms": 1,
        "detail_kind": "RetrievalSpanDetail",
        "detail": {
            "k_requested": None, "k_returned": len(tables),
            "candidates": [
                {"object_id": t, "object_type": "table", "score": 0.0,
                 "rank": i, "schema_hash": None}
                for i, t in enumerate(tables)
            ],
            "retrieval_version": "legacy_context_selector_v1",
        },
        "attributes": {},
    }


def _validation_span(valid, categories, status="ok"):
    return {
        "stage": "validation", "status": status, "duration_ms": 1,
        "detail_kind": "ValidationSpanDetail",
        "detail": {
            "valid": valid, "sql_sha256": "abc",
            "issues": [
                {"category": c, "stage": "semantic_validation",
                 "severity": None, "reason_code": c}
                for c in categories
            ],
        },
        "attributes": {},
    }


def _security_span(checks, status="ok"):
    return {
        "stage": "security", "status": status, "duration_ms": 1,
        "detail_kind": "SecuritySpanDetail",
        "detail": {"checks": checks},
        "attributes": {},
    }


def _skipped(stage):
    return {"stage": stage, "status": "skipped", "duration_ms": None,
            "detail_kind": None, "detail": None, "attributes": {}}


def test_extracts_envelope_fields():
    baseline = extract_baseline(_payload([]))
    assert baseline is not None
    assert baseline.trace_id == "trace_abc"
    assert baseline.terminal_status == "completed"


def test_extracts_retrieval_tables_sorted_and_table_typed_only():
    span = _retrieval_span(["orders", "customers"])
    span["detail"]["candidates"].append(
        {"object_id": "orders.id", "object_type": "column", "score": 0.0,
         "rank": 9, "schema_hash": None})
    baseline = extract_baseline(_payload([span]))
    # sirali VE yalniz object_type == "table"
    assert baseline.retrieval_tables == ("customers", "orders")


def test_extracts_validation_valid_and_issue_categories():
    baseline = extract_baseline(
        _payload([_validation_span(False, ["missing_column", "syntax_error"])]))
    assert baseline.validation_valid is False
    assert baseline.validation_issue_types == ("missing_column", "syntax_error")


def test_extracts_only_denied_security_reason_codes():
    checks = [
        {"category": "sql_guardrail", "outcome": "allowed", "severity": "info",
         "reason_code": None, "audit_entry_hash": None},
        {"category": "sql_sandbox_safety", "outcome": "denied", "severity": "error",
         "reason_code": "unsafe_sandbox_rejected", "audit_entry_hash": None},
    ]
    baseline = extract_baseline(_payload([_security_span(checks)]))
    assert baseline.security_denied == ("unsafe_sandbox_rejected",)


def test_skipped_span_yields_none_for_that_dimension():
    baseline = extract_baseline(_payload([
        _skipped("retrieval"), _skipped("validation"), _skipped("security")]))
    assert baseline.retrieval_tables is None
    assert baseline.validation_valid is None
    assert baseline.validation_issue_types is None
    assert baseline.security_denied is None


def test_missing_span_yields_none_for_that_dimension():
    baseline = extract_baseline(_payload([_retrieval_span(["orders"])]))
    assert baseline.retrieval_tables == ("orders",)
    assert baseline.validation_valid is None
    assert baseline.security_denied is None


def test_empty_or_none_payload_returns_none():
    assert extract_baseline(None) is None
    assert extract_baseline({}) is None


def test_denied_check_without_reason_code_falls_back_to_category():
    checks = [{"category": "sql_guardrail", "outcome": "denied",
               "severity": "error", "reason_code": None,
               "audit_entry_hash": None}]
    baseline = extract_baseline(_payload([_security_span(checks)]))
    assert baseline.security_denied == ("sql_guardrail",)
