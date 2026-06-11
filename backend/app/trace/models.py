from dataclasses import dataclass, field
import datetime as dt
from typing import Any, Dict, List, Optional
import uuid
import json

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
    created_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    job_id: str | None = None
    request_id: str | None = None

    def __post_init__(self):
        if not self.trace_id:
            self.trace_id = generate_trace_id()
        if not isinstance(self.payload, dict):
            raise TypeError("payload must be a dictionary")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        ensure_json_serializable(self.payload)

@dataclass
class NL2SQLTrace:
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())

    raw_query: Optional[str] = None
    normalized_query: Optional[str] = None

    candidate_signals: List[Dict[str, Any]] = field(default_factory=list)
    rag_matches: List[Dict[str, Any]] = field(default_factory=list)
    graph_trace: Dict[str, Any] = field(default_factory=dict)

    selected_tables: List[str] = field(default_factory=list)
    dropped_tables: List[str] = field(default_factory=list)

    estimated_tokens: int = 0
    confidence: Optional[float] = None

    generated_sql: Optional[str] = None
    last_generated_sql: Optional[str] = None
    sql_valid: Optional[bool] = None
    sql_validation_errors: List[Dict[str, Any]] = field(default_factory=list)
    attempts: List[Dict[str, Any]] = field(default_factory=list)

    error_type: Optional[str] = None
    error_message: Optional[str] = None

    latency_ms: Dict[str, int] = field(default_factory=dict)

    metadata: Dict[str, Any] = field(default_factory=dict)
    schema_context_selection: Dict[str, Any] = field(default_factory=dict)
