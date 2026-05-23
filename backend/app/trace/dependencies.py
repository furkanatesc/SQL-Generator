import os
from functools import lru_cache

from app.trace.store import TraceStore
from app.trace.sqlite_store import SQLiteTraceStore


@lru_cache(maxsize=1)
def get_trace_store() -> TraceStore:
    db_path = os.getenv("NL2SQL_TRACE_DB_PATH", "data/nl2sql_traces.db")
    return SQLiteTraceStore(db_path)
