from dataclasses import dataclass, field
import datetime as dt
from typing import Any, Dict, List, Optional
import uuid

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
