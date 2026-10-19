"""Pure load-test logic: scenarios, scheduling, percentiles, summaries, thresholds."""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Callable, Sequence


@dataclass(frozen=True)
class RequestSpec:
    name: str
    method: str
    path: str
    expected: frozenset
    weight: int = 1
    # body(run, seq) -> JSON body; `run` is a per-run id, `seq` a per-run counter.
    body: Callable[[str, int], dict] | None = None


@dataclass(frozen=True)
class Result:
    name: str
    status: int | None
    latency_ms: float
    ok: bool


def _workspace_body(run: str, seq: int) -> dict:
    return {"name": f"load-{run}-{seq}", "slug": f"load-{run}-{seq}"}


def _job_body(run: str, seq: int) -> dict:
    return {"natural_query": "load test"}


_READ = (
    RequestSpec("health", "GET", "/health", frozenset({200})),
    RequestSpec("ready", "GET", "/ready", frozenset({200})),
    RequestSpec("jobs_list", "GET", "/api/jobs", frozenset({200})),
    RequestSpec("query_history", "GET", "/api/v1/query-history", frozenset({200})),
    RequestSpec("workspaces_list", "GET", "/api/v1/workspaces", frozenset({200})),
)
_WRITE = (
    RequestSpec("workspace_create", "POST", "/api/v1/workspaces", frozenset({201}), body=_workspace_body),
    RequestSpec("job_create", "POST", "/api/jobs/without-file", frozenset({200}), body=_job_body),
)


def _weighted(specs: Sequence[RequestSpec], weight: int) -> tuple[RequestSpec, ...]:
    return tuple(RequestSpec(s.name, s.method, s.path, s.expected, weight, s.body) for s in specs)


SCENARIOS: dict[str, tuple[RequestSpec, ...]] = {
    "read": _READ,
    "write": _WRITE,
    "mixed": _weighted(_READ, 3) + _weighted(_WRITE, 1),
}


def percentile(values: Sequence[float], p: float) -> float:
    """Nearest-rank percentile; 0.0 for empty input."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100.0 * len(ordered)))
    return float(ordered[min(rank, len(ordered)) - 1])


def schedule(specs: Sequence[RequestSpec], n: int) -> list[RequestSpec]:
    """Deterministic weighted round-robin: expand each spec by weight, then cycle."""
    expanded = [s for s in specs for _ in range(max(1, s.weight))]
    if not expanded:
        return []
    return [expanded[i % len(expanded)] for i in range(n)]


def _stats(results: Sequence[Result], duration_s: float) -> dict:
    n = len(results)
    errors = sum(1 for r in results if not r.ok)
    lat = [r.latency_ms for r in results]
    return {
        "requests": n,
        "errors": errors,
        "error_rate": (errors / n) if n else 1.0,
        "throughput_rps": (n / duration_s) if duration_s > 0 else 0.0,
        "latency_ms": {
            "p50": percentile(lat, 50),
            "p95": percentile(lat, 95),
            "p99": percentile(lat, 99),
            "max": float(max(lat)) if lat else 0.0,
        },
        "status_counts": dict(Counter(str(r.status) for r in results)),
    }


def summarize(results: Sequence[Result], duration_s: float) -> dict:
    summary = _stats(results, duration_s)
    by_name: dict[str, list[Result]] = {}
    for r in results:
        by_name.setdefault(r.name, []).append(r)
    summary["endpoints"] = {name: _stats(rs, duration_s) for name, rs in by_name.items()}
    return summary


def evaluate(summary: dict, max_error_rate: float, max_p95_ms: float) -> list[str]:
    violations = []
    if summary["error_rate"] > max_error_rate:
        violations.append(f"error rate {summary['error_rate']:.4f} exceeds max {max_error_rate:.4f}")
    p95 = summary["latency_ms"]["p95"]
    if p95 > max_p95_ms:
        violations.append(f"p95 latency {p95:.1f} ms exceeds max {max_p95_ms:.1f} ms")
    return violations
