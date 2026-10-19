"""CLI: python -m loadtest --base-url URL --scenario mixed --concurrency 8 --duration 10"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .core import SCENARIOS, evaluate, summarize
from .http_runner import run


def _format(summary: dict, violations: list[str]) -> str:
    rows = [("endpoint", "requests", "errors", "p50", "p95", "p99", "max")]

    def row(name: str, s: dict) -> tuple:
        lat = s["latency_ms"]
        return (name, str(s["requests"]), str(s["errors"]),
                f"{lat['p50']:.1f}", f"{lat['p95']:.1f}", f"{lat['p99']:.1f}", f"{lat['max']:.1f}")

    for name, s in sorted(summary["endpoints"].items()):
        rows.append(row(name, s))
    rows.append(row("TOTAL", summary))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    lines = ["  ".join(c.ljust(widths[i]) if i == 0 else c.rjust(widths[i]) for i, c in enumerate(r))
             for r in rows]
    lines.insert(1, "  ".join("-" * w for w in widths))
    lines.append(f"latency in ms; throughput {summary['throughput_rps']:.1f} req/s; "
                 f"error rate {summary['error_rate']:.4f}; statuses {summary['status_counts']}")
    lines.append("VIOLATIONS:" if violations else "OK: thresholds met")
    lines.extend(f"  - {v}" for v in violations)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="loadtest", description="Stdlib HTTP load test for the SQLGen API")
    p.add_argument("--base-url", required=True)
    p.add_argument("--api-key-file")
    p.add_argument("--scenario", choices=sorted(SCENARIOS), default="mixed")
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--duration", type=float, default=10.0)
    p.add_argument("--json", dest="json_path")
    p.add_argument("--max-error-rate", type=float, default=0.0)
    p.add_argument("--max-p95-ms", type=float, default=2000.0)
    args = p.parse_args(argv)

    if args.api_key_file:
        with open(args.api_key_file, encoding="utf-8") as fh:
            api_key = fh.read().strip()
    else:
        api_key = os.environ.get("NL2SQL_API_KEY", "")
    if not api_key:
        print("error: provide --api-key-file or set NL2SQL_API_KEY", file=sys.stderr)
        return 2

    results, elapsed = run(args.base_url, api_key, SCENARIOS[args.scenario], args.concurrency, args.duration)
    summary = summarize(results, elapsed)
    violations = evaluate(summary, args.max_error_rate, args.max_p95_ms)
    print(f"scenario={args.scenario} concurrency={args.concurrency} duration={args.duration}s")
    print(_format(summary, violations))
    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as fh:
            json.dump({"scenario": args.scenario, "concurrency": args.concurrency,
                       "duration_s": args.duration, "summary": summary, "violations": violations},
                      fh, indent=2)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
