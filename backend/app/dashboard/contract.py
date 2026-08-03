"""Admin dashboard sozlesmesi — frozen record'lar (Sprint 27.7).

to_payload() JSON-safe ve DETERMINISTIKTIR: tuple'lar listeye, sozluk anahtarlari
SIRALI serilenir. Duvar-saati YOKTUR.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Tuple

DASHBOARD_CONTRACT_VERSION = "dashboard_v1"


def _sorted_int_map(d: Mapping[str, int]) -> dict:
    return {k: d[k] for k in sorted(d)}


@dataclass(frozen=True)
class DashboardWindow:
    created_after: Optional[str]
    created_before: Optional[str]
    dialect: Optional[str]
    trace_count: int
    truncated: bool
    scan_cap: int
    bucket: str
    timeseries_truncated: bool = False
    feedback_truncated: bool = False

    def to_payload(self) -> dict:
        return {
            "created_after": self.created_after,
            "created_before": self.created_before,
            "dialect": self.dialect,
            "trace_count": self.trace_count,
            "truncated": self.truncated,
            "scan_cap": self.scan_cap,
            "bucket": self.bucket,
            "timeseries_truncated": self.timeseries_truncated,
            "feedback_truncated": self.feedback_truncated,
        }


@dataclass(frozen=True)
class TimeseriesBucket:
    bucket_start: str
    total: int
    success_rate: Optional[float]
    error_count: int
    p95_ms: Optional[float]

    def to_payload(self) -> dict:
        return {
            "bucket_start": self.bucket_start,
            "total": self.total,
            "success_rate": self.success_rate,
            "error_count": self.error_count,
            "p95_ms": self.p95_ms,
        }


@dataclass(frozen=True)
class TopError:
    code: str
    category: str
    count: int

    def to_payload(self) -> dict:
        return {"code": self.code, "category": self.category, "count": self.count}


@dataclass(frozen=True)
class FeedbackSummary:
    total: int
    by_verdict: Mapping[str, int]
    by_category: Mapping[str, int]

    def to_payload(self) -> dict:
        return {
            "total": self.total,
            "by_verdict": _sorted_int_map(self.by_verdict),
            "by_category": _sorted_int_map(self.by_category),
        }


@dataclass(frozen=True)
class RecentTrace:
    job_id: Optional[str]
    trace_id: Optional[str]
    terminal_status: Optional[str]
    dialect: Optional[str]
    total_duration_ms: Optional[float]
    created_at: Optional[str]

    def to_payload(self) -> dict:
        return {
            "job_id": self.job_id,
            "trace_id": self.trace_id,
            "terminal_status": self.terminal_status,
            "dialect": self.dialect,
            "total_duration_ms": self.total_duration_ms,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class DashboardReport:
    version: str
    window: DashboardWindow
    metrics: Mapping[str, Any]
    timeseries: Tuple[TimeseriesBucket, ...]
    top_errors: Tuple[TopError, ...]
    feedback: FeedbackSummary
    recent_activity: Tuple[RecentTrace, ...]

    def to_payload(self) -> dict:
        return {
            "version": self.version,
            "window": self.window.to_payload(),
            "metrics": dict(self.metrics),
            "timeseries": [b.to_payload() for b in self.timeseries],
            "top_errors": [e.to_payload() for e in self.top_errors],
            "feedback": self.feedback.to_payload(),
            "recent_activity": [r.to_payload() for r in self.recent_activity],
        }
