"""Canlı pipeline verilerinden EndToEndTrace montajı (Sprint 27.1w).

Saf ve I/O-free: legacy run_pipeline'ın ürettiği redakte edilmiş verilerden
(attempts, schema_selection_trace, prompt sha'ları) 7 sabit span kurar.

Span kuralları (spec §1.4):
  INTENT     — canlı yolda intent extraction YOK. error_type
               {excel_parse_error, input_error} -> doğrudan ERROR span
               (attributes={"reason_code": error_type}); aksi halde SKIPPED
               (build_intent_span(None)).
  RETRIEVAL  — error_type {schema_pruning_failed, schema_pruning_crashed,
               schema_context_selection_crashed} -> doğrudan ERROR span
               (bu setler registry'den türetilir; Sprint 27.2);
               retrieval hiç koşmadıysa (schema_selection_trace None ve
               pruned_tables boş) -> SKIPPED (build_retrieval_span(None));
               aksi halde duck nesneyle OK/WARNING, selected_tables
               pruned_tables'a önceliklidir.
  PROMPT     — prompt_sha256 None -> SKIPPED; aksi halde duck nesneyle OK.
  GENERATION — attempts boş -> SKIPPED; aksi halde duck nesneyle OK/ERROR
               (output_sha256 yoksa ERROR — Task 1 builder davranışı).
  VALIDATION — attempts boş -> SKIPPED (issues=None); aksi halde tüm
               attempts'lerin validation_errors'larından güvenlik-dışı
               (stage not in {sql_guardrail, sql_sandbox_safety}) olanlar
               issue listesi; valid = success or guardrail_or_safety_final
               (son attempt'in hatası güvenlikse doğrulama SQL'i reddetmedi).
  SECURITY   — attempts boş -> SKIPPED (build_security_span(())); güvenlik
               hatası varsa her biri ERROR check; yoksa tek "allowed" OK check.
  EXECUTION  — Faz-1'de canlı çalıştırma yok: HER ZAMAN doğrudan
               TraceSpan(EXECUTION, SKIPPED) (build_execution_span(None)
               KULLANILMAZ — EndToEndTraceError fırlatır).

Terminal tutarlılığı build_end_to_end_trace/derive_terminal tarafından
türetilir: ilk ERROR span'in stage'i FAILED terminal_stage'i olur; hiç
ERROR yoksa COMPLETED (son span EXECUTION). Import yüzeyi: yalnız stdlib
(hashlib, types.SimpleNamespace, typing) + app.trace.* + app.errors.*
(Sprint 27.2: app.errors yaprak katmandır, driver taşımaz).
"""
import hashlib
from types import SimpleNamespace
from typing import Mapping, Optional, Sequence

from app.trace.end_to_end_trace import (
    EndToEndTrace, TraceSpan, TraceSpanStatus, TraceStageKind,
    build_end_to_end_trace,
)
from app.trace.end_to_end_trace_builders import (
    build_generation_span, build_intent_span, build_prompt_span,
    build_retrieval_span, build_security_span, build_validation_span,
)

from app.errors import ErrorCategory, codes_for_category

# Sprint 27.2: bu setler ARTIK ELLE BAKILMAZ, registry'den türetilir.
# v1'de elle yazılmış kopyalardı ve eksiktiler: sql_generation_failed ile
# llm_api_error hiçbir sette yoktu, yani bir üretim hatası bu dallardan
# reason_code'lu ERROR span üretmiyordu.
_INPUT_ERROR_TYPES = codes_for_category(ErrorCategory.INPUT)
_RETRIEVAL_ERROR_TYPES = codes_for_category(ErrorCategory.RETRIEVAL)

# _SECURITY_STAGES bir STAGE setidir (kod değil) ve registry'ye girmez —
# kategori kodun sabit özelliği, stage çalışma zamanı verisidir.
_SECURITY_STAGES = frozenset({"sql_guardrail", "sql_sandbox_safety"})


def sha256_text(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _attempt_issues(attempts: Sequence[Mapping]) -> list:
    issues = []
    for att in attempts or ():
        issues.extend(att.get("validation_errors") or [])
    return issues


def assemble_live_end_to_end_trace(
    *, trace_id: str, request_id: str, job_id: str, dialect: str,
    natural_query_redacted: str, total_duration_ms: int,
    stage_timings: Optional[Mapping[str, int]],
    error_type: Optional[str], success: bool,
    schema_selection_trace: Optional[Mapping], pruned_tables: Sequence[str],
    prompt_sha256: Optional[str], prompt_char_count: Optional[int],
    attempts_redacted: Sequence[Mapping],
    last_generated_sql_redacted: Optional[str],
) -> EndToEndTrace:
    timings = dict(stage_timings or {})
    attempts = list(attempts_redacted or [])
    all_issues = _attempt_issues(attempts)
    security_issues = [e for e in all_issues if e.get("stage") in _SECURITY_STAGES]
    validation_issues = [e for e in all_issues if e.get("stage") not in _SECURITY_STAGES]
    final_issues = (attempts[-1].get("validation_errors") or []) if attempts else []
    guardrail_or_safety_final = any(
        e.get("stage") in _SECURITY_STAGES for e in final_issues)

    # INTENT — canlı yolda intent extraction koşmaz.
    if error_type in _INPUT_ERROR_TYPES:
        intent_span = TraceSpan(stage=TraceStageKind.INTENT,
                                status=TraceSpanStatus.ERROR,
                                duration_ms=timings.get("intent"),
                                attributes={"reason_code": error_type})
    else:
        intent_span = build_intent_span(None, duration_ms=timings.get("intent"))

    # RETRIEVAL
    if error_type in _RETRIEVAL_ERROR_TYPES:
        retrieval_span = TraceSpan(stage=TraceStageKind.RETRIEVAL,
                                   status=TraceSpanStatus.ERROR,
                                   duration_ms=timings.get("retrieval"),
                                   attributes={"reason_code": error_type})
    else:
        table_names = list((schema_selection_trace or {}).get("selected_tables")
                           or pruned_tables or [])
        if not table_names and schema_selection_trace is None:
            retrieval_span = build_retrieval_span(
                None, duration_ms=timings.get("retrieval"))
        else:
            duck = SimpleNamespace(
                k_requested=None, k_returned=len(table_names),
                retrieval_version="legacy_context_selector_v1",
                candidates=[SimpleNamespace(object_id=t, object_type="table")
                            for t in table_names])
            retrieval_span = build_retrieval_span(
                duck, duration_ms=timings.get("retrieval"))

    # PROMPT
    if prompt_sha256 is None:
        prompt_span = build_prompt_span(None)
    else:
        prompt_span = build_prompt_span(
            SimpleNamespace(prompt_sha256=prompt_sha256,
                            prompt_char_count=prompt_char_count,
                            intent_type=None, target_dialect=dialect,
                            source_section_types=(), source_item_ids=(),
                            input_version="legacy_prompt_template_manager"),
            duration_ms=timings.get("prompt"))

    # GENERATION
    if not attempts:
        generation_span = build_generation_span(None)
    else:
        generation_span = build_generation_span(
            SimpleNamespace(
                response=SimpleNamespace(provider_id="legacy_pipeline",
                                         model_id=None, finish_reason=None,
                                         latency_ms=None, token_usage=None),
                output_sha256=sha256_text(last_generated_sql_redacted),
                prompt_sha256=prompt_sha256),
            duration_ms=timings.get("generation"))

    # VALIDATION
    if not attempts:
        validation_span = build_validation_span(None, valid=False)
    else:
        validation_span = build_validation_span(
            [SimpleNamespace(**e) for e in validation_issues],
            valid=bool(success or guardrail_or_safety_final),
            sql_sha256=sha256_text(last_generated_sql_redacted),
            duration_ms=timings.get("validation"))

    # SECURITY
    if not attempts:
        security_span = build_security_span((), duration_ms=timings.get("security"))
    elif security_issues:
        security_span = build_security_span([
            SimpleNamespace(category=e.get("stage"), outcome="denied",
                            severity="error", reason_code=e.get("type"),
                            entry_hash=None)
            for e in security_issues], duration_ms=timings.get("security"))
    else:
        security_span = build_security_span([
            SimpleNamespace(category="sql_guardrail", outcome="allowed",
                            severity="info", reason_code=None, entry_hash=None)],
            duration_ms=timings.get("security"))

    # EXECUTION — Faz-1'de canlı çalıştırma yok (spec §1.4).
    execution_span = TraceSpan(stage=TraceStageKind.EXECUTION,
                               status=TraceSpanStatus.SKIPPED)

    return build_end_to_end_trace(
        trace_id=trace_id, request_id=request_id,
        spans=(intent_span, retrieval_span, prompt_span, generation_span,
               validation_span, security_span, execution_span),
        job_id=job_id, dialect=dialect,
        nl_query_sha256=sha256_text(natural_query_redacted),
        total_duration_ms=total_duration_ms)
