import sqlite3
import threading
import time

from fastapi.testclient import TestClient

from app.database import get_db_connection, get_db_path, init_db
from app.main import app
from app.settings import DEV_DEFAULT_API_KEY, get_settings

HEADERS = {"X-API-Key": DEV_DEFAULT_API_KEY}


def test_connection_sets_busy_timeout(monkeypatch):
    monkeypatch.setenv("NL2SQL_DB_BUSY_TIMEOUT_MS", "1234")
    get_settings.cache_clear()
    conn = get_db_connection()
    try:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 1234
    finally:
        conn.close()


def test_fresh_db_connection_has_default_busy_timeout(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLGEN_DB_PATH", str(tmp_path / "fresh.db"))
    get_settings.cache_clear()
    conn = get_db_connection()
    try:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    finally:
        conn.close()


def test_init_db_enables_wal():
    init_db()
    conn = sqlite3.connect(get_db_path())
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        conn.close()


def test_reader_not_blocked_by_exclusive_writer(monkeypatch):
    monkeypatch.setenv("NL2SQL_DB_BUSY_TIMEOUT_MS", "3000")
    get_settings.cache_clear()
    init_db()
    writer = sqlite3.connect(get_db_path(), isolation_level=None)
    result = {}

    def read():
        start = time.monotonic()
        resp = TestClient(app).get("/api/jobs", headers=HEADERS)
        result["status"] = resp.status_code
        result["elapsed"] = time.monotonic() - start

    try:
        writer.execute("BEGIN EXCLUSIVE")
        t = threading.Thread(target=read)
        t.start()
        t.join(timeout=10)
    finally:
        writer.execute("ROLLBACK")
        writer.close()
    assert result["status"] == 200
    assert result["elapsed"] < 2
