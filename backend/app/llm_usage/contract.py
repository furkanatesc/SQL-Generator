"""LLM usage/cost telemetri sozlesmesi — frozen record'lar (Sprint 27.8).

to_payload() JSON-safe ve DETERMINISTIKTIR: tuple'lar listeye, sozluk anahtarlari
SIRALI serilenir. Duvar-saati YOKTUR.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

LLM_USAGE_CONTRACT_VERSION = "llm_usage_v1"


def _sorted_int_map(d: Mapping[str, int]) -> dict:
    return {k: d[k] for k in sorted(d)}


@dataclass(frozen=True)
class UsageWindow:
    created_after: Optional[str]
    created_before: Optional[str]
    bucket: str
    trace_count: int
    generation_count: int
    truncated: bool
    scan_cap: int
    timeseries_truncated: bool = False

    def to_payload(self) -> dict:
        return {
            "created_after": self.created_after,
            "created_before": self.created_before,
            "bucket": self.bucket,
            "trace_count": self.trace_count,
            "generation_count": self.generation_count,
            "truncated": self.truncated,
            "scan_cap": self.scan_cap,
            "timeseries_truncated": self.timeseries_truncated,
        }


@dataclass(frozen=True)
class UsageTotals:
    request_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost: Optional[float]
    unpriced_request_count: int

    def to_payload(self) -> dict:
        return {
            "request_count": self.request_count,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost": self.estimated_cost,
            "unpriced_request_count": self.unpriced_request_count,
        }


@dataclass(frozen=True)
class ModelUsage:
    model_id: str
    request_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost: Optional[float]

    def to_payload(self) -> dict:
        return {
            "model_id": self.model_id,
            "request_count": self.request_count,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost": self.estimated_cost,
        }


@dataclass(frozen=True)
class ProviderUsage:
    provider_id: str
    request_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost: Optional[float]

    def to_payload(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "request_count": self.request_count,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost": self.estimated_cost,
        }


@dataclass(frozen=True)
class LatencyStats:
    count: int
    p50: Optional[float]
    p95: Optional[float]
    p99: Optional[float]

    def to_payload(self) -> dict:
        return {"count": self.count, "p50": self.p50, "p95": self.p95, "p99": self.p99}


@dataclass(frozen=True)
class UsageBucket:
    bucket_start: str
    request_count: int
    total_tokens: int
    estimated_cost: Optional[float]

    def to_payload(self) -> dict:
        return {
            "bucket_start": self.bucket_start,
            "request_count": self.request_count,
            "total_tokens": self.total_tokens,
            "estimated_cost": self.estimated_cost,
        }


@dataclass(frozen=True)
class PricingInfo:
    models_priced: Tuple[str, ...]
    models_missing_price: Tuple[str, ...]

    def to_payload(self) -> dict:
        return {
            "models_priced": list(self.models_priced),
            "models_missing_price": list(self.models_missing_price),
        }


@dataclass(frozen=True)
class LLMUsageReport:
    version: str
    currency: str
    window: UsageWindow
    totals: UsageTotals
    by_model: Tuple[ModelUsage, ...]
    by_provider: Tuple[ProviderUsage, ...]
    latency_ms: LatencyStats
    finish_reasons: Mapping[str, int]
    timeseries: Tuple[UsageBucket, ...]
    pricing: PricingInfo

    def to_payload(self) -> dict:
        return {
            "version": self.version,
            "currency": self.currency,
            "window": self.window.to_payload(),
            "totals": self.totals.to_payload(),
            "by_model": [m.to_payload() for m in self.by_model],
            "by_provider": [p.to_payload() for p in self.by_provider],
            "latency_ms": self.latency_ms.to_payload(),
            "finish_reasons": _sorted_int_map(self.finish_reasons),
            "timeseries": [b.to_payload() for b in self.timeseries],
            "pricing": self.pricing.to_payload(),
        }
