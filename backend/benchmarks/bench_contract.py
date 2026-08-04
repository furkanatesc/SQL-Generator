"""Sprint 28.0 — Large Schema Benchmark Suite: pure metric/report contract.

Frozen records with JSON-stable to_dict. No I/O, no clock, no randomness.
"""
from dataclasses import dataclass

BENCHMARK_SCHEMA_VERSION = "large_schema_benchmark_v2"


@dataclass(frozen=True)
class BenchmarkMetric:
    target: str          # "schema_validation" | "join_paths" | "implicit_fk" | "context_selection"
    scale: int           # 100 | 500 | 1000 | 2000
    deterministic: dict  # {metric_name: int} — the ONLY gated data
    wall_ms: float       # informational only, never gated

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "scale": self.scale,
            "deterministic": dict(sorted(self.deterministic.items())),
            "wall_ms": self.wall_ms,
        }


@dataclass(frozen=True)
class BenchmarkReport:
    schema_version: str
    generator_params: dict
    metrics: tuple  # tuple[BenchmarkMetric, ...]

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "generator_params": dict(sorted(self.generator_params.items())),
            "metrics": [m.to_dict() for m in self.metrics],
        }
