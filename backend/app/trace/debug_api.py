import datetime as dt
from typing import Any, List, Optional
from app.trace.models import NL2SQLTrace, TraceRecord
from app.trace.store import TraceStore
from app.trace.query import TraceQuery
from app.trace.redaction import redact_sensitive

def redact_sensitive_dict(d: Any) -> Any:
    """
    Recursively scans and redacts any dictionary keys containing credential words,
    and runs recursively through sub-dictionaries and lists.
    """
    if isinstance(d, dict):
        res = {}
        for k, v in d.items():
            k_lower = str(k).lower()
            if any(word in k_lower for word in ["api_key", "password", "token", "secret", "api-key"]):
                res[k] = "[REDACTED]"
            else:
                res[k] = redact_sensitive_dict(v)
        return res
    elif isinstance(d, list):
        return [redact_sensitive_dict(item) for item in d]
    return d

def serialize_trace_for_debug(trace: TraceRecord | NL2SQLTrace) -> dict:
    """
    Serializes a TraceRecord or legacy NL2SQLTrace into a canonical DTO dictionary
    while applying sensitive value redaction and maintaining root-level key backwards compatibility.
    """
    if isinstance(trace, TraceRecord):
        # Canonical TraceRecord DTO
        res = {
            "trace_id": trace.trace_id,
            "trace_type": trace.trace_type,
            "created_at": trace.created_at.isoformat() if isinstance(trace.created_at, dt.datetime) else str(trace.created_at),
            "job_id": trace.job_id,
            "request_id": trace.request_id,
            "payload": trace.payload,
        }
        # Mirror payload keys at root level for test & consumer backwards compatibility
        if isinstance(trace.payload, dict):
            for k, v in trace.payload.items():
                if k not in res:
                    res[k] = v
        
        # Apply dictionary-key redaction first, then pattern-based redaction
        redacted = redact_sensitive_dict(res)
        return redact_sensitive(redacted)
    else:
        # Legacy NL2SQLTrace DTO
        metadata = getattr(trace, "metadata", {}) or {}
        job_id = metadata.get("job_id") or getattr(trace, "job_id", None)
        request_id = metadata.get("request_id") or getattr(trace, "request_id", None)
        
        payload = {
            "raw_query": getattr(trace, "raw_query", None),
            "normalized_query": getattr(trace, "normalized_query", None),
            "candidate_signals": getattr(trace, "candidate_signals", []),
            "rag_matches": getattr(trace, "rag_matches", []),
            "graph_trace": getattr(trace, "graph_trace", {}),
            "selected_tables": getattr(trace, "selected_tables", []),
            "dropped_tables": getattr(trace, "dropped_tables", []),
            "estimated_tokens": getattr(trace, "estimated_tokens", 0),
            "confidence": getattr(trace, "confidence", None),
            "generated_sql": getattr(trace, "generated_sql", None),
            "last_generated_sql": getattr(trace, "last_generated_sql", None),
            "sql_valid": getattr(trace, "sql_valid", None),
            "sql_validation_errors": getattr(trace, "sql_validation_errors", []),
            "attempts": getattr(trace, "attempts", []),
            "error_type": getattr(trace, "error_type", None),
            "error_message": getattr(trace, "error_message", None),
            "latency_ms": getattr(trace, "latency_ms", {}),
            "metadata": metadata,
        }
        
        res = {
            "trace_id": trace.trace_id,
            "trace_type": "nl2sql",
            "created_at": trace.created_at.isoformat() if isinstance(trace.created_at, dt.datetime) else str(trace.created_at),
            "job_id": job_id,
            "request_id": request_id,
            "payload": payload,
        }
        # Add legacy properties to root-level for backwards compatibility
        for k, v in payload.items():
            if k not in res:
                res[k] = v
                
        # Apply dictionary-key redaction first, then pattern-based redaction
        redacted = redact_sensitive_dict(res)
        return redact_sensitive(redacted)

def _matches_debug_query(item: dict, query: TraceQuery) -> bool:
    """
    Validates a serialized trace dictionary DTO against the query filters.
    """
    if query.trace_type is not None and item.get("trace_type") != query.trace_type:
        return False
    if query.request_id is not None and item.get("request_id") != query.request_id:
        return False
    if query.job_id is not None and item.get("job_id") != query.job_id:
        return False
    if query.dialect is not None:
        dialect = item.get("dialect") or item.get("payload", {}).get("dialect") or item.get("payload", {}).get("metadata", {}).get("dialect")
        if dialect != query.dialect:
            return False
    if query.sql_valid is not None:
        sql_valid = item.get("sql_valid")
        if sql_valid is None:
            sql_valid = item.get("payload", {}).get("sql_valid")
        if sql_valid is not query.sql_valid:
            return False
    if query.error_type is not None:
        error_type = item.get("error_type") or item.get("payload", {}).get("error_type")
        if error_type != query.error_type:
            return False

    def get_dt(val):
        cat = val.get("created_at")
        if isinstance(cat, str):
            try:
                return dt.datetime.fromisoformat(cat)
            except ValueError:
                pass
        return cat

    if query.created_after is not None:
        item_dt = get_dt(item)
        try:
            query_dt = dt.datetime.fromisoformat(query.created_after)
            if item_dt and query_dt and item_dt < query_dt:
                return False
        except ValueError:
            pass

    if query.created_before is not None:
        item_dt = get_dt(item)
        try:
            query_dt = dt.datetime.fromisoformat(query.created_before)
            if item_dt and query_dt and item_dt > query_dt:
                return False
        except ValueError:
            pass

    return True

class DebugTraceAdapter:
    """
    Adapter class to encapsulate fallback store-probing logic
    and serve standardized trace dictionaries to the debug API.
    """
    def __init__(self, store: TraceStore):
        self.store = store

    def get_trace(self, trace_id: str) -> Optional[dict]:
        # Probe legacy SQLiteTraceStore table if exists
        if hasattr(self.store, "get_legacy"):
            trace = self.store.get_legacy(trace_id)
            if trace is not None:
                return serialize_trace_for_debug(trace)
        
        trace = self.store.get(trace_id)
        if trace is not None:
            return serialize_trace_for_debug(trace)
        return None

    def list_traces(self, query: TraceQuery) -> List[dict]:
        # Merge lists from both canonical and legacy tables if the store has dual capabilities
        if hasattr(self.store, "list_traces_legacy"):
            sub_query = TraceQuery(
                limit=query.offset + query.limit,
                offset=0,
                trace_type=query.trace_type,
                request_id=query.request_id,
                job_id=query.job_id,
                dialect=query.dialect,
                created_after=query.created_after,
                created_before=query.created_before,
                sql_valid=query.sql_valid,
                error_type=query.error_type,
            )
            
            canonical_traces = self.store.list_traces(sub_query)
            legacy_traces = self.store.list_traces_legacy(sub_query)
            
            serialized = [serialize_trace_for_debug(t) for t in canonical_traces] + \
                         [serialize_trace_for_debug(t) for t in legacy_traces]
            
            # Apply DTO-level final filtering to resolve trace_type and request_id constraints correctly
            serialized = [t for t in serialized if _matches_debug_query(t, query)]
            
            # Sort descending chronologically (created_at DESC, trace_id DESC)
            def get_dt(item):
                cat = item.get("created_at")
                if isinstance(cat, str):
                    try:
                        return dt.datetime.fromisoformat(cat)
                    except ValueError:
                        pass
                return cat

            serialized.sort(key=lambda x: (get_dt(x), x.get("trace_id", "")), reverse=True)
            
            # Return exact paginated slice
            return serialized[query.offset : query.offset + query.limit]
        else:
            # Single-store implementations (e.g. InMemoryTraceStore)
            traces = self.store.list_traces(query)
            return [serialize_trace_for_debug(t) for t in traces]
