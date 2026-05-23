from typing import Any, Dict, Optional
from app.trace.models import NL2SQLTrace

def build_trace_from_pruned_schema(
    raw_query: str,
    pruned_schema: Dict[str, Any],
    generated_sql: Optional[str] = None,
    error_message: Optional[str] = None,
    error_type: Optional[str] = None,
    latency_ms: Optional[Dict[str, int]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> NL2SQLTrace:
    debug_trace = pruned_schema.get("debug_trace", {})

    return NL2SQLTrace(
        raw_query=raw_query,
        candidate_signals=debug_trace.get("candidate_signals", []),
        rag_matches=debug_trace.get("rag_matches", []),
        graph_trace=debug_trace.get("graph_trace", {}),
        selected_tables=debug_trace.get("selected_tables", []),
        estimated_tokens=pruned_schema.get("estimated_tokens", 0),
        generated_sql=generated_sql,
        error_message=error_message or pruned_schema.get("error"),
        error_type=error_type,
        latency_ms=latency_ms or {},
        metadata=metadata or {},
    )
