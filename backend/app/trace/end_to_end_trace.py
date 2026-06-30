"""Sprint 27.0 — End-to-End Trace Contract.

Pure, deterministic, secret-free, I/O-free contract that correlates the
SQLGen pipeline's per-stage outputs under one request_id. Hybrid model:
typed envelope + typed per-stage span detail + generic attributes escape
hatch. Clock-free: all timings are caller-supplied. Imports stdlib only,
so importing this module never loads DB drivers or app.evaluation.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional, Tuple

END_TO_END_TRACE_CONTRACT_VERSION = "end_to_end_trace_v1"


class EndToEndTraceError(Exception):
    """Raised on any contract/wiring violation in the trace contract."""


class TraceStageKind(str, Enum):
    INTENT = "intent"
    RETRIEVAL = "retrieval"
    PROMPT = "prompt"
    GENERATION = "generation"
    VALIDATION = "validation"
    SECURITY = "security"
    EXECUTION = "execution"


class TraceSpanStatus(str, Enum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    SKIPPED = "skipped"


class TraceTerminalStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    REJECTED = "rejected"


@dataclass(frozen=True)
class TraceSpanDetail:
    """Marker base for typed, secret-free per-stage span detail."""


@dataclass(frozen=True)
class ExecutionSpanDetail(TraceSpanDetail):
    execution_status: str               # "executed" | "blocked_live_connection" | "rejected"
    dialect: Optional[str] = None
    sql_sha256: Optional[str] = None    # never raw SQL
    row_count: Optional[int] = None
    truncated: Optional[bool] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None  # sanitized


@dataclass(frozen=True)
class SecurityCheck:
    category: str
    outcome: str
    severity: str
    reason_code: Optional[str] = None
    audit_entry_hash: Optional[str] = None


@dataclass(frozen=True)
class SecuritySpanDetail(TraceSpanDetail):
    checks: Tuple[SecurityCheck, ...] = ()


@dataclass(frozen=True)
class TraceSpan:
    stage: TraceStageKind
    status: TraceSpanStatus
    duration_ms: Optional[float] = None
    detail: Optional[TraceSpanDetail] = None
    attributes: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.stage, TraceStageKind):
            raise EndToEndTraceError(f"stage must be TraceStageKind, got {self.stage!r}")
        if not isinstance(self.status, TraceSpanStatus):
            raise EndToEndTraceError(f"status must be TraceSpanStatus, got {self.status!r}")
        if self.detail is not None and not isinstance(self.detail, TraceSpanDetail):
            raise EndToEndTraceError("detail must be a TraceSpanDetail or None")
        for k, v in self.attributes.items():
            if not isinstance(k, str) or not isinstance(v, str):
                raise EndToEndTraceError("attributes must be a str->str mapping (secret-free)")


@dataclass(frozen=True)
class EndToEndTrace:
    version: str
    trace_id: str
    request_id: str
    terminal_status: TraceTerminalStatus
    spans: Tuple[TraceSpan, ...]
    terminal_stage: Optional[TraceStageKind] = None
    job_id: Optional[str] = None
    dialect: Optional[str] = None
    nl_query_sha256: Optional[str] = None
    total_duration_ms: Optional[float] = None

    def __post_init__(self):
        if self.version != END_TO_END_TRACE_CONTRACT_VERSION:
            raise EndToEndTraceError(
                f"version must be {END_TO_END_TRACE_CONTRACT_VERSION!r}, got {self.version!r}")
        if not isinstance(self.trace_id, str) or not self.trace_id.strip():
            raise EndToEndTraceError("trace_id must be a non-empty string")
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise EndToEndTraceError("request_id must be a non-empty string")
        if not isinstance(self.terminal_status, TraceTerminalStatus):
            raise EndToEndTraceError("terminal_status must be a TraceTerminalStatus")
        seen = set()
        for s in self.spans:
            if not isinstance(s, TraceSpan):
                raise EndToEndTraceError("spans must contain TraceSpan instances")
            if s.stage in seen:
                raise EndToEndTraceError(f"duplicate span stage: {s.stage.value}")
            seen.add(s.stage)
        by_stage = {s.stage: s for s in self.spans}
        if self.terminal_status == TraceTerminalStatus.COMPLETED:
            if any(s.status == TraceSpanStatus.ERROR for s in self.spans):
                raise EndToEndTraceError("COMPLETED trace must have no ERROR span")
        else:  # FAILED / BLOCKED / REJECTED
            if self.terminal_stage is None:
                raise EndToEndTraceError(
                    f"{self.terminal_status.value} trace requires a terminal_stage")
            span = by_stage.get(self.terminal_stage)
            if span is None:
                raise EndToEndTraceError(
                    f"terminal_stage {self.terminal_stage.value} has no span")
            if span.status != TraceSpanStatus.ERROR:
                raise EndToEndTraceError(
                    f"terminal_stage {self.terminal_stage.value} span must be ERROR")

    def to_payload(self) -> dict:
        """JSON-safe dict for the existing TraceRecord.payload bridge."""
        def _span(s: TraceSpan) -> dict:
            return {
                "stage": s.stage.value,
                "status": s.status.value,
                "duration_ms": s.duration_ms,
                "detail_kind": type(s.detail).__name__ if s.detail is not None else None,
                "detail": dataclasses.asdict(s.detail) if s.detail is not None else None,
                "attributes": dict(s.attributes),
            }
        return {
            "version": self.version,
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "terminal_status": self.terminal_status.value,
            "terminal_stage": self.terminal_stage.value if self.terminal_stage else None,
            "job_id": self.job_id,
            "dialect": self.dialect,
            "nl_query_sha256": self.nl_query_sha256,
            "total_duration_ms": self.total_duration_ms,
            "spans": [_span(s) for s in self.spans],
        }


def derive_terminal(spans: Tuple[TraceSpan, ...]) -> Tuple[TraceTerminalStatus, Optional[TraceStageKind]]:
    """Pure rule: derive (terminal_status, terminal_stage) from ordered spans.

    Precedence (top wins):
      1. EXECUTION span with execution_status 'blocked_live_connection' -> BLOCKED
      2. EXECUTION span with execution_status 'rejected'                 -> REJECTED
      3. first span with status ERROR                                    -> FAILED
      4. no ERROR span                                                   -> COMPLETED
    """
    exec_span = next((s for s in spans if s.stage == TraceStageKind.EXECUTION), None)
    if exec_span is not None and isinstance(exec_span.detail, ExecutionSpanDetail):
        if exec_span.detail.execution_status == "blocked_live_connection":
            return (TraceTerminalStatus.BLOCKED, TraceStageKind.EXECUTION)
        if exec_span.detail.execution_status == "rejected":
            return (TraceTerminalStatus.REJECTED, TraceStageKind.EXECUTION)
    for s in spans:
        if s.status == TraceSpanStatus.ERROR:
            return (TraceTerminalStatus.FAILED, s.stage)
    if spans:
        return (TraceTerminalStatus.COMPLETED, spans[-1].stage)
    return (TraceTerminalStatus.COMPLETED, None)


def build_end_to_end_trace(
    *,
    trace_id: str,
    request_id: str,
    spans: Tuple[TraceSpan, ...],
    job_id: Optional[str] = None,
    dialect: Optional[str] = None,
    nl_query_sha256: Optional[str] = None,
    total_duration_ms: Optional[float] = None,
) -> EndToEndTrace:
    """Compose spans into a validated EndToEndTrace, deriving terminal state."""
    spans = tuple(spans)
    terminal_status, terminal_stage = derive_terminal(spans)
    return EndToEndTrace(
        version=END_TO_END_TRACE_CONTRACT_VERSION,
        trace_id=trace_id, request_id=request_id,
        terminal_status=terminal_status, spans=spans,
        terminal_stage=terminal_stage, job_id=job_id, dialect=dialect,
        nl_query_sha256=nl_query_sha256, total_duration_ms=total_duration_ms)
