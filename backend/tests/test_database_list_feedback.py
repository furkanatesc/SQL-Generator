"""database.list_feedback — pencere-bazli feedback satirlari (Sprint 27.7).

Izolasyon: get_db_connection() her cagriyi get_db_path() -> SQLGEN_DB_PATH env
uzerinden cozer (bkz. conftest.py session fixture'i). Bu yuzden her test taze bir
tmp DB'ye SQLGEN_DB_PATH'i monkeypatch'ler ve init_db calistirir; boylece session
DB'sindeki diger feedback satirlarindan izole kalir.
"""
import pytest

from app import database


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    db = tmp_path / "fb.db"
    monkeypatch.setenv("SQLGEN_DB_PATH", str(db))
    database.init_db()
    return db


def test_list_feedback_window_filter_and_order(isolated_db):
    database.create_job("j1", natural_query="q")
    # created_at DB tarafinda now() ile atanir; siralamayi rowid tiebreak korur
    database.create_feedback("f1", "j1", "incorrect", "wrong_columns", None, None)
    database.create_feedback("f2", "j1", "correct", None, None, None)

    rows = database.list_feedback()
    assert len(rows) == 2
    # DESC created_at, rowid -> en son eklenen (f2) once
    assert rows[0]["id"] == "f2"
    assert {r["verdict"] for r in rows} == {"incorrect", "correct"}
    assert rows[0]["job_id"] == "j1"


def test_list_feedback_limit_and_empty(isolated_db):
    assert database.list_feedback() == []
    database.create_job("j1", natural_query="q")
    database.create_feedback("f1", "j1", "correct", None, None, None)
    database.create_feedback("f2", "j1", "correct", None, None, None)
    assert len(database.list_feedback(limit=1)) == 1


def test_list_feedback_created_before_filter(isolated_db):
    database.create_job("j1", natural_query="q")
    database.create_feedback("f1", "j1", "correct", None, None, None)
    # gelecekteki bir created_before -> satir gelmeli; gecmisteki -> gelmemeli
    assert len(database.list_feedback(created_before="2099-01-01T00:00:00")) == 1
    assert database.list_feedback(created_before="2000-01-01T00:00:00") == []


def test_list_feedback_offset_aware_boundary_matches_naive_utc_rows(isolated_db, monkeypatch):
    # feedback.created_at is stored naive-UTC (datetime.utcnow().isoformat()). An
    # offset-aware created_after boundary representing the SAME instant must still
    # include a row created at/after it. Before the fix, the offset-suffixed string
    # sorts lexicographically greater than the naive stored value and the row is
    # wrongly excluded.
    import datetime as dt_module

    # Same instant as the boundary below, naive-UTC, no microseconds -> isoformat()
    # produces "2026-08-07T00:00:00", a string-prefix of the offset-aware boundary
    # "2026-08-07T00:00:00+00:00" and therefore lexicographically LESS than it.
    fixed_now = dt_module.datetime(2026, 8, 7, 0, 0, 0)

    class _FixedDateTime(dt_module.datetime):
        @classmethod
        def utcnow(cls):
            return fixed_now

    monkeypatch.setattr(dt_module, "datetime", _FixedDateTime)

    database.create_job("j1", natural_query="q")
    database.create_feedback("f1", "j1", "correct", None, None, None)

    rows = database.list_feedback(created_after="2026-08-07T00:00:00+00:00")
    assert len(rows) == 1
    assert rows[0]["id"] == "f1"
