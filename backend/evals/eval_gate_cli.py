import json
import sys
from pathlib import Path
from typing import Any

from evals.eval_gate import evaluate_release_gate


REQUIRED_REPORT_FIELDS = {
    "total",
    "passed",
    "failed",
    "pass_rate",
    "failed_cases",
}


def _load_report(path: str) -> dict[str, Any]:
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

    missing = REQUIRED_REPORT_FIELDS - set(report.keys())
    if missing:
        raise ValueError("Invalid eval report schema")

    return report


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if len(args) != 1:
        print("Usage: python -m evals.eval_gate_cli <report.json>", file=sys.stderr)
        return 2

    try:
        report = _load_report(args[0])
        gate_result = evaluate_release_gate(report)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(gate_result, sort_keys=True))
    return 0 if gate_result["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
