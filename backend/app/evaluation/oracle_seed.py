"""Sprint 29.4 — Oracle integration-seed applier (harness only).

Pure statement splitter + DB-API seed applier used by the Oracle CI job and
docker-compose flow. NOT wired into any runtime path and NOT re-exported from
``app.evaluation``. The ``oracledb`` driver is imported lazily inside ``main``
only, preserving the 29.3 driver-isolation posture.
"""

import os
import sys
from typing import Optional, Sequence, Tuple

ORACLE_SEED_VERSION = "v1"

_DEFAULT_SEED_PATH = os.path.join("tests", "fixtures", "oracle", "seed.sql")


def split_statements(sql: str) -> Tuple[str, ...]:
    """Split a plain DDL+INSERT script into ``;``-terminated statements.

    Strips ``--`` line comments and blank lines. No PL/SQL support (the seed
    contains none), so a simple split on ``;`` is correct and deterministic.
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


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CI entry-point: connect from ORACLE_TEST_* env and apply the seed file."""
    argv = list(sys.argv[1:] if argv is None else argv)
    seed_path = argv[0] if argv else _DEFAULT_SEED_PATH

    import oracledb  # noqa: WPS433 - runtime-only import, keeps driver isolation

    from app.evaluation.oracle_connection_resolver import (
        resolve_local_docker_connection,
    )

    conn_info = resolve_local_docker_connection()
    if conn_info is None:
        print("oracle_seed: no local Docker Oracle connection resolved", file=sys.stderr)
        return 1

    with open(seed_path, "r", encoding="utf-8") as fh:
        sql = fh.read()

    connection = oracledb.connect(
        user=conn_info.user,
        password=conn_info.password,
        dsn=f"{conn_info.host}:{conn_info.port}/{conn_info.service_name}",
    )
    try:
        applied = apply_seed(connection, sql)
    finally:
        connection.close()
    print(f"oracle_seed: applied {applied} statements from {seed_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
