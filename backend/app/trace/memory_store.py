from typing import Dict, List, Optional, TypeVar, Any, Generic
import datetime as dt
from app.trace.models import DuplicateTraceError
from app.trace.store import TraceStore
from app.trace.query import TraceQuery

T_Trace = TypeVar("T_Trace")

class InMemoryTraceStore(Generic[T_Trace]):
    def __init__(self):
        self._traces: Dict[str, T_Trace] = {}

    def save(self, trace: T_Trace) -> T_Trace:
        if getattr(trace, "trace_id") in self._traces:
            raise DuplicateTraceError(f"Trace with id {getattr(trace, 'trace_id')} already exists")
        if hasattr(trace, "payload") and isinstance(trace.payload, dict):
            from app.trace.models import ensure_json_serializable
            ensure_json_serializable(trace.payload)
        self._traces[getattr(trace, "trace_id")] = trace
        return trace

    def get(self, trace_id: str) -> Optional[T_Trace]:
        return self._traces.get(trace_id)

    def list_traces(self, query: Optional[TraceQuery] = None) -> List[T_Trace]:
        query = query or TraceQuery()

        def get_created_at_dt(t):
            cat = getattr(t, "created_at")
            if isinstance(cat, str):
                try:
                    return dt.datetime.fromisoformat(cat)
                except ValueError:
                    pass
            return cat

        items = sorted(self._traces.values(), key=lambda t: (get_created_at_dt(t), getattr(t, "trace_id")), reverse=True)

        if query.sql_valid is not None:
            items = [t for t in items if getattr(t, "sql_valid", None) is query.sql_valid or (isinstance(getattr(t, "payload", None), dict) and t.payload.get("sql_valid") is query.sql_valid)]

        if query.error_type:
            items = [t for t in items if getattr(t, "error_type", None) == query.error_type or (isinstance(getattr(t, "payload", None), dict) and t.payload.get("error_type") == query.error_type)]

        if query.job_id:
            items = [t for t in items if (getattr(t, "job_id", None) == query.job_id) or (getattr(t, "metadata", {}).get("job_id") == query.job_id)]

        if query.dialect:
            items = [t for t in items if getattr(t, "metadata", {}).get("dialect") == query.dialect or (isinstance(getattr(t, "payload", None), dict) and t.payload.get("dialect") == query.dialect)]

        if query.created_after:
            try:
                created_after_dt = dt.datetime.fromisoformat(query.created_after)
            except ValueError:
                created_after_dt = query.created_after
            items = [t for t in items if get_created_at_dt(t) >= created_after_dt]

        if query.created_before:
            try:
                created_before_dt = dt.datetime.fromisoformat(query.created_before)
            except ValueError:
                created_before_dt = query.created_before
            items = [t for t in items if get_created_at_dt(t) <= created_before_dt]

        if query.trace_type is not None:
            items = [t for t in items if getattr(t, "trace_type", None) == query.trace_type]
            
        if query.request_id is not None:
            items = [t for t in items if getattr(t, "request_id", None) == query.request_id]

        return items[query.offset : query.offset + query.limit]

    def list_recent(self, limit: int = 50) -> List[T_Trace]:
        return self.list_traces(TraceQuery(limit=limit))
