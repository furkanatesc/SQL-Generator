"""Operator CLI for backups (Sprint 32.8).

    python -m app.backup create [--no-qdrant] [--dir DIR]
    python -m app.backup verify ARCHIVE
    python -m app.backup list [--dir DIR]
    python -m app.backup restore ARCHIVE --yes [--include-qdrant] [--no-safety-backup]
    python -m app.backup prune --keep N [--dir DIR]

Output is JSON on stdout; failures exit 1. Stop the backend and worker before `restore`.
"""
import argparse
import json
import sys
from typing import Optional, Sequence

from app.backup.core import BackupError, create_backup, list_backups, prune_backups, restore_backup, verify_backup


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.backup")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create")
    p.add_argument("--no-qdrant", action="store_true")
    p.add_argument("--dir")
    p = sub.add_parser("verify")
    p.add_argument("archive")
    p = sub.add_parser("list")
    p.add_argument("--dir")
    p = sub.add_parser("restore")
    p.add_argument("archive")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--include-qdrant", action="store_true")
    p.add_argument("--no-safety-backup", action="store_true")
    p = sub.add_parser("prune")
    p.add_argument("--keep", type=int, required=True)
    p.add_argument("--dir")
    args = parser.parse_args(argv)

    def out(payload) -> None:
        print(json.dumps(payload, indent=2))

    try:
        if args.command == "create":
            out({"archive": str(create_backup(dest_dir=args.dir, include_qdrant=not args.no_qdrant))})
        elif args.command == "verify":
            result = verify_backup(args.archive)
            out({"ok": result.ok, "errors": result.errors})
            return 0 if result.ok else 1
        elif args.command == "list":
            out(list_backups(args.dir))
        elif args.command == "restore":
            if not args.yes:
                print("restore overwrites the current databases; stop the backend and worker, "
                      "then re-run with --yes", file=sys.stderr)
                return 1
            out(restore_backup(args.archive, include_qdrant=args.include_qdrant,
                               safety_backup=not args.no_safety_backup))
        elif args.command == "prune":
            out({"removed": prune_backups(args.keep, args.dir)})
    except (BackupError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    from app.logging_config import configure_logging

    configure_logging()  # logs go to stderr; stdout stays pure JSON
    sys.exit(main())
