"""Source-scan purity guard for app/schema/reindex_planner.py (Sprint 28.8).

Must stay stdlib-only and side-effect-free (deterministic, safe to call on every
load_schema). Mirrors tests/schema/test_schema_signature_purity.py.
"""
from pathlib import Path

_SRC = (Path(__file__).resolve().parents[2]
        / "app" / "schema" / "reindex_planner.py").read_text(encoding="utf-8")

_FORBIDDEN = ["datetime", "perf_counter", "time.time", "time.monotonic", "monotonic",
              "random", "open(", "requests", "qdrant", "psycopg", "oracledb", "sqlite3",
              "from app.", "import app."]


def test_reindex_planner_is_pure():
    for token in _FORBIDDEN:
        assert token not in _SRC, f"reindex_planner.py must not reference {token!r}"
