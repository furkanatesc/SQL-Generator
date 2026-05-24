from app.trace.models import NL2SQLTrace
from app.trace.sqlite_store import SQLiteTraceStore


def test_sqlite_trace_store_save_and_get(tmp_path):
    db_path = tmp_path / "traces.db"
    store = SQLiteTraceStore(str(db_path))

    trace = NL2SQLTrace(
        raw_query="doktor listele",
        selected_tables=["HST_DOKTOR"],
        candidate_signals=[{"table": "HST_DOKTOR", "score": 0.9}],
        graph_trace={"path_mode": "undirected_weighted"},
        estimated_tokens=123,
        sql_valid=True,
        metadata={"env": "test"},
    )

    store.save(trace)

    loaded = store.get(trace.trace_id)

    assert loaded is not None
    assert loaded.trace_id == trace.trace_id
    assert loaded.raw_query == "doktor listele"
    assert loaded.selected_tables == ["HST_DOKTOR"]
    assert loaded.candidate_signals == [{"table": "HST_DOKTOR", "score": 0.9}]
    assert loaded.graph_trace == {"path_mode": "undirected_weighted"}
    assert loaded.estimated_tokens == 123
    assert loaded.sql_valid is True
    assert loaded.metadata == {"env": "test"}

def test_sqlite_trace_store_get_nonexistent_returns_none(tmp_path):
    store = SQLiteTraceStore(str(tmp_path / "traces.db"))
    assert store.get("missing") is None

def test_sqlite_trace_store_list_recent(tmp_path):
    store = SQLiteTraceStore(str(tmp_path / "traces.db"))

    old = NL2SQLTrace(raw_query="old", created_at="2026-01-01T00:00:00+00:00")
    new = NL2SQLTrace(raw_query="new", created_at="2026-01-02T00:00:00+00:00")

    store.save(old)
    store.save(new)

    recent = store.list_recent(limit=1)

    assert len(recent) == 1
    assert recent[0].raw_query == "new"

def test_sqlite_trace_store_save_replaces_existing_trace(tmp_path):
    store = SQLiteTraceStore(str(tmp_path / "traces.db"))

    trace = NL2SQLTrace(
        trace_id="trace-1",
        raw_query="first",
    )
    store.save(trace)

    trace.raw_query = "updated"
    trace.selected_tables = ["HST_DOKTOR"]
    store.save(trace)

    loaded = store.get("trace-1")

    assert loaded.raw_query == "updated"
    assert loaded.selected_tables == ["HST_DOKTOR"]

def test_sqlite_trace_store_preserves_sql_valid_tristate(tmp_path):
    store = SQLiteTraceStore(str(tmp_path / "traces.db"))

    traces = [
        NL2SQLTrace(trace_id="none", sql_valid=None),
        NL2SQLTrace(trace_id="true", sql_valid=True),
        NL2SQLTrace(trace_id="false", sql_valid=False),
    ]

    for trace in traces:
        store.save(trace)

    assert store.get("none").sql_valid is None
    assert store.get("true").sql_valid is True
    assert store.get("false").sql_valid is False

def test_sqlite_trace_store_round_trips_all_json_fields(tmp_path):
    store = SQLiteTraceStore(str(tmp_path / "traces.db"))

    trace = NL2SQLTrace(
        trace_id="trace-json",
        candidate_signals=[{"table": "HST_DOKTOR", "score": 0.9}],
        rag_matches=[{"table": "HST_DOKTOR", "raw_score": 0.82}],
        graph_trace={"path_mode": "undirected_weighted"},
        selected_tables=["HST_DOKTOR"],
        dropped_tables=["LOG"],
        last_generated_sql="SELECT broken",
        attempts=[{"attempt": 1, "valid": False}],
        sql_valid=False,
        sql_validation_errors=[
            {"type": "missing_column", "column": "x"},
            {"type": "unsafe_sql", "stage": "sql_guardrail", "message": "Only read-only SELECT statements are allowed", "details": {"reason": "dml_keyword_detected", "keyword": "DELETE"}}
        ],
        latency_ms={"total": 123, "llm": 90},
        metadata={"env": "test"},
    )

    store.save(trace)
    loaded = store.get("trace-json")

    assert loaded.candidate_signals == trace.candidate_signals
    assert loaded.rag_matches == trace.rag_matches
    assert loaded.graph_trace == trace.graph_trace
    assert loaded.selected_tables == trace.selected_tables
    assert loaded.dropped_tables == trace.dropped_tables
    assert loaded.last_generated_sql == trace.last_generated_sql
    assert loaded.attempts == trace.attempts
    assert loaded.sql_valid is False
    assert loaded.sql_validation_errors == trace.sql_validation_errors
    assert loaded.latency_ms == trace.latency_ms
    assert loaded.metadata == trace.metadata

def test_sqlite_trace_store_creates_parent_directory(tmp_path):
    db_path = tmp_path / "nested" / "trace" / "traces.db"

    store = SQLiteTraceStore(str(db_path))
    store.save(NL2SQLTrace(trace_id="trace-1", raw_query="test"))

    assert db_path.exists()
    assert store.get("trace-1") is not None

    store.close()

def test_sqlite_trace_store_reconnects_after_close(tmp_path):
    store = SQLiteTraceStore(str(tmp_path / "traces.db"))

    store.save(NL2SQLTrace(trace_id="trace-1", raw_query="first"))
    store.close()

    loaded = store.get("trace-1")

    assert loaded is not None
    assert loaded.raw_query == "first"

    store.close()

def test_sqlite_trace_store_migrates_existing_trace_table(tmp_path):
    import sqlite3

    db_path = tmp_path / "traces.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE nl2sql_traces (
                trace_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                raw_query TEXT,
                normalized_query TEXT,
                candidate_signals_json TEXT NOT NULL DEFAULT '[]',
                rag_matches_json TEXT NOT NULL DEFAULT '[]',
                graph_trace_json TEXT NOT NULL DEFAULT '{}',
                selected_tables_json TEXT NOT NULL DEFAULT '[]',
                dropped_tables_json TEXT NOT NULL DEFAULT '[]',
                estimated_tokens INTEGER NOT NULL DEFAULT 0,
                confidence REAL,
                generated_sql TEXT,
                sql_valid INTEGER,
                sql_validation_errors_json TEXT NOT NULL DEFAULT '[]',
                error_type TEXT,
                error_message TEXT,
                latency_ms_json TEXT NOT NULL DEFAULT '{}',
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )
        """)

    store = SQLiteTraceStore(str(db_path))

    trace = NL2SQLTrace(
        trace_id="t1",
        last_generated_sql="SELECT 1",
        attempts=[{"attempt": 1}],
    )
    store.save(trace)

    loaded = store.get("t1")
    assert loaded.last_generated_sql == "SELECT 1"
    assert loaded.attempts == [{"attempt": 1}]

from app.trace.query import TraceQuery

def test_sqlite_trace_store_filters_by_sql_valid(tmp_path):
    store = SQLiteTraceStore(str(tmp_path / "traces.db"))
    store.save(NL2SQLTrace(trace_id="t1", sql_valid=True))
    store.save(NL2SQLTrace(trace_id="t2", sql_valid=False))
    store.save(NL2SQLTrace(trace_id="t3", sql_valid=None))

    assert len(store.list_traces(TraceQuery(sql_valid=True))) == 1
    assert store.list_traces(TraceQuery(sql_valid=True))[0].trace_id == "t1"
    
    assert len(store.list_traces(TraceQuery(sql_valid=False))) == 1
    assert store.list_traces(TraceQuery(sql_valid=False))[0].trace_id == "t2"

def test_sqlite_trace_store_filters_by_error_type(tmp_path):
    store = SQLiteTraceStore(str(tmp_path / "traces.db"))
    store.save(NL2SQLTrace(trace_id="t1", error_type="type1"))
    store.save(NL2SQLTrace(trace_id="t2", error_type="type2"))

    res = store.list_traces(TraceQuery(error_type="type1"))
    assert len(res) == 1
    assert res[0].trace_id == "t1"

def test_sqlite_trace_store_filters_by_job_id(tmp_path):
    store = SQLiteTraceStore(str(tmp_path / "traces.db"))
    store.save(NL2SQLTrace(trace_id="t1", metadata={"job_id": "j1"}))
    store.save(NL2SQLTrace(trace_id="t2", metadata={"job_id": "j2"}))

    res = store.list_traces(TraceQuery(job_id="j1"))
    assert len(res) == 1
    assert res[0].trace_id == "t1"

def test_sqlite_trace_store_filters_by_dialect(tmp_path):
    store = SQLiteTraceStore(str(tmp_path / "traces.db"))
    store.save(NL2SQLTrace(trace_id="t1", metadata={"dialect": "postgres"}))
    store.save(NL2SQLTrace(trace_id="t2", metadata={"dialect": "mysql"}))

    res = store.list_traces(TraceQuery(dialect="postgres"))
    assert len(res) == 1
    assert res[0].trace_id == "t1"

def test_sqlite_trace_store_applies_limit_and_offset(tmp_path):
    store = SQLiteTraceStore(str(tmp_path / "traces.db"))
    for i in range(5):
        store.save(NL2SQLTrace(trace_id=f"t{i}", created_at=f"2026-01-0{i+1}T00:00:00+00:00"))

    res = store.list_traces(TraceQuery(limit=2, offset=1))
    assert len(res) == 2
    assert res[0].trace_id == "t3"
    assert res[1].trace_id == "t2"

def test_sqlite_trace_store_combines_filters_with_and_semantics(tmp_path):
    store = SQLiteTraceStore(str(tmp_path / "traces.db"))
    store.save(NL2SQLTrace(trace_id="t1", sql_valid=False, error_type="e1"))
    store.save(NL2SQLTrace(trace_id="t2", sql_valid=False, error_type="e2"))
    store.save(NL2SQLTrace(trace_id="t3", sql_valid=True, error_type="e1"))

    res = store.list_traces(TraceQuery(sql_valid=False, error_type="e1"))
    assert len(res) == 1
    assert res[0].trace_id == "t1"

def test_sqlite_trace_store_adds_job_id_and_dialect_columns_to_existing_db(tmp_path):
    import sqlite3
    db_path = tmp_path / "traces.db"
    
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE nl2sql_traces (
                trace_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                raw_query TEXT,
                normalized_query TEXT,
                candidate_signals_json TEXT NOT NULL DEFAULT '[]',
                rag_matches_json TEXT NOT NULL DEFAULT '[]',
                graph_trace_json TEXT NOT NULL DEFAULT '{}',
                selected_tables_json TEXT NOT NULL DEFAULT '[]',
                dropped_tables_json TEXT NOT NULL DEFAULT '[]',
                estimated_tokens INTEGER NOT NULL DEFAULT 0,
                confidence REAL,
                generated_sql TEXT,
                sql_valid INTEGER,
                sql_validation_errors_json TEXT NOT NULL DEFAULT '[]',
                error_type TEXT,
                error_message TEXT,
                latency_ms_json TEXT NOT NULL DEFAULT '{}',
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )
        """)
        
    store = SQLiteTraceStore(str(db_path))
    trace = NL2SQLTrace(
        trace_id="t1",
        metadata={"job_id": "job-1", "dialect": "psql"}
    )
    store.save(trace)
    
    loaded = store.get("t1")
    assert loaded.metadata.get("job_id") == "job-1"
    assert loaded.metadata.get("dialect") == "psql"
    
    res = store.list_traces(TraceQuery(job_id="job-1"))
    assert len(res) == 1
    
    # Also verify the columns were actually added
    with sqlite3.connect(db_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(nl2sql_traces)").fetchall()}
        assert "job_id" in cols
        assert "dialect" in cols

def test_sqlite_trace_store_backfills_job_id_and_dialect_from_existing_metadata(tmp_path):
    import sqlite3
    import json

    db_path = tmp_path / "traces.db"

    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE nl2sql_traces (
                trace_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                raw_query TEXT,
                normalized_query TEXT,
                candidate_signals_json TEXT NOT NULL DEFAULT '[]',
                rag_matches_json TEXT NOT NULL DEFAULT '[]',
                graph_trace_json TEXT NOT NULL DEFAULT '{}',
                selected_tables_json TEXT NOT NULL DEFAULT '[]',
                dropped_tables_json TEXT NOT NULL DEFAULT '[]',
                estimated_tokens INTEGER NOT NULL DEFAULT 0,
                confidence REAL,
                generated_sql TEXT,
                sql_valid INTEGER,
                sql_validation_errors_json TEXT NOT NULL DEFAULT '[]',
                error_type TEXT,
                error_message TEXT,
                latency_ms_json TEXT NOT NULL DEFAULT '{}',
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )
        """)
        conn.execute("""
            INSERT INTO nl2sql_traces (
                trace_id,
                created_at,
                metadata_json
            )
            VALUES (?, ?, ?)
        """, (
            "old-trace",
            "2026-01-01T00:00:00+00:00",
            json.dumps({"job_id": "old-job", "dialect": "postgres"}),
        ))

    store = SQLiteTraceStore(str(db_path))

    by_job = store.list_traces(TraceQuery(job_id="old-job"))
    assert len(by_job) == 1
    assert by_job[0].trace_id == "old-trace"

    by_dialect = store.list_traces(TraceQuery(dialect="postgres"))
    assert len(by_dialect) == 1
    assert by_dialect[0].trace_id == "old-trace"
