"""Sprint 28.0 — dirty CLI for the large-schema benchmark suite.

Exit codes (27.10 convention): 0 clean, 1 deterministic-metric mismatch,
2 bad-input / malformed baseline. --update-baseline appends to history.json.
A CI perf-gate runs `--gate --scales 100,500,1000` (Sprint 28.1); it can also be run manually.
"""
import argparse
import json
import sys
from pathlib import Path

from benchmarks.bench_runner import run_benchmark, DEFAULT_SCALES
from benchmarks.bench_compare import compare_benchmark

BASELINE_PATH = Path(__file__).parent / "baselines" / "history.json"


def _load_history(path: Path):
    if not path.exists():
        return []
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("history.json must be a JSON list")
    return data


def _latest_baseline(history):
    return history[-1] if history else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Large Schema Benchmark Suite (Sprint 28.0)")
    parser.add_argument("--scales", type=str, default=None,
                        help="comma-separated table counts, e.g. 100,500,1000")
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--gate", action="store_true",
                        help="compare against latest baseline; exit 1 on drift")
    parser.add_argument("--update-baseline", action="store_true",
                        help="append this run to baselines/history.json")
    args = parser.parse_args(argv)

    if args.scales:
        try:
            scales = tuple(int(x) for x in args.scales.split(","))
        except ValueError as exc:
            print(f"BAD_INPUT: invalid --scales: {exc}", file=sys.stderr)
            return 2
    else:
        scales = DEFAULT_SCALES

    report = run_benchmark(scales=scales, seed=args.seed).to_dict()

    if args.gate:
        try:
            history = _load_history(BASELINE_PATH)
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"BAD_BASELINE: {exc}", file=sys.stderr)
            return 2
        result = compare_benchmark(report, _latest_baseline(history))
        print(json.dumps(result, indent=2))
        return 0 if result["gate_passed"] else 1

    if args.update_baseline:
        try:
            history = _load_history(BASELINE_PATH)
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"BAD_BASELINE: {exc}", file=sys.stderr)
            return 2
        history.append(report)
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(BASELINE_PATH, "w") as f:
            json.dump(history, f, indent=2)
        print(f"Appended baseline entry ({len(history)} total) to {BASELINE_PATH}")
        return 0

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
