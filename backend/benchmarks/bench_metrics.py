"""Sprint 28.0 — pure deterministic metric extractors.

Each extractor derives its metrics purely from the input schema and the
operation's OUTPUT (len/attrs). No production function is instrumented or
modified. All values are seed-deterministic and therefore exact-match gate-able.
"""

_RULE_BUCKET = {
    "singular_table_id_pattern": "rule1_singular_id",
    "fuzzy_prefix_match": "rule2_fuzzy",
    "exact_column_match": "rule3_exact",
}


def derive_validation_metrics(schema) -> dict:
    return {
        "tables": len(schema.tables),
        "columns_total": sum(len(t.columns) for t in schema.tables),
        "relationships_validated": len(schema.relationships),
        "valid": 1,  # a DatabaseSchema instance means validation passed
    }


def derive_join_path_metrics(results, adjacency_edges: int) -> dict:
    paths_found_total = sum(len(cands) for _, _, cands in results)
    path_edges_total = sum(len(c.edges) for _, _, cands in results for c in cands)
    pairs_with_path = sum(1 for _, _, cands in results if cands)
    return {
        "pairs_evaluated": len(results),
        "paths_found_total": paths_found_total,
        "path_edges_total": path_edges_total,
        "pairs_with_path": pairs_with_path,
        "adjacency_edges": adjacency_edges,
    }


def derive_implicit_fk_metrics(rels) -> dict:
    by_rule = {"rule1_singular_id": 0, "rule2_fuzzy": 0, "rule3_exact": 0, "other": 0}
    for r in rels:
        bucket = _RULE_BUCKET.get((r.raw or {}).get("rule"), "other")
        by_rule[bucket] += 1
    return {"implicit_rels_found": len(rels), **by_rule}


def derive_selection_metrics(results) -> dict:
    return {
        "questions_evaluated": len(results),
        "focus_tables_total": sum(len(s.focus_tables) for s in results),
        "selected_tables_total": sum(len(s.selected_tables) for s in results),
        "join_paths_total": sum(len(s.join_paths) for s in results),
        "fallback_used_count": sum(1 for s in results if s.fallback_used),
    }


def derive_graph_backend_metrics(graph_nodes: int, graph_edges: int, sp_results) -> dict:
    with_path = [p for p in sp_results if p]
    return {
        "graph_nodes": graph_nodes,
        "graph_edges": graph_edges,
        "sp_pairs_evaluated": len(sp_results),
        "sp_pairs_with_path": len(with_path),
        "sp_total_path_len": sum(len(p) for p in with_path),
    }
