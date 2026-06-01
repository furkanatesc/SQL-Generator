import uuid
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

class DuplicateTraceError(Exception):
    pass

class TraceSerializationError(ValueError):
    pass

def generate_trace_id() -> str:
    return f"trace_{uuid.uuid4().hex}"

def ensure_json_serializable(payload: dict[str, Any]) -> None:
    try:
        json.dumps(payload)
    except (TypeError, ValueError) as e:
        raise TraceSerializationError(f"Payload is not JSON serializable: {e}")

@dataclass
class TraceRecord:
    trace_type: str
    payload: dict[str, Any]
    trace_id: str = field(default_factory=generate_trace_id)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    job_id: str | None = None
    request_id: str | None = None

    def __post_init__(self):
        if not self.trace_id:
            self.trace_id = generate_trace_id()
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        ensure_json_serializable(self.payload)

@dataclass
class TraceQuery:
    trace_type: str | None = None
    job_id: str | None = None
    request_id: str | None = None
    limit: int = 50
    offset: int = 0

@runtime_checkable
class TraceStore(Protocol):
    def save(self, trace: TraceRecord) -> TraceRecord:
        ...

    def get(self, trace_id: str) -> TraceRecord | None:
        ...

    def list(self, query: TraceQuery | None = None) -> list[TraceRecord]:
        ...

class InMemoryTraceStore:
    def __init__(self):
        self._store: dict[str, TraceRecord] = {}

    def save(self, trace: TraceRecord) -> TraceRecord:
        if trace.trace_id in self._store:
            raise DuplicateTraceError(f"Trace with id {trace.trace_id} already exists")
        self._store[trace.trace_id] = trace
        return trace

    def get(self, trace_id: str) -> TraceRecord | None:
        return self._store.get(trace_id)

    def list(self, query: TraceQuery | None = None) -> list[TraceRecord]:
        query = query or TraceQuery()
        
        traces = sorted(
            self._store.values(),
            key=lambda t: (t.created_at, t.trace_id),
            reverse=True
        )

        # Apply filters
        if query.trace_type is not None:
            traces = [t for t in traces if t.trace_type == query.trace_type]
        if query.job_id is not None:
            traces = [t for t in traces if t.job_id == query.job_id]
        if query.request_id is not None:
            traces = [t for t in traces if t.request_id == query.request_id]

        # Apply limit and offset
        return traces[query.offset : query.offset + query.limit]
