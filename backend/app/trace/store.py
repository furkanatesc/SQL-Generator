from typing import TypeVar, Protocol, runtime_checkable, List, Optional
from app.trace.query import TraceQuery

T_Trace = TypeVar("T_Trace")

@runtime_checkable
class TraceStore(Protocol[T_Trace]):
    def save(self, trace: T_Trace) -> T_Trace:
        ...

    def get(self, trace_id: str) -> Optional[T_Trace]:
        ...

    def list_traces(self, query: Optional[TraceQuery] = None) -> List[T_Trace]:
        ...

    def list_recent(self, limit: int = 50) -> List[T_Trace]:
        return self.list_traces(TraceQuery(limit=limit))
