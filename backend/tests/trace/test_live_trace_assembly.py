from app.trace.end_to_end_trace import TraceSpanStatus, TraceStageKind, TraceTerminalStatus
from app.trace.live_trace_assembly import assemble_live_end_to_end_trace, sha256_text

BASE = dict(trace_id="e2e_t", request_id="req_r", job_id="j1", dialect="postgres",
            natural_query_redacted="soru", total_duration_ms=100, stage_timings=None,
            schema_selection_trace=None, pruned_tables=[], prompt_sha256=None,
            prompt_char_count=None, attempts_redacted=[], last_generated_sql_redacted=None)


def _span(trace, kind):
    return next(s for s in trace.spans if s.stage is kind)


def test_happy_path_seven_spans_completed():
    ok_attempt = {"attempt": 1, "action": "generate", "sql": "SELECT 1",
                  "valid": True, "error": None}
    t = assemble_live_end_to_end_trace(**{**BASE,
        "error_type": None, "success": True,
        "schema_selection_trace": {"selected_tables": ["users", "orders"]},
        "pruned_tables": ["users", "orders", "extra"],
        "prompt_sha256": "p" * 64, "prompt_char_count": 1200,
        "attempts_redacted": [ok_attempt],
        "last_generated_sql_redacted": "SELECT 1"})
    assert len(t.spans) == 7
    assert t.terminal_status is TraceTerminalStatus.COMPLETED
    assert _span(t, TraceStageKind.INTENT).status is TraceSpanStatus.SKIPPED
    assert _span(t, TraceStageKind.RETRIEVAL).status is TraceSpanStatus.OK
    assert _span(t, TraceStageKind.RETRIEVAL).detail.k_returned == 2  # selected_tables önceliklidir
    assert _span(t, TraceStageKind.PROMPT).status is TraceSpanStatus.OK
    assert _span(t, TraceStageKind.GENERATION).status is TraceSpanStatus.OK
    assert _span(t, TraceStageKind.VALIDATION).status is TraceSpanStatus.OK
    assert _span(t, TraceStageKind.SECURITY).status is TraceSpanStatus.OK
    assert _span(t, TraceStageKind.EXECUTION).status is TraceSpanStatus.SKIPPED
    assert t.nl_query_sha256 == sha256_text("soru")


def test_excel_parse_error_terminal_intent():
    t = assemble_live_end_to_end_trace(**{**BASE, "error_type": "excel_parse_error",
                                          "success": False})
    assert t.terminal_status is TraceTerminalStatus.FAILED
    assert t.terminal_stage is TraceStageKind.INTENT
    assert _span(t, TraceStageKind.RETRIEVAL).status is TraceSpanStatus.SKIPPED
    assert _span(t, TraceStageKind.GENERATION).status is TraceSpanStatus.SKIPPED


def test_retrieval_error_terminal_retrieval():
    t = assemble_live_end_to_end_trace(**{**BASE, "error_type": "schema_pruning_failed",
                                          "success": False})
    assert t.terminal_status is TraceTerminalStatus.FAILED
    assert t.terminal_stage is TraceStageKind.RETRIEVAL
    assert _span(t, TraceStageKind.INTENT).status is TraceSpanStatus.SKIPPED


def test_guardrail_block_terminal_security_not_validation():
    # unsafe_dml_keyword is a real SECURITY-category registry code (Sprint 27.2/28.3.1
    # §5.3), so this still exercises a genuine security denial, not just a
    # sql_guardrail-stage tag.
    bad = {"attempt": 1, "action": "generate", "sql": "", "valid": False,
           "error": "guardrail", "validation_errors": [
               {"type": "unsafe_dml_keyword", "stage": "sql_guardrail",
                "message": "DDL yasak"}]}
    t = assemble_live_end_to_end_trace(**{**BASE, "error_type": "sql_generation_failed",
        "success": False, "prompt_sha256": "p" * 64, "prompt_char_count": 10,
        "attempts_redacted": [bad], "last_generated_sql_redacted": "DROP TABLE x"})
    assert _span(t, TraceStageKind.SECURITY).status is TraceSpanStatus.ERROR
    assert _span(t, TraceStageKind.VALIDATION).status is not TraceSpanStatus.ERROR
    assert t.terminal_status is TraceTerminalStatus.FAILED
    assert t.terminal_stage is TraceStageKind.SECURITY
    sec = _span(t, TraceStageKind.SECURITY)
    assert sec.detail.checks[0].reason_code == "unsafe_dml_keyword"
    assert sec.detail.checks[0].outcome == "denied"


def test_semantic_failure_terminal_validation():
    bad = {"attempt": 1, "action": "generate", "sql": "SELECT x", "valid": False,
           "error": "sem", "validation_errors": [
               {"type": "missing_column", "stage": "semantic_validation",
                "message": "kolon yok"}]}
    t = assemble_live_end_to_end_trace(**{**BASE, "error_type": "sql_generation_failed",
        "success": False, "prompt_sha256": "p" * 64, "prompt_char_count": 10,
        "attempts_redacted": [bad], "last_generated_sql_redacted": "SELECT x"})
    assert t.terminal_stage is TraceStageKind.VALIDATION
    assert _span(t, TraceStageKind.SECURITY).status is TraceSpanStatus.OK
    assert _span(t, TraceStageKind.GENERATION).status is TraceSpanStatus.OK


def test_llm_error_no_output_terminal_generation():
    bad = {"attempt": 1, "action": "generate", "sql": "", "valid": False,
           "error": "LLM API", "validation_errors": [
               {"type": "llm_api_error", "stage": "llm_generation", "message": "boom"}]}
    t = assemble_live_end_to_end_trace(**{**BASE, "error_type": "sql_generation_failed",
        "success": False, "prompt_sha256": "p" * 64, "prompt_char_count": 10,
        "attempts_redacted": [bad], "last_generated_sql_redacted": None})
    assert t.terminal_stage is TraceStageKind.GENERATION


def test_stage_timings_land_on_spans():
    ok_attempt = {"attempt": 1, "action": "generate", "sql": "SELECT 1",
                  "valid": True, "error": None}
    t = assemble_live_end_to_end_trace(**{**BASE, "error_type": None, "success": True,
        "schema_selection_trace": {"selected_tables": ["u"]}, "pruned_tables": ["u"],
        "prompt_sha256": "p" * 64, "prompt_char_count": 5,
        "attempts_redacted": [ok_attempt], "last_generated_sql_redacted": "SELECT 1",
        "stage_timings": {"retrieval": 30, "prompt": 5, "generation": 800,
                          "validation": 20, "security": 3}})
    assert _span(t, TraceStageKind.RETRIEVAL).duration_ms == 30
    assert _span(t, TraceStageKind.GENERATION).duration_ms == 800


def test_payload_is_json_safe():
    import json
    t = assemble_live_end_to_end_trace(**{**BASE, "error_type": "input_error",
                                          "success": False})
    json.dumps(t.to_payload())


def test_intent_error_span_carries_measured_duration():
    t = assemble_live_end_to_end_trace(**{**BASE, "error_type": "excel_parse_error",
        "success": False, "stage_timings": {"intent": 42}})
    assert _span(t, TraceStageKind.INTENT).duration_ms == 42


def test_retrieval_error_span_carries_measured_duration():
    t = assemble_live_end_to_end_trace(**{**BASE, "error_type": "schema_pruning_failed",
        "success": False, "stage_timings": {"retrieval": 17}})
    assert _span(t, TraceStageKind.RETRIEVAL).duration_ms == 17


def test_security_span_carries_measured_duration_when_ok():
    ok_attempt = {"attempt": 1, "action": "generate", "sql": "SELECT 1",
                  "valid": True, "error": None}
    t = assemble_live_end_to_end_trace(**{**BASE, "error_type": None, "success": True,
        "schema_selection_trace": {"selected_tables": ["u"]}, "pruned_tables": ["u"],
        "prompt_sha256": "p" * 64, "prompt_char_count": 5,
        "attempts_redacted": [ok_attempt], "last_generated_sql_redacted": "SELECT 1",
        "stage_timings": {"security": 7}})
    assert _span(t, TraceStageKind.SECURITY).duration_ms == 7


def test_security_span_carries_measured_duration_when_denied():
    # unsafe_dml_keyword is a real SECURITY-category registry code, so this is a
    # genuine denial (see test_guardrail_block_terminal_security_not_validation).
    bad = {"attempt": 1, "action": "generate", "sql": "", "valid": False,
           "error": "guardrail", "validation_errors": [
               {"type": "unsafe_dml_keyword", "stage": "sql_guardrail",
                "message": "DDL yasak"}]}
    t = assemble_live_end_to_end_trace(**{**BASE, "error_type": "sql_generation_failed",
        "success": False, "prompt_sha256": "p" * 64, "prompt_char_count": 10,
        "attempts_redacted": [bad], "last_generated_sql_redacted": "DROP TABLE x",
        "stage_timings": {"security": 11}})
    assert _span(t, TraceStageKind.SECURITY).duration_ms == 11


def test_security_stage_validation_error_renders_as_warning_not_denied():
    # A validation-category error (sql_parse_error) tagged at a security stage must
    # NOT render as a security denial (ERROR); it renders as flagged/WARNING.
    trace = assemble_live_end_to_end_trace(
        trace_id="t", request_id="r", job_id="j", dialect="postgres",
        natural_query_redacted="q", total_duration_ms=1, stage_timings={"security": 2},
        error_type="sql_parse_error", success=False, schema_selection_trace=None,
        pruned_tables=[], prompt_sha256=None, prompt_char_count=None,
        attempts_redacted=[{"validation_errors": [
            {"stage": "sql_guardrail", "type": "sql_parse_error"}]}],
        last_generated_sql_redacted=None,
    )
    sec = next(s for s in trace.spans if s.stage.name == "SECURITY")
    assert sec.status.name == "WARNING"          # not ERROR
    check = sec.detail.checks[0]
    assert check.outcome == "flagged"            # not "denied"
    assert check.reason_code == "sql_parse_error"


def test_security_stage_real_security_code_still_denied():
    trace = assemble_live_end_to_end_trace(
        trace_id="t", request_id="r", job_id="j", dialect="postgres",
        natural_query_redacted="q", total_duration_ms=1, stage_timings={"security": 2},
        error_type="unsafe_dml_keyword", success=False, schema_selection_trace=None,
        pruned_tables=[], prompt_sha256=None, prompt_char_count=None,
        attempts_redacted=[{"validation_errors": [
            {"stage": "sql_guardrail", "type": "unsafe_dml_keyword"}]}],
        last_generated_sql_redacted=None,
    )
    sec = next(s for s in trace.spans if s.stage.name == "SECURITY")
    assert sec.status.name == "ERROR"
    assert sec.detail.checks[0].outcome == "denied"


def test_live_trace_assembly_module_does_not_load_stage_modules_or_drivers():
    import sys
    before = set(sys.modules)
    import app.trace.live_trace_assembly  # noqa: F401
    newly_loaded = set(sys.modules) - before
    assert "app.sql_pipeline" not in newly_loaded
    for drv in ("psycopg", "psycopg2", "oracledb", "cx_Oracle"):
        assert drv not in newly_loaded
    assert not any(m.startswith("app.evaluation") for m in newly_loaded)
    assert not any(m.startswith("app.schema") for m in newly_loaded)


def test_live_trace_assembly_may_import_only_trace_and_errors_packages():
    """Sprint 27.2: import yüzeyi app.trace.* + app.errors.* ile SINIRLI.
    app.errors yaprak katmandır (kendi purity testi: tests/errors/)."""
    import sys
    prefixes = ("app.trace", "app.errors")
    saved = {m: sys.modules[m] for m in list(sys.modules) if m.startswith(prefixes)}
    for m in saved:
        del sys.modules[m]
    try:
        before = set(sys.modules)
        import app.trace.live_trace_assembly  # noqa: F401
        newly_loaded = {m for m in set(sys.modules) - before if m.startswith("app.")}
        for mod in newly_loaded:
            assert mod.startswith(prefixes), \
                f"izinsiz app modülü yüklendi: {mod}"
    finally:
        # Bu test sys.modules'u mutasyona uğrattı. Orijinal modül nesnelerini
        # birebir geri yükle ki sonraki testler sınıf-kimliğini (ör.
        # app.trace.models.TraceSerializationError) korusun; aksi halde reimport
        # yeni sınıf nesneleri üretir ve başka bir test dosyasındaki
        # pytest.raises(EskiSınıf) yeni exception'ı yakalayamaz.
        for m in [m for m in list(sys.modules) if m.startswith(prefixes)]:
            del sys.modules[m]
        sys.modules.update(saved)
