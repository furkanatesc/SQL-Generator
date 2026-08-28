"""Sprint 29.6 — SQL Server integration-seed applier (harness only).

Pure statement splitter + DB-API seed applier used by the SQL Server CI job
and docker-compose flow. NOT wired into any runtime path and NOT re-exported
from ``app.evaluation``. The ``pymssql`` driver is imported lazily inside
``main`` only, preserving the 29.5/29.6 driver-isolation posture.

``split_statements`` / ``apply_seed`` are a deliberate per-dialect duplicate
of ``mysql_seed.py`` (29.5) rather than a shared helper: plain DDL+INSERT
script parsing with no stored-procedure support, verbatim across dialects.

SQL Server needs orchestration the other dialects don't: the seed database
does not exist until created, and a read-only login/user pair must be
provisioned after the seed is applied. ``readonly_login_ddl`` builds that
DDL as pure, validated strings; ``main`` sequences admin connections against
``master`` (create DB + login) and then ``sqlgen_test`` (apply seed, then
create user + grant db_datareader).
"""

import os
import re
import time
from typing import Optional, Sequence, Tuple

MSSQL_SEED_VERSION = "v1"

_IDENT_RE = re.compile(r"^[A-Za-z0-9_]+$")


def split_statements(sql: str) -> Tuple[str, ...]:
    """Split a plain DDL+INSERT script into ``;``-terminated statements.

    Strips ``--`` line comments and blank lines. No stored procedure support
    (the seed contains none), so a simple split on ``;`` is correct and
    deterministic.
    """
    lines = []
    for raw in sql.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("--"):
            continue
        lines.append(raw)
    joined = "\n".join(lines)
    out = []
    for chunk in joined.split(";"):
        stmt = chunk.strip()
        if stmt:
            out.append(stmt)
    return tuple(out)


def apply_seed(connection, sql: str) -> int:
    """Execute each statement of ``sql`` on ``connection`` and commit once.

    ``connection`` is an already-open DB-API connection (injected). Returns the
    number of statements applied.
    """
    statements = split_statements(sql)
    cursor = connection.cursor()
    try:
        for stmt in statements:
            cursor.execute(stmt)
    finally:
        cursor.close()
    connection.commit()
    return len(statements)


def _validate_identifier(name: str) -> str:
    if not _IDENT_RE.match(name or ""):
        raise ValueError("SQL Server identifier must be alphanumeric/underscore")
    return name


def readonly_login_ddl(login: str, password: str, database: str) -> Tuple[str, str, str]:
    """Idempotent DDL to create a db_datareader-only login/user. Pure (no I/O).

    Identifiers are validated (alnum/underscore); the password must not contain
    a single quote (values come from trusted CI env, not user input).
    """
    _validate_identifier(login)
    _validate_identifier(database)
    if "'" in password:
        raise ValueError("read-only password must not contain a single quote")
    return (
        f"IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'{login}') "
        f"CREATE LOGIN [{login}] WITH PASSWORD = N'{password}', CHECK_POLICY = OFF;",
        f"IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'{login}') "
        f"CREATE USER [{login}] FOR LOGIN [{login}];",
        f"ALTER ROLE db_datareader ADD MEMBER [{login}];",
    )


def _connect_with_retry(pymssql, *, attempts=30, delay=2.0, **kwargs):
    """Bounded retry loop owning container readiness.

    The mcr mssql image has no reliable healthcheck, so the caller (``main``)
    must poll the admin connection itself rather than assume readiness.
    """
    last = None
    for _ in range(attempts):
        try:
            return pymssql.connect(**kwargs)
        except Exception as exc:  # noqa: BLE001 - readiness wait
            last = exc
            time.sleep(delay)
    raise last


def _exec(conn, sql: str) -> None:
    cur = conn.cursor()
    try:
        cur.execute(sql)
    finally:
        cur.close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CI entry-point: create the DB + seed it + provision a RO login.

    Reads admin creds from MSSQL_TEST_ADMIN_USER/MSSQL_TEST_ADMIN_PASSWORD
    (default sa / Sqlgen_Str0ng!Pass) and RO creds from MSSQL_TEST_USER/
    MSSQL_TEST_PASSWORD (default sqlgen_ro / Sqlgen_Ro0!Pass).
    """
    import pymssql  # noqa: WPS433 - runtime-only import, keeps driver isolation

    host = os.environ.get("MSSQL_TEST_HOST", "localhost")
    port = int(os.environ.get("MSSQL_TEST_PORT", "1433"))
    database = os.environ.get("MSSQL_TEST_DB", "sqlgen_test")
    admin_user = os.environ.get("MSSQL_TEST_ADMIN_USER", "sa")
    admin_password = os.environ.get("MSSQL_TEST_ADMIN_PASSWORD", "Sqlgen_Str0ng!Pass")
    ro_user = os.environ.get("MSSQL_TEST_USER", "sqlgen_ro")
    ro_password = os.environ.get("MSSQL_TEST_PASSWORD", "Sqlgen_Ro0!Pass")

    create_login, create_user, grant_role = readonly_login_ddl(ro_user, ro_password, database)

    # Phase A: master — wait for readiness, create DB + RO login (autocommit for DDL).
    master = _connect_with_retry(
        pymssql, server=host, port=port, user=admin_user,
        password=admin_password, database="master", login_timeout=5,
    )
    try:
        master.autocommit(True)
        _exec(master, f"IF DB_ID(N'{database}') IS NULL CREATE DATABASE [{database}];")
        _exec(master, create_login)
    finally:
        master.close()

    # Phase B: sqlgen_test — apply the seed (transactional), then the RO user + role (autocommit).
    seed_path = os.path.join(os.path.dirname(__file__), "..", "..", "tests", "fixtures", "mssql", "seed.sql")
    with open(os.path.abspath(seed_path), "r", encoding="utf-8") as fh:
        seed_sql = fh.read()

    conn = pymssql.connect(server=host, port=port, user=admin_user, password=admin_password, database=database)
    try:
        count = apply_seed(conn, seed_sql)
        conn.autocommit(True)
        _exec(conn, create_user)
        _exec(conn, grant_role)
    finally:
        conn.close()

    print(f"applied {count} statements; provisioned read-only login {ro_user}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
