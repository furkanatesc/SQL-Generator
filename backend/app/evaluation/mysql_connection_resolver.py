"""Sprint 29.5 — Pure local-Docker MySQL connection resolver.

Single, reusable place a SQLMySQLLocalDockerConnection is built from the
MYSQL_TEST_* env contract. Never connects and never raises: any invalid /
remote / missing value yields None (inert), matching the adapter's
connection=None inert path.
"""

import os
from typing import Mapping, Optional

from app.evaluation.mysql_adapter import (
    SQLMySQLAdapterContractError,
    SQLMySQLLocalDockerConnection,
)

MYSQL_CONNECTION_RESOLVER_VERSION = "v1"


def resolve_local_docker_connection(
    env: Optional[Mapping[str, str]] = None,
) -> Optional[SQLMySQLLocalDockerConnection]:
    src = os.environ if env is None else env
    host = src.get("MYSQL_TEST_HOST", "localhost")
    port_raw = src.get("MYSQL_TEST_PORT", "3306")
    database = src.get("MYSQL_TEST_DB", "sqlgen_test")
    user = src.get("MYSQL_TEST_USER", "sqlgen")
    password = src.get("MYSQL_TEST_PASSWORD", "sqlgen")

    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        return None

    try:
        return SQLMySQLLocalDockerConnection(
            host=host, port=port, database=database, user=user, password=password,
        )
    except (SQLMySQLAdapterContractError, ValueError):
        return None
