"""SQLite result-cache adaptor (Sprint 28.9, Task 2)."""
import pytest
import app.database as db
import app.result_cache as rc


@pytest.fixture
def cache_db(monkeypatch, tmp_path):
    path = str(tmp_path / "sqlgen.db")
    monkeypatch.setattr(db, "get_db_path", lambda: path)
    db.init_db()
    return path


def test_put_get_roundtrip(cache_db):
    rc.put_cached_sql("k1", "SELECT 1", "postgres", "SIG")
    assert rc.get_cached_sql("k1") == "SELECT 1"


def test_get_miss_returns_none(cache_db):
    assert rc.get_cached_sql("nope") is None


def test_bump_hit_increments(cache_db):
    rc.put_cached_sql("k1", "SELECT 1", "postgres", "SIG")
    rc.bump_hit("k1")
    rc.bump_hit("k1")
    stats = rc.cache_stats()
    assert stats["entries"] == 1
    assert stats["total_hits"] == 2


def test_put_replace_preserves_hit_count(cache_db):
    rc.put_cached_sql("k1", "SELECT 1", "postgres", "SIG")
    rc.bump_hit("k1")
    rc.put_cached_sql("k1", "SELECT 2", "postgres", "SIG")   # re-cache same key
    assert rc.get_cached_sql("k1") == "SELECT 2"
    assert rc.cache_stats()["total_hits"] == 1               # hit_count preserved


def test_clear_cache_deletes_and_counts(cache_db):
    rc.put_cached_sql("k1", "SELECT 1", "postgres", "SIG")
    rc.put_cached_sql("k2", "SELECT 2", "postgres", "SIG")
    assert rc.clear_cache() == 2
    assert rc.cache_stats() == {"entries": 0, "total_hits": 0}


def test_no_raw_query_column():
    # sql_cache must NOT have a natural_query / query column (secret-free).
    import sqlite3
    cols = {c.split()[0] for c in
            ["cache_key", "sql", "dialect", "schema_signature", "created_at", "hit_count"]}
    assert "natural_query" not in cols and "query" not in cols


@pytest.mark.parametrize("value,expected", [
    (None, True), ("", True), ("1", True), ("true", True), ("on", True),
    ("0", False), ("false", False), ("no", False), ("off", False), ("FALSE", False),
])
def test_is_result_cache_enabled(value, expected):
    assert rc.is_result_cache_enabled(value) is expected
