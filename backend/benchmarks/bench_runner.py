"""Sprint 28.1 — dirty benchmark runner v2.

Times four REUSED pure production functions across synthetic scales, capturing
deterministic internal-explosion counters via an injected ProfileProbe (one per
target). Adds a fifth graph_backend target exercising NetworkXGraphBackend via
the existing to_legacy_dict serialization. wall_ms informational (injected clock).
"""
import time

from app.schema.schema_adapter import from_legacy_schema, to_legacy_dict
from app.schema.graph_traversal import find_join_paths
from app.schema.schema_context_selector import select_schema_context
from app.schema.implicit_relationships import detect_implicit_relationships
from app.schema.profiling import ProfileProbe
from app.schema_graph.networkx_backend import NetworkXGraphBackend

from benchmarks import schema_generator as gen
from benchmarks import bench_metrics as metrics
from benchmarks.bench_contract import (
    BenchmarkMetric, BenchmarkReport, BENCHMARK_SCHEMA_VERSION,
)

DEFAULT_SCALES = (100, 500, 1000)
FK_DENSITY = 0.6
HUB_COUNT = 3


def _pagerank_seeds(table_names):
    # deterministic: first three table names as seeds, weight 1.0
    return {name: 1.0 for name in table_names[:3]}


def run_benchmark(*, scales=DEFAULT_SCALES, seed=1729, dialect="postgres",
                  clock=time.perf_counter) -> BenchmarkReport:
    all_metrics = []
    for scale in scales:
        legacy = gen.generate_schema(table_count=scale, seed=seed,
                                     fk_density=FK_DENSITY, hub_count=HUB_COUNT, dialect=dialect)

        # Target 1: schema validation
        t0 = clock()
        schema = from_legacy_schema(legacy, dialect)
        wall = (clock() - t0) * 1000.0
        all_metrics.append(BenchmarkMetric(
            "schema_validation", scale, metrics.derive_validation_metrics(schema), wall))

        table_names = [t.name for t in schema.tables]

        # Target 2: join-path DFS (one probe for the whole target)
        pairs = gen.generate_join_path_pairs(table_names, seed=seed)
        probe = ProfileProbe()
        t0 = clock()
        jp_results = [(s, t, find_join_paths(schema, s, t, probe=probe).paths) for s, t in pairs]
        wall = (clock() - t0) * 1000.0
        det = metrics.derive_join_path_metrics(jp_results, len(schema.relationships))
        det.update(probe.counts)
        all_metrics.append(BenchmarkMetric("join_paths", scale, det, wall))

        # Target 3: implicit-FK inference
        probe = ProfileProbe()
        t0 = clock()
        rels = detect_implicit_relationships(schema, probe=probe)
        wall = (clock() - t0) * 1000.0
        det = metrics.derive_implicit_fk_metrics(rels)
        det.update(probe.counts)
        all_metrics.append(BenchmarkMetric("implicit_fk", scale, det, wall))

        # Target 4: lexical context selection
        questions = gen.generate_selection_questions(table_names, seed=seed)
        probe = ProfileProbe()
        t0 = clock()
        sel_results = [select_schema_context(schema, q, probe=probe) for q in questions]
        wall = (clock() - t0) * 1000.0
        det = metrics.derive_selection_metrics(sel_results)
        det.update(probe.counts)
        all_metrics.append(BenchmarkMetric("context_selection", scale, det, wall))

        # Target 5: NetworkX graph backend (output-derived; pagerank run but NOT gated)
        graph_dict = to_legacy_dict(schema)
        backend = NetworkXGraphBackend()
        t0 = clock()
        backend.build_graph(graph_dict)
        backend.personalized_pagerank(_pagerank_seeds(table_names))  # run for timing; float NOT gated
        sp_results = [backend.shortest_path(s, t) for s, t in pairs]
        wall = (clock() - t0) * 1000.0
        graph_nodes = backend.G.number_of_nodes()
        graph_edges = backend.G.number_of_edges()
        det = metrics.derive_graph_backend_metrics(graph_nodes, graph_edges, sp_results)
        all_metrics.append(BenchmarkMetric("graph_backend", scale, det, wall))

    params = {"seed": seed, "scales": list(scales), "dialect": dialect,
              "fk_density": FK_DENSITY, "hub_count": HUB_COUNT}
    return BenchmarkReport(BENCHMARK_SCHEMA_VERSION, params, tuple(all_metrics))
