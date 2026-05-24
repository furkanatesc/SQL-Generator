from typing import Dict, List, Optional
from app.trace.models import NL2SQLTrace
from app.trace.store import TraceStore
from app.trace.query import TraceQuery

class InMemoryTraceStore(TraceStore):
    def __init__(self):
        self._traces: Dict[str, NL2SQLTrace] = {}

    def save(self, trace: NL2SQLTrace) -> None:
        self._traces[trace.trace_id] = trace

    def get(self, trace_id: str) -> Optional[NL2SQLTrace]:
        return self._traces.get(trace_id)

    def list_traces(self, query: TraceQuery) -> List[NL2SQLTrace]:
        items = sorted(self._traces.values(), key=lambda t: (t.created_at, t.trace_id), reverse=True)

        if query.sql_valid is not None:
            items = [t for t in items if t.sql_valid is query.sql_valid]

        if query.error_type:
            items = [t for t in items if t.error_type == query.error_type]

        if query.job_id:
            items = [t for t in items if t.metadata.get("job_id") == query.job_id]

        if query.dialect:
            items = [t for t in items if t.metadata.get("dialect") == query.dialect]

        if query.created_after:
            items = [t for t in items if t.created_at >= query.created_after]

        if query.created_before:
            items = [t for t in items if t.created_at <= query.created_before]

        return items[query.offset : query.offset + query.limit]
