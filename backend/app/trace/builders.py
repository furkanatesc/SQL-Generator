from typing import Any, Dict
from app.trace.models import NL2SQLTrace

def build_trace_from_pruned_schema(
    raw_query: str,
    pruned_schema: Dict[str, Any],
) -> NL2SQLTrace:
    debug_trace = pruned_schema.get("debug_trace", {})

    return NL2SQLTrace(
        raw_query=raw_query,
        candidate_signals=debug_trace.get("candidate_signals", []),
        rag_matches=debug_trace.get("rag_matches", []),
        graph_trace=debug_trace.get("graph_trace", {}),
        selected_tables=debug_trace.get("selected_tables", []),
        estimated_tokens=pruned_schema.get("estimated_tokens", 0),
        error_message=pruned_schema.get("error"),
    )
