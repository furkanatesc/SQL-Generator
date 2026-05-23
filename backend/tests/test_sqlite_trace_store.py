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
        sql_validation_errors=[{"type": "missing_column", "column": "x"}],
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
    assert loaded.sql_validation_errors == trace.sql_validation_errors
    assert loaded.latency_ms == trace.latency_ms
    assert loaded.metadata == trace.metadata
