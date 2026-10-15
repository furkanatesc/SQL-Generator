"""Migration status of the app and trace databases (Sprint 32.3).

Used by startup validation and the `python -m app.migrations` CLI. Inspection is read-only
and never creates a database file (a missing file is reported as `exists=False`).
"""
import os
import sqlite3
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from app.migrations.app_db import APP_MIGRATIONS
from app.migrations.runner import Migration, MigrationStatus, inspect, migrate
from app.migrations.trace_db import TRACE_MIGRATIONS


@dataclass(frozen=True)
class ManagedDatabase:
    label: str  # "app" | "trace" — safe to show; paths are not
    path: Callable[[], str]
    migrations: Sequence[Migration]


def _app_db_path() -> str:
    from app.database import get_db_path

    return get_db_path()


def _trace_db_path() -> str:
    from app.trace.dependencies import get_trace_db_path

    return get_trace_db_path()


MANAGED_DATABASES: tuple[ManagedDatabase, ...] = (
    ManagedDatabase("app", _app_db_path, APP_MIGRATIONS),
    ManagedDatabase("trace", _trace_db_path, TRACE_MIGRATIONS),
)


def _open_existing(path: str) -> Optional[sqlite3.Connection]:
    if not os.path.isfile(path):
        return None
    return sqlite3.connect(f"file:{os.path.abspath(path)}?mode=ro", uri=True)


def database_statuses() -> list[tuple[ManagedDatabase, Optional[MigrationStatus]]]:
    """Read-only status per database; `None` when the file does not exist yet."""
    result = []
    for db in MANAGED_DATABASES:
        conn = _open_existing(db.path())
        if conn is None:
            result.append((db, None))
            continue
        try:
            result.append((db, inspect(conn, db.migrations)))
        finally:
            conn.close()
    return result


def upgrade_all() -> list[tuple[ManagedDatabase, MigrationStatus]]:
    """Apply pending migrations to both databases, creating them if needed."""
    result = []
    for db in MANAGED_DATABASES:
        path = db.path()
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        conn = sqlite3.connect(path)
        try:
            result.append((db, migrate(conn, db.migrations)))
        finally:
            conn.close()
    return result
