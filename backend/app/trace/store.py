from abc import ABC, abstractmethod
from typing import List, Optional
from app.trace.models import NL2SQLTrace
from app.trace.query import TraceQuery

class TraceStore(ABC):
    @abstractmethod
    def save(self, trace: NL2SQLTrace) -> None:
        pass

    @abstractmethod
    def get(self, trace_id: str) -> Optional[NL2SQLTrace]:
        pass

    @abstractmethod
    def list_traces(self, query: TraceQuery) -> List[NL2SQLTrace]:
        pass

    def list_recent(self, limit: int = 50) -> List[NL2SQLTrace]:
        return self.list_traces(TraceQuery(limit=limit))

class RecordingTraceStore(TraceStore):
    def __init__(self):
        self.saved: List[NL2SQLTrace] = []

    def save(self, trace: NL2SQLTrace) -> None:
        self.saved.append(trace)

    def get(self, trace_id: str) -> Optional[NL2SQLTrace]:
        for trace in self.saved:
            if trace.trace_id == trace_id:
                return trace
        return None

    def list_traces(self, query: TraceQuery) -> List[NL2SQLTrace]:
        # Return reversed to match typical store behavior of recent first
        return self.saved[::-1][:query.limit if query.limit else len(self.saved)]
