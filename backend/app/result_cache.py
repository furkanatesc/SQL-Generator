"""SQLite result-cache adaptor (Sprint 28.9).

Stores hash cache_key -> generated SQL (no raw NL query; secret-free). Backs the
deterministic exact result cache that short-circuits LLM generation in run_pipeline.
"""
import datetime

from app.database import get_db_connection


def is_result_cache_enabled(value) -> bool:
    """Default ON: None/empty -> True; only explicit off-token disables."""
    if value is None:
        return True
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def get_cached_sql(cache_key):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT sql FROM sql_cache WHERE cache_key = ?", (cache_key,))
        row = cur.fetchone()
        return row["sql"] if row else None


def put_cached_sql(cache_key, sql, dialect, schema_signature):
    now = datetime.datetime.utcnow().isoformat()
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO sql_cache "
            "(cache_key, sql, dialect, schema_signature, created_at, hit_count) "
            "VALUES (?, ?, ?, ?, ?, COALESCE((SELECT hit_count FROM sql_cache WHERE cache_key = ?), 0))",
            (cache_key, sql, dialect, schema_signature, now, cache_key),
        )
        conn.commit()


def bump_hit(cache_key):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE sql_cache SET hit_count = hit_count + 1 WHERE cache_key = ?", (cache_key,))
        conn.commit()


def clear_cache() -> int:
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS cnt FROM sql_cache")
        n = cur.fetchone()["cnt"]
        cur.execute("DELETE FROM sql_cache")
        conn.commit()
        return n


def cache_stats():
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS entries, COALESCE(SUM(hit_count), 0) AS total_hits FROM sql_cache")
        row = cur.fetchone()
        return {"entries": row["entries"], "total_hits": row["total_hits"]}
