# backend/tests/benchmarks/test_benchmarks_purity.py
from pathlib import Path

_PURE_MODULES = ["schema_generator.py", "bench_contract.py", "bench_metrics.py", "bench_compare.py"]
_BENCH_DIR = Path(__file__).resolve().parents[2] / "benchmarks"

_FORBIDDEN = ["datetime", "perf_counter", "time.time", "time.monotonic"]


def test_pure_modules_have_no_clock_or_datetime():
    for name in _PURE_MODULES:
        src = (_BENCH_DIR / name).read_text(encoding="utf-8")
        for token in _FORBIDDEN:
            assert token not in src, f"{name} must not reference {token!r} (pure/deterministic)"


def test_pure_modules_only_use_seeded_random():
    src = (_BENCH_DIR / "schema_generator.py").read_text(encoding="utf-8")
    # randomness must be seeded: every random usage goes through random.Random(...)
    assert "random.Random(" in src
    assert "random.random(" not in src   # no module-level global random
    assert "random.randrange(" not in src or "rng.randrange(" in src  # only via the seeded instance
