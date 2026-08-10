"""Source-scan purity guard for app/schema/schema_signature.py (Sprint 28.7).

The module must stay stdlib-only and side-effect-free (no clock/datetime/random,
no I/O, no heavy app.* imports) so it is deterministic and safe to call on every
load_schema. Mirrors tests/benchmarks/test_benchmarks_purity.py.
"""
from pathlib import Path

_SRC = (Path(__file__).resolve().parents[2]
        / "app" / "schema" / "schema_signature.py").read_text(encoding="utf-8")

_FORBIDDEN = ["datetime", "perf_counter", "time.time", "time.monotonic",
              "random", "open(", "requests", "psycopg", "oracledb", "sqlite3",
              "from app.", "import app."]


def test_signature_module_is_pure():
    for token in _FORBIDDEN:
        assert token not in _SRC, f"schema_signature.py must not reference {token!r}"
