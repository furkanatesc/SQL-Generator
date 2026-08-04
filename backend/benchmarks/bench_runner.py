"""Sprint 28.0 — dirty benchmark runner.

Times four REUSED production functions across synthetic scales. wall_ms is
captured via an injected clock (default time.perf_counter) and is informational
only. Deterministic metrics come from benchmarks.bench_metrics.
"""
import time

from app.schema.schema_adapter import from_legacy_schema
from app.schema.graph_traversal import find_join_paths
from app.schema.schema_context_selector import select_schema_context
from app.schema.implicit_relationships import detect_implicit_relationships

from benchmarks import schema_generator as gen
from benchmarks import bench_metrics as metrics
from benchmarks.bench_contract import (
    BenchmarkMetric, BenchmarkReport, BENCHMARK_SCHEMA_VERSION,
)

DEFAULT_SCALES = (100, 500, 1000, 2000)


def run_benchmark(*, scales=DEFAULT_SCALES, seed=1729, dialect="postgres",
                  clock=time.perf_counter) -> BenchmarkReport:
    all_metrics = []
    for scale in scales:
        legacy = gen.generate_schema(table_count=scale, seed=seed, dialect=dialect)

        # Target 1: schema validation (from_legacy_schema parse + validator)
        t0 = clock()
        schema = from_legacy_schema(legacy, dialect)
        wall = (clock() - t0) * 1000.0
        all_metrics.append(BenchmarkMetric(
            "schema_validation", scale, metrics.derive_validation_metrics(schema), wall))

        table_names = [t.name for t in schema.tables]

        # Target 2: join-path DFS
        pairs = gen.generate_join_path_pairs(table_names, seed=seed)
        t0 = clock()
        jp_results = [(s, t, find_join_paths(schema, s, t)) for s, t in pairs]
        wall = (clock() - t0) * 1000.0
        all_metrics.append(BenchmarkMetric(
            "join_paths", scale,
            metrics.derive_join_path_metrics(jp_results, len(schema.relationships)), wall))

        # Target 3: implicit-FK inference
        t0 = clock()
        rels = detect_implicit_relationships(schema)
        wall = (clock() - t0) * 1000.0
        all_metrics.append(BenchmarkMetric(
            "implicit_fk", scale, metrics.derive_implicit_fk_metrics(rels), wall))

        # Target 4: lexical context selection
        questions = gen.generate_selection_questions(table_names, seed=seed)
        t0 = clock()
        sel_results = [select_schema_context(schema, q) for q in questions]
        wall = (clock() - t0) * 1000.0
        all_metrics.append(BenchmarkMetric(
            "context_selection", scale, metrics.derive_selection_metrics(sel_results), wall))

    params = {"seed": seed, "scales": list(scales), "dialect": dialect}
    return BenchmarkReport(BENCHMARK_SCHEMA_VERSION, params, tuple(all_metrics))
