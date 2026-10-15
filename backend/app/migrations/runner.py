"""Forward-only, versioned SQLite migration runner (Sprint 32.3).

Each registry is a tuple of `Migration`s numbered 1..N. Applied versions are recorded in
`schema_migrations`; every pending migration runs in its own transaction together with its
bookkeeping row, so a failure leaves the database at the last good version. The runner never
raises: problems are returned in `MigrationStatus` and surfaced by startup validation
(`DB_MIGRATIONS_PENDING` / `DB_SCHEMA_AHEAD`), in line with the warn-only startup policy.

A shipped migration is never edited; a schema change is always a new version.
"""
import datetime as dt
import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

logger = logging.getLogger(__name__)

MIGRATIONS_TABLE = "schema_migrations"


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]


@dataclass
class MigrationStatus:
    current: int
    latest: int
    pending: list[int]
    ahead: bool
    applied: list[int] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return not self.pending and not self.ahead and self.error is None


def validate_registry(migrations: Sequence[Migration]) -> None:
    if not migrations:
        raise ValueError("migration registry is empty")
    versions = [m.version for m in migrations]
    if versions != list(range(1, len(migrations) + 1)):
        raise ValueError(f"migration versions must be 1..N without gaps, got {versions}")
    names = [m.name for m in migrations]
    if len(set(names)) != len(names):
        raise ValueError(f"migration names must be unique, got {names}")


def _has_migrations_table(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (MIGRATIONS_TABLE,)
    ).fetchone()
    return row is not None


def _current_version(conn: sqlite3.Connection) -> int:
    if not _has_migrations_table(conn):
        return 0
    row = conn.execute(f"SELECT MAX(version) FROM {MIGRATIONS_TABLE}").fetchone()
    return row[0] or 0


def inspect(conn: sqlite3.Connection, migrations: Sequence[Migration]) -> MigrationStatus:
    """Read-only status; never creates tables."""
    current = _current_version(conn)
    latest = migrations[-1].version if migrations else 0
    return MigrationStatus(
        current=current,
        latest=latest,
        pending=[m.version for m in migrations if m.version > current],
        ahead=current > latest,
    )


def migrate(conn: sqlite3.Connection, migrations: Sequence[Migration]) -> MigrationStatus:
    validate_registry(migrations)
    previous_isolation = conn.isolation_level
    if conn.in_transaction:
        conn.commit()
    conn.isolation_level = None  # explicit BEGIN/COMMIT so DDL is transactional
    applied: list[int] = []
    error: Optional[str] = None
    try:
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} ("
            "version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        status = inspect(conn, migrations)
        if status.ahead:
            logger.error(
                "database schema version %s is newer than this code (latest %s); no migrations applied",
                status.current, status.latest,
            )
            return status
        for migration in migrations:
            if migration.version not in status.pending:
                continue
            try:
                # IMMEDIATE takes the write lock up front; re-checking the version inside the
                # transaction lets a second process (e.g. backend + worker booting together)
                # skip a migration the first one just applied instead of failing on it.
                conn.execute("BEGIN IMMEDIATE")
                if _current_version(conn) >= migration.version:
                    conn.execute("COMMIT")
                    continue
                migration.apply(conn)
                conn.execute(
                    f"INSERT INTO {MIGRATIONS_TABLE} (version, name, applied_at) VALUES (?, ?, ?)",
                    (migration.version, migration.name, dt.datetime.now(dt.timezone.utc).isoformat()),
                )
                conn.execute("COMMIT")
            except Exception as exc:  # noqa: BLE001 — reported, never raised
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                error = type(exc).__name__
                logger.exception("migration %s (%s) failed; rolled back", migration.version, migration.name)
                break
            applied.append(migration.version)
    finally:
        conn.isolation_level = previous_isolation

    status = inspect(conn, migrations)
    status.applied = applied
    status.error = error
    return status


def ensure_column(conn: sqlite3.Connection, table: str, column: str, column_sql: str) -> None:
    """Idempotent `ALTER TABLE ... ADD COLUMN` for adopting pre-migration databases."""
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_sql}")
