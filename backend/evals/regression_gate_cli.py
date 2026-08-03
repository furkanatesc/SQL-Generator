"""Surum basina dogruluk regresyon kapisi — CLI (Sprint 27.10, KIRLI katman).

Golden eval raporunu okur, evals/baselines/history.json'daki son baseline'la
kiyaslar (evals.eval_gate_cli kardesi). Exit: 0 gecti (bootstrap dahil) /
1 regresyon / 2 bozuk girdi veya kullanim hatasi. --update-baseline ile yeni
surum baseline'i append edilir (elle, surum keserken; CI otomatik yazmaz).
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from evals.regression_gate import (
    append_baseline,
    build_baseline_entry,
    compare_regression,
    select_latest_baseline,
)

DEFAULT_BASELINE_PATH = "evals/baselines/history.json"
REQUIRED_REPORT_FIELDS = {"total", "passed", "failed", "pass_rate", "results"}


def _load_report(path: str) -> dict:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError("Eval report file not found") from exc
    try:
        report = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid eval report JSON") from exc
    if not isinstance(report, dict):
        raise ValueError("Invalid eval report schema")
    if REQUIRED_REPORT_FIELDS - set(report.keys()):
        raise ValueError("Invalid eval report schema")
    if not isinstance(report["results"], list):
        raise ValueError("Invalid eval report schema")
    return report


def _load_history(path: str) -> list:
    p = Path(path)
    if not p.exists():
        return []
    try:
        history = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid baseline history JSON") from exc
    if not isinstance(history, list):
        raise ValueError("Invalid baseline history schema")
    return history


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evals.regression_gate_cli",
        description="Per-release accuracy regression gate over a golden eval report.",
    )
    parser.add_argument("report", help="Path to the golden eval report JSON")
    parser.add_argument("--baseline", default=DEFAULT_BASELINE_PATH,
                        help="Path to baseline history.json")
    parser.add_argument("--update-baseline", action="store_true",
                        help="Append a new baseline entry from the report instead of gating")
    parser.add_argument("--version", help="Release version label (required with --update-baseline)")
    parser.add_argument("--timestamp", help="ISO-8601 timestamp for the baseline entry")
    parser.add_argument("--max-pass-rate-drop", type=float, default=0.0,
                        help="Allowed aggregate pass-rate drop over common cases (default 0.0)")
    return parser


def _run_update(args: Any, report: dict) -> int:
    if not args.version:
        print("--version is required with --update-baseline", file=sys.stderr)
        return 2
    try:
        history = _load_history(args.baseline)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    timestamp = args.timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = build_baseline_entry(report, version=args.version, timestamp=timestamp)
    try:
        new_history = append_baseline(history, entry)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    out = Path(args.baseline)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(new_history, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"updated": True, "version": args.version, "count": len(new_history)},
                     sort_keys=True))
    return 0


def _run_gate(args: Any, report: dict) -> int:
    try:
        history = _load_history(args.baseline)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    baseline = select_latest_baseline(history)
    result = compare_regression(report, baseline,
                                policy={"max_pass_rate_drop": args.max_pass_rate_drop})
    print(json.dumps(result, sort_keys=True))
    if result["bootstrap"]:
        print("No baseline recorded yet; bootstrapping (gate passes).", file=sys.stderr)
    return 0 if result["gate_passed"] else 1


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:   # argparse kullanim hatasi -> 2
        return exc.code if isinstance(exc.code, int) else 2
    try:
        report = _load_report(args.report)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.update_baseline:
        return _run_update(args, report)
    return _run_gate(args, report)


if __name__ == "__main__":
    raise SystemExit(main())
