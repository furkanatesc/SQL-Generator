# backend/tests/trace/test_end_to_end_trace_builders.py
from types import SimpleNamespace

import pytest

from app.trace.end_to_end_trace import (
    TraceStageKind, TraceSpanStatus, ExecutionSpanDetail, EndToEndTraceError,
)
from app.trace.end_to_end_trace_builders import build_execution_span


def _executed_outcome(warnings=()):
    return SimpleNamespace(
        status="executed",
        plan=SimpleNamespace(effective_dialect=SimpleNamespace(value="postgresql")),
        execution_result=SimpleNamespace(
            sql_sha256="a" * 64, row_count=2, truncated=False, execution_error=None),
        error=None, warnings=tuple(warnings))


def test_executed_maps_to_ok():
    span = build_execution_span(_executed_outcome(), duration_ms=4.0)
    assert span.stage == TraceStageKind.EXECUTION
    assert span.status == TraceSpanStatus.OK
    assert span.duration_ms == 4.0
    assert isinstance(span.detail, ExecutionSpanDetail)
    assert span.detail.execution_status == "executed"
    assert span.detail.dialect == "postgresql"
    assert span.detail.sql_sha256 == "a" * 64
    assert span.detail.row_count == 2


def test_executed_with_warnings_maps_to_warning():
    span = build_execution_span(_executed_outcome(warnings=("row cap",)))
    assert span.status == TraceSpanStatus.WARNING


def test_blocked_maps_to_error_and_sanitizes():
    outcome = SimpleNamespace(
        status="blocked_live_connection",
        plan=SimpleNamespace(effective_dialect=SimpleNamespace(value="oracle")),
        execution_result=None,
        error="live connection blocked; password=hunter2", warnings=())
    span = build_execution_span(outcome)
    assert span.status == TraceSpanStatus.ERROR
    assert span.detail.execution_status == "blocked_live_connection"
    assert span.detail.dialect == "oracle"
    assert "hunter2" not in (span.detail.error_message or "")


def test_rejected_maps_to_error():
    outcome = SimpleNamespace(
        status="rejected", plan=None, execution_result=None,
        error="rejected by orchestrator", warnings=())
    span = build_execution_span(outcome)
    assert span.status == TraceSpanStatus.ERROR
    assert span.detail.execution_status == "rejected"
    assert span.detail.dialect is None


def test_unknown_status_raises():
    outcome = SimpleNamespace(status="weird", plan=None, execution_result=None,
                              error=None, warnings=())
    with pytest.raises(EndToEndTraceError):
        build_execution_span(outcome)


def test_no_raw_sql_carried():
    # the builder only ever reads sql_sha256, never a raw sql attribute
    outcome = _executed_outcome()
    span = build_execution_span(outcome)
    assert not hasattr(span.detail, "sql")


# --- security span tests ---
from app.trace.end_to_end_trace import SecuritySpanDetail  # noqa: E402
from app.trace.end_to_end_trace_builders import build_security_span  # noqa: E402


def _evt(outcome, *, category="read_only", severity="info",
         reason_code="read_only_select", entry_hash="b" * 64):
    return SimpleNamespace(
        category=SimpleNamespace(value=category),
        outcome=SimpleNamespace(value=outcome),
        severity=SimpleNamespace(value=severity),
        reason_code=reason_code, entry_hash=entry_hash)


def test_security_empty_is_skipped():
    span = build_security_span(())
    assert span.stage == TraceStageKind.SECURITY
    assert span.status == TraceSpanStatus.SKIPPED
    assert isinstance(span.detail, SecuritySpanDetail)
    assert span.detail.checks == ()


def test_security_all_allowed_is_ok():
    span = build_security_span((_evt("allowed"), _evt("allowed")))
    assert span.status == TraceSpanStatus.OK
    assert len(span.detail.checks) == 2
    assert span.detail.checks[0].category == "read_only"
    assert span.detail.checks[0].audit_entry_hash == "b" * 64


def test_security_denied_is_error():
    span = build_security_span((_evt("allowed"), _evt("denied", category="tenant_boundary")))
    assert span.status == TraceSpanStatus.ERROR


def test_security_error_outcome_is_error():
    span = build_security_span((_evt("error"),))
    assert span.status == TraceSpanStatus.ERROR


def test_security_flagged_is_warning():
    span = build_security_span((_evt("flagged", category="query_risk"),))
    assert span.status == TraceSpanStatus.WARNING


def test_security_requires_approval_is_warning():
    span = build_security_span((_evt("requires_approval", category="approval"),))
    assert span.status == TraceSpanStatus.WARNING


def test_security_none_is_skipped():
    span = build_security_span(None)
    assert span.stage == TraceStageKind.SECURITY
    assert span.status == TraceSpanStatus.SKIPPED
    assert span.detail.checks == ()


# --- intent span tests ---
from app.trace.end_to_end_trace import IntentSpanDetail  # noqa: E402
from app.trace.end_to_end_trace_builders import build_intent_span  # noqa: E402


def _intent(intent_type="list", ambiguity=False, **flags):
    base = dict(has_filter=False, has_aggregation=False, has_grouping=False,
                has_ordering=False, has_limit=False, requires_join=False,
                has_time_range=False)
    base.update(flags)
    return SimpleNamespace(
        extraction_version="intent_extraction_v1",
        intent=SimpleNamespace(
            normalized_query="show me users named alice",  # secret-ish; must NOT surface
            intent_type=intent_type, ambiguity_detected=ambiguity,
            signals=(SimpleNamespace(name="has_filter", value=True,
                                     reason="found WHERE-like phrase alice"),),
            **base))


def test_intent_ok_and_flags():
    span = build_intent_span(_intent(has_filter=True, requires_join=True), duration_ms=2.0)
    assert span.stage == TraceStageKind.INTENT
    assert span.status == TraceSpanStatus.OK
    assert span.duration_ms == 2.0
    assert isinstance(span.detail, IntentSpanDetail)
    assert span.detail.intent_type == "list"
    assert set(span.detail.flags) == {"has_filter", "requires_join"}
    assert span.detail.signal_names == ("has_filter",)
    assert span.detail.extraction_version == "intent_extraction_v1"


def test_intent_ambiguity_is_warning():
    span = build_intent_span(_intent(ambiguity=True))
    assert span.status == TraceSpanStatus.WARNING


def test_intent_unknown_type_is_warning():
    span = build_intent_span(_intent(intent_type="unknown"))
    assert span.status == TraceSpanStatus.WARNING


def test_intent_none_is_skipped():
    span = build_intent_span(None)
    assert span.stage == TraceStageKind.INTENT
    assert span.status == TraceSpanStatus.SKIPPED
    assert span.detail is None


def test_intent_carries_no_raw_query():
    span = build_intent_span(_intent(has_filter=True))
    assert not hasattr(span.detail, "normalized_query")
    # signal reason (which embedded user text) must not survive either
    assert "alice" not in repr(span.detail)


# --- retrieval span tests ---
from app.trace.end_to_end_trace import (  # noqa: E402
    RetrievalSpanDetail, RetrievalCandidateRef,
)
from app.trace.end_to_end_trace_builders import build_retrieval_span  # noqa: E402


def _cand(object_id="tbl.users", rank=1, score=0.91):
    return SimpleNamespace(
        id="c1", object_id=object_id, object_type="table",
        text="users table containing alice's PII",  # NL — must NOT surface
        score=score, rank=rank, summary_version="v1",
        schema_hash="d" * 64, provider_id="p", model_id="m", dimension=768)


def _retrieval(k_requested=5, k_returned=2, candidates=None):
    return SimpleNamespace(
        query_text="who is alice", k_requested=k_requested,
        k_returned=k_returned, retrieval_version="top_k_retrieval_v1",
        candidates=tuple(candidates if candidates is not None
                         else (_cand(), _cand("col.users.name", 2, 0.80))))


def test_retrieval_ok_and_candidate_refs():
    span = build_retrieval_span(_retrieval(), duration_ms=3.0)
    assert span.stage == TraceStageKind.RETRIEVAL
    assert span.status == TraceSpanStatus.OK
    assert isinstance(span.detail, RetrievalSpanDetail)
    assert span.detail.k_requested == 5
    assert span.detail.k_returned == 2
    assert span.detail.candidates[0] == RetrievalCandidateRef(
        object_id="tbl.users", object_type="table", score=0.91, rank=1,
        schema_hash="d" * 64)
    assert span.detail.retrieval_version == "top_k_retrieval_v1"


def test_retrieval_zero_returned_is_warning():
    span = build_retrieval_span(_retrieval(k_returned=0, candidates=()))
    assert span.status == TraceSpanStatus.WARNING


def test_retrieval_none_is_skipped():
    span = build_retrieval_span(None)
    assert span.status == TraceSpanStatus.SKIPPED
    assert span.detail is None


def test_retrieval_carries_no_candidate_text():
    span = build_retrieval_span(_retrieval())
    assert "alice" not in repr(span.detail)
    assert not hasattr(span.detail.candidates[0], "text")


# --- prompt span tests ---
from app.trace.end_to_end_trace import PromptSpanDetail  # noqa: E402
from app.trace.end_to_end_trace_builders import build_prompt_span  # noqa: E402


def _gen_input():
    return SimpleNamespace(
        raw_query="who is alice", normalized_query="who is alice",
        rendered_prompt="SYSTEM: you are ... SELECT alice",  # raw prompt — must NOT surface
        intent_type="list", target_dialect="postgresql",
        prompt_sha256="e" * 64, prompt_char_count=1234,
        source_section_types=("schema", "examples"),
        source_item_ids=("s1", "s2"), input_version="sql_generation_input_v1")


def test_prompt_ok_fields():
    span = build_prompt_span(_gen_input(), duration_ms=1.5)
    assert span.stage == TraceStageKind.PROMPT
    assert span.status == TraceSpanStatus.OK
    assert isinstance(span.detail, PromptSpanDetail)
    assert span.detail.prompt_sha256 == "e" * 64
    assert span.detail.prompt_char_count == 1234
    assert span.detail.intent_type == "list"
    assert span.detail.target_dialect == "postgresql"
    assert span.detail.source_section_types == ("schema", "examples")
    assert span.detail.source_item_ids == ("s1", "s2")
    assert span.detail.input_version == "sql_generation_input_v1"


def test_prompt_none_is_skipped():
    span = build_prompt_span(None)
    assert span.status == TraceSpanStatus.SKIPPED
    assert span.detail is None


def test_prompt_carries_no_raw_prompt():
    span = build_prompt_span(_gen_input())
    assert "SELECT" not in repr(span.detail).upper()
    assert not hasattr(span.detail, "rendered_prompt")


# --- generation span tests ---
from app.trace.end_to_end_trace import GenerationSpanDetail  # noqa: E402
from app.trace.end_to_end_trace_builders import build_generation_span  # noqa: E402


def _gen_result(finish_reason="stop", output_sha256="f" * 64, latency_ms=42):
    response = SimpleNamespace(
        version="sql_generation_provider_v1", provider_id="nvidia",
        model_id="nemotron", raw_text="SELECT 1",  # raw SQL — must NOT surface
        finish_reason=finish_reason, prompt_sha256="e" * 64,
        output_sha256=output_sha256, latency_ms=latency_ms,
        token_usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20,
                                    total_tokens=120))
    return SimpleNamespace(version="sql_generation_provider_v1", response=response,
                           generated_sql_text="SELECT 1", prompt_sha256="e" * 64,
                           output_sha256=output_sha256)


def test_generation_ok_and_tokens():
    span = build_generation_span(_gen_result())
    assert span.stage == TraceStageKind.GENERATION
    assert span.status == TraceSpanStatus.OK
    assert isinstance(span.detail, GenerationSpanDetail)
    assert span.detail.provider_id == "nvidia"
    assert span.detail.model_id == "nemotron"
    assert span.detail.finish_reason == "stop"
    assert span.detail.output_sha256 == "f" * 64
    assert span.detail.prompt_tokens == 100
    assert span.detail.total_tokens == 120
    assert span.duration_ms == 42          # fell back to response.latency_ms


def test_generation_explicit_duration_wins():
    span = build_generation_span(_gen_result(latency_ms=42), duration_ms=99.0)
    assert span.duration_ms == 99.0


def test_generation_length_finish_is_warning():
    span = build_generation_span(_gen_result(finish_reason="length"))
    assert span.status == TraceSpanStatus.WARNING


def test_generation_missing_output_is_error():
    span = build_generation_span(_gen_result(output_sha256=None))
    assert span.status == TraceSpanStatus.ERROR


def test_generation_error_finish_is_error():
    span = build_generation_span(_gen_result(finish_reason="error"))
    assert span.status == TraceSpanStatus.ERROR


def test_generation_none_is_skipped():
    span = build_generation_span(None)
    assert span.status == TraceSpanStatus.SKIPPED
    assert span.detail is None


def test_generation_carries_no_raw_sql():
    span = build_generation_span(_gen_result())
    assert "SELECT" not in repr(span.detail).upper()
    assert not hasattr(span.detail, "raw_text")


# --- validation span tests ---
from app.trace.end_to_end_trace import ValidationSpanDetail, ValidationIssue  # noqa: E402
from app.trace.end_to_end_trace_builders import build_validation_span  # noqa: E402


def _issue(type_="missing_column", stage="semantic_validation", severity="error"):
    # legacy validation_errors dict-shape carries type/stage/message; message
    # embeds column/SQL fragments and must NOT surface.
    return SimpleNamespace(type=type_, stage=stage, severity=severity,
                           message="column alice_ssn not found in users")


def test_validation_valid_no_issues_is_ok():
    span = build_validation_span((), valid=True, sql_sha256="a" * 64, duration_ms=1.0)
    assert span.stage == TraceStageKind.VALIDATION
    assert span.status == TraceSpanStatus.OK
    assert isinstance(span.detail, ValidationSpanDetail)
    assert span.detail.valid is True
    assert span.detail.sql_sha256 == "a" * 64
    assert span.detail.issues == ()


def test_validation_valid_with_issues_is_warning():
    span = build_validation_span((_issue(severity="warning"),), valid=True)
    assert span.status == TraceSpanStatus.WARNING
    assert span.detail.issues[0] == ValidationIssue(
        category="missing_column", stage="semantic_validation",
        severity="warning", reason_code="missing_column")


def test_validation_invalid_is_error():
    span = build_validation_span((_issue(),), valid=False)
    assert span.status == TraceSpanStatus.ERROR
    assert span.detail.valid is False


def test_validation_none_is_skipped():
    span = build_validation_span(None, valid=True)
    assert span.status == TraceSpanStatus.SKIPPED
    assert span.detail is None


def test_validation_carries_no_message():
    span = build_validation_span((_issue(),), valid=False)
    assert "alice_ssn" not in repr(span.detail)
    assert not hasattr(span.detail.issues[0], "message")


def test_builders_module_does_not_load_stage_modules_or_drivers():
    import sys
    before = set(sys.modules)
    import app.trace.end_to_end_trace_builders  # noqa: F401
    newly_loaded = set(sys.modules) - before
    for mod in ("app.query_understanding.intent_extractor",
                "app.retrieval.top_k_retriever",
                "app.sql_generation.sql_generation_provider_runner",
                "app.evaluation.connection_aware_execution_orchestrator"):
        assert mod not in newly_loaded, f"builder import pulled {mod}"
    for drv in ("psycopg", "psycopg2", "oracledb", "cx_Oracle"):
        assert drv not in newly_loaded


# ---- Sprint 27.1w: carried Minor fixes ----

def test_generation_span_ok_when_output_present_but_finish_reason_missing():
    result = SimpleNamespace(
        response=SimpleNamespace(provider_id="p", model_id="m", finish_reason=None,
                                 latency_ms=12, token_usage=None),
        output_sha256="abc123", prompt_sha256="def456")
    span = build_generation_span(result)
    assert span.status is TraceSpanStatus.OK


def test_generation_span_error_when_output_missing():
    result = SimpleNamespace(
        response=SimpleNamespace(provider_id="p", model_id="m", finish_reason=None,
                                 latency_ms=None, token_usage=None),
        output_sha256=None, prompt_sha256=None)
    span = build_generation_span(result)
    assert span.status is TraceSpanStatus.ERROR


def test_generation_span_error_when_finish_reason_is_error():
    result = SimpleNamespace(
        response=SimpleNamespace(provider_id="p", model_id="m", finish_reason="error",
                                 latency_ms=None, token_usage=None),
        output_sha256="abc123", prompt_sha256=None)
    span = build_generation_span(result)
    assert span.status is TraceSpanStatus.ERROR


def test_retrieval_candidate_missing_score_rank_gets_typed_fallbacks():
    result = SimpleNamespace(
        k_requested=2, k_returned=2, retrieval_version="v1",
        candidates=[SimpleNamespace(object_id="t1", object_type="table"),
                    SimpleNamespace(object_id="t2", object_type="table")])
    span = build_retrieval_span(result)
    c0, c1 = span.detail.candidates
    assert c0.score == 0.0 and isinstance(c0.score, float)
    assert c0.rank == 0 and isinstance(c0.rank, int)
    assert c1.rank == 1


def test_security_and_validation_reason_code_normalized_from_enum():
    import enum

    class _RC(enum.Enum):
        POLICY_X = "policy_x"

    event = SimpleNamespace(category="policy", outcome="denied", severity="high",
                            reason_code=_RC.POLICY_X, entry_hash=None)
    sec = build_security_span([event])
    assert sec.detail.checks[0].reason_code == "policy_x"

    issue = SimpleNamespace(category="semantic", stage="semantic_validation",
                            severity="error", reason_code=_RC.POLICY_X)
    val = build_validation_span([issue], valid=False)
    assert val.detail.issues[0].reason_code == "policy_x"
