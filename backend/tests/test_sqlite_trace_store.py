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
