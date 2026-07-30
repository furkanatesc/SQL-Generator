"""Metrics Contract sozlesmesi — frozen record'lar (Sprint 27.6).

to_payload() JSON-safe'tir ve DETERMINISTIKTIR: tum sozluk anahtarlari SIRALI
serilenir, boylece ayni girdi her zaman ayni payload'i uretir. Duvar-saati YOKTUR.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional


def _sorted_int_map(d: Mapping[str, int]) -> dict:
    return {k: d[k] for k in sorted(d)}


@dataclass(frozen=True)
class MetricsWindow:
    created_after: Optional[str] = None
    created_before: Optional[str] = None
    dialect: Optional[str] = None
    trace_count: int = 0
    truncated: bool = False
    scan_cap: int = 0

    def to_payload(self) -> dict:
        return {
            "created_after": self.created_after,
            "created_before": self.created_before,
            "dialect": self.dialect,
            "trace_count": self.trace_count,
            "truncated": self.truncated,
            "scan_cap": self.scan_cap,
        }


@dataclass(frozen=True)
class OutcomeMetrics:
    total: int
    terminal_status: Mapping[str, int]
    success_rate: Optional[float]

    def to_payload(self) -> dict:
        return {
            "total": self.total,
            "terminal_status": _sorted_int_map(self.terminal_status),
            "success_rate": self.success_rate,
        }


@dataclass(frozen=True)
class ErrorMetrics:
    by_code: Mapping[str, int]
    by_category: Mapping[str, int]

    def to_payload(self) -> dict:
        return {
            "by_code": _sorted_int_map(self.by_code),
            "by_category": _sorted_int_map(self.by_category),
        }


@dataclass(frozen=True)
class LatencyMetrics:
    count: int
    p50: Optional[float]
    p95: Optional[float]
    p99: Optional[float]
    min: Optional[float]
    max: Optional[float]
    mean: Optional[float]

    def to_payload(self) -> dict:
        return {
            "count": self.count,
            "p50": self.p50,
            "p95": self.p95,
            "p99": self.p99,
            "min": self.min,
            "max": self.max,
            "mean": self.mean,
        }


@dataclass(frozen=True)
class MetricsReport:
    version: str
    window: MetricsWindow
    outcome: OutcomeMetrics
    errors: ErrorMetrics
    latency_ms: LatencyMetrics
    stages: Mapping[str, Mapping[str, int]]

    def to_payload(self) -> dict:
        return {
            "version": self.version,
            "window": self.window.to_payload(),
            "outcome": self.outcome.to_payload(),
            "errors": self.errors.to_payload(),
            "latency_ms": self.latency_ms.to_payload(),
            "stages": {stg: _sorted_int_map(self.stages[stg]) for stg in sorted(self.stages)},
        }


METRICS_CONTRACT_VERSION = "metrics_v1"
