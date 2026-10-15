# Database Migrations

Since Sprint 32.3 the schemas of SQLGen's two SQLite databases are versioned:

| Database | Path variable | Registry |
| :--- | :--- | :--- |
| `app` | `SQLGEN_DB_PATH` | `backend/app/migrations/app_db.py` (`APP_MIGRATIONS`) |
| `trace` | `NL2SQL_TRACE_DB_PATH` | `backend/app/migrations/trace_db.py` (`TRACE_MIGRATIONS`) |

The runner (`backend/app/migrations/runner.py`) is forward-only. Applied versions are recorded in a
`schema_migrations` table (`version`, `name`, `applied_at`) inside each database.

## How it runs

- **On every start** the backend applies pending migrations: `init_db()` for the app database and
  `SQLiteTraceStore` for the trace database. A second start does nothing. The trace database is
  created lazily, on the first trace write, so `status` can report it as `exists: false` until then.
  Startup validation skips a database that does not exist yet.
- Each migration runs in **its own transaction** together with its `schema_migrations` row (SQLite DDL is
  transactional). If one fails it is rolled back, later migrations are not attempted, and the database
  stays at the last good version.
- The runner never crashes the app. Problems show up as critical startup warnings, so `/ready` returns 503:
  - `DB_MIGRATIONS_PENDING`: a migration failed (see the backend logs).
  - `DB_SCHEMA_AHEAD`: the database was migrated by a **newer** release than the running one, for example
    after a rollback to an older image. Nothing is applied. Run the newer image, or restore a backup taken
    before the upgrade (Sprint 32.8).
- Version 1 of each registry is the **baseline**: the schema the code used to create ad hoc before 32.3. It
  is idempotent (`CREATE ... IF NOT EXISTS` + `ensure_column`), so databases created before 32.3 are adopted
  without data loss.

## Shipped migrations

| DB | Version | Name | Sprint | Change |
| :--- | :--- | :--- | :--- | :--- |
| app | 1 | `baseline` | 32.3 | The pre-32.3 schema (12 tables, 6 indexes) |
| app | 2 | `job_worker` | 32.4 | Adds `jobs.worker_id`, `claimed_at` and `heartbeat_at`; adds the `job_logs` table and two indexes |
| trace | 1 | `baseline` | 32.3 | The pre-32.3 trace schema |

The runner opens each migration with `BEGIN IMMEDIATE` and checks the version again inside the
transaction. If the backend and the worker start at the same time, the second one skips a migration the
first one already applied.

## Operator CLI

```bash
python -m app.migrations status    # read-only JSON per database: exists, current, latest, pending, ahead
python -m app.migrations upgrade   # apply pending migrations; exit 1 on failure or when a DB is ahead

# Production compose:
docker compose -f docker-compose.prod.yml exec backend python -m app.migrations status
```

## Writing a migration

1. Append `Migration(N + 1, "<short_snake_name>", _fn)` to the registry. Versions must be 1..N without
   gaps and names must be unique (`validate_registry` runs at import time and in tests).
2. **Never edit a migration that has shipped.** Every schema change is a new version, because existing
   databases have already recorded the old one.
3. `_fn(conn)` receives a `sqlite3.Connection` that is already inside a transaction. Do not call
   `commit()` or `rollback()` in it.
4. Prefer additive changes. SQLite cannot drop or alter columns in place on older versions; use the
   "create new table → copy → drop → rename" pattern inside the migration.
5. Seed data (default configs, synonym bootstrap) is not schema. It stays in `init_db`.
6. Add a test to `backend/tests/test_migrations.py` that upgrades a database at the previous version and
   checks that existing data survives.

## Not covered (TECH-DEBT §39)

- No down migrations. Rollback means restoring a backup (32.8).
- No automatic backup before migrating.
- Concurrent start-up on one host is handled (`BEGIN IMMEDIATE` and a version re-check). There is no
  coordination across hosts.
- No checksum to detect an edited migration.
- No external database (Postgres) or Qdrant collection migrations.
