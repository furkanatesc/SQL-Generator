"""Source-scan purity guard for app/cache/result_cache_key.py (Sprint 28.9)."""
from pathlib import Path

_SRC = (Path(__file__).resolve().parents[2]
        / "app" / "cache" / "result_cache_key.py").read_text(encoding="utf-8")

_FORBIDDEN = ["datetime", "perf_counter", "time.time", "time.monotonic", "monotonic",
              "random", "open(", "requests", "sqlite3", "qdrant",
              "from app.", "import app."]


def test_result_cache_key_is_pure():
    for token in _FORBIDDEN:
        assert token not in _SRC, f"result_cache_key.py must not reference {token!r}"
