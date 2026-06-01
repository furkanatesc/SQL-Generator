from typing import Dict, List, Optional, TypeVar, Any, Generic
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
        self._traces[getattr(trace, "trace_id")] = trace
        return trace

    def get(self, trace_id: str) -> Optional[T_Trace]:
        return self._traces.get(trace_id)

    def list_traces(self, query: Optional[TraceQuery] = None) -> List[T_Trace]:
        query = query or TraceQuery()
        items = sorted(self._traces.values(), key=lambda t: (getattr(t, "created_at"), getattr(t, "trace_id")), reverse=True)

        if query.sql_valid is not None:
            items = [t for t in items if getattr(t, "sql_valid", None) is query.sql_valid]

        if query.error_type:
            items = [t for t in items if getattr(t, "error_type", None) == query.error_type]

        if query.job_id:
            items = [t for t in items if (getattr(t, "job_id", None) == query.job_id) or (getattr(t, "metadata", {}).get("job_id") == query.job_id)]

        if query.dialect:
            items = [t for t in items if getattr(t, "metadata", {}).get("dialect") == query.dialect]

        if query.created_after:
            items = [t for t in items if getattr(t, "created_at", "") >= query.created_after]

        if query.created_before:
            items = [t for t in items if getattr(t, "created_at", "") <= query.created_before]

        if query.trace_type is not None:
            items = [t for t in items if getattr(t, "trace_type", None) == query.trace_type]
            
        if query.request_id is not None:
            items = [t for t in items if getattr(t, "request_id", None) == query.request_id]

        return items[query.offset : query.offset + query.limit]

    def list_recent(self, limit: int = 50) -> List[T_Trace]:
        return self.list_traces(TraceQuery(limit=limit))
