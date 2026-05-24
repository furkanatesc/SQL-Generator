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
