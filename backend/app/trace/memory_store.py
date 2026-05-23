from typing import Dict, List, Optional
from app.trace.models import NL2SQLTrace
from app.trace.store import TraceStore

class InMemoryTraceStore(TraceStore):
    def __init__(self):
        self._traces: Dict[str, NL2SQLTrace] = {}

    def save(self, trace: NL2SQLTrace) -> None:
        self._traces[trace.trace_id] = trace

    def get(self, trace_id: str) -> Optional[NL2SQLTrace]:
        return self._traces.get(trace_id)

    def list_recent(self, limit: int = 50) -> List[NL2SQLTrace]:
        traces = list(self._traces.values())
        traces.sort(key=lambda t: t.created_at, reverse=True)
        return traces[:limit]
