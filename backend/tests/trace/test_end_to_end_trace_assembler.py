# backend/tests/trace/test_end_to_end_trace_assembler.py
from app.trace.end_to_end_trace import (
    TraceStageKind, TraceSpanStatus, TraceTerminalStatus,
    ExecutionSpanDetail, TraceSpan, EndToEndTrace,
    derive_terminal, build_end_to_end_trace,
)


def _span(stage, status, detail=None):
    return TraceSpan(stage=stage, status=status, detail=detail)


def _exec(execution_status, status):
    return TraceSpan(stage=TraceStageKind.EXECUTION, status=status,
                     detail=ExecutionSpanDetail(execution_status=execution_status))


def test_derive_completed_uses_last_span():
    spans = (_span(TraceStageKind.SECURITY, TraceSpanStatus.OK),
             _exec("executed", TraceSpanStatus.OK))
    assert derive_terminal(spans) == (TraceTerminalStatus.COMPLETED, TraceStageKind.EXECUTION)


def test_derive_failed_at_first_error():
    spans = (_span(TraceStageKind.VALIDATION, TraceSpanStatus.ERROR),
             _span(TraceStageKind.SECURITY, TraceSpanStatus.OK))
    assert derive_terminal(spans) == (TraceTerminalStatus.FAILED, TraceStageKind.VALIDATION)


def test_derive_blocked_at_execution():
    spans = (_span(TraceStageKind.SECURITY, TraceSpanStatus.OK),
             _exec("blocked_live_connection", TraceSpanStatus.ERROR))
    assert derive_terminal(spans) == (TraceTerminalStatus.BLOCKED, TraceStageKind.EXECUTION)


def test_derive_rejected_at_execution():
    spans = (_exec("rejected", TraceSpanStatus.ERROR),)
    assert derive_terminal(spans) == (TraceTerminalStatus.REJECTED, TraceStageKind.EXECUTION)


def test_execution_block_takes_precedence_over_earlier_error():
    # an earlier validation ERROR exists, but execution blocked is authoritative
    spans = (_span(TraceStageKind.VALIDATION, TraceSpanStatus.ERROR),
             _exec("blocked_live_connection", TraceSpanStatus.ERROR))
    assert derive_terminal(spans) == (TraceTerminalStatus.BLOCKED, TraceStageKind.EXECUTION)


def test_derive_empty_spans_completed_none_stage():
    assert derive_terminal(()) == (TraceTerminalStatus.COMPLETED, None)


def test_assembler_builds_valid_trace():
    spans = (_span(TraceStageKind.SECURITY, TraceSpanStatus.OK),
             _exec("executed", TraceSpanStatus.OK))
    t = build_end_to_end_trace(trace_id="t1", request_id="r1", spans=spans,
                               dialect="postgresql", total_duration_ms=5.0)
    assert isinstance(t, EndToEndTrace)
    assert t.terminal_status == TraceTerminalStatus.COMPLETED
    assert t.terminal_stage == TraceStageKind.EXECUTION
    assert t.dialect == "postgresql"


def test_assembler_builds_failed_trace():
    spans = (_exec("rejected", TraceSpanStatus.ERROR),)
    t = build_end_to_end_trace(trace_id="t1", request_id="r1", spans=spans)
    assert t.terminal_status == TraceTerminalStatus.REJECTED
    assert t.terminal_stage == TraceStageKind.EXECUTION
