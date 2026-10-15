"""Operator CLI for database migrations (Sprint 32.3).

    python -m app.migrations status    # read-only JSON report, always exit 0
    python -m app.migrations upgrade   # apply pending migrations; exit 1 on failure / DB ahead

Production: `docker compose -f docker-compose.prod.yml exec backend python -m app.migrations status`.
The backend also applies pending migrations on every start.
"""
import argparse
import json
import sys
from typing import Optional, Sequence

from app.migrations.status import database_statuses, upgrade_all


def _report(db, status, exists=True) -> dict:
    latest = db.migrations[-1].version
    if status is None:
        return {"db": db.label, "exists": False, "current": 0, "latest": latest,
                "pending": [m.version for m in db.migrations], "ahead": False}
    report = {"db": db.label, "exists": exists, "current": status.current, "latest": status.latest,
              "pending": status.pending, "ahead": status.ahead}
    if status.applied or status.error:
        report["applied"] = status.applied
        report["error"] = status.error
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.migrations")
    parser.add_argument("command", choices=["status", "upgrade"])
    args = parser.parse_args(argv)

    if args.command == "status":
        print(json.dumps([_report(db, s) for db, s in database_statuses()], indent=2))
        return 0

    results = upgrade_all()
    print(json.dumps([_report(db, s) for db, s in results], indent=2))
    return 0 if all(s.ok for _, s in results) else 1


if __name__ == "__main__":
    sys.exit(main())
