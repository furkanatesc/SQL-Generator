"""Sprint 29.6 — Pure local-Docker SQL Server connection resolver.

Single, reusable place a SQLMSSQLLocalDockerConnection (the read-only login)
is built from the MSSQL_TEST_* env contract. Never connects and never raises:
any invalid / remote / missing value yields None (inert), matching the
adapter's connection=None inert path.
"""

import os
from typing import Mapping, Optional

from app.evaluation.mssql_adapter import (
    SQLMSSQLAdapterContractError,
    SQLMSSQLLocalDockerConnection,
)

MSSQL_CONNECTION_RESOLVER_VERSION = "v1"


def resolve_local_docker_connection(
    env: Optional[Mapping[str, str]] = None,
) -> Optional[SQLMSSQLLocalDockerConnection]:
    src = os.environ if env is None else env
    host = src.get("MSSQL_TEST_HOST", "localhost")
    port_raw = src.get("MSSQL_TEST_PORT", "1433")
    database = src.get("MSSQL_TEST_DB", "sqlgen_test")
    user = src.get("MSSQL_TEST_USER", "sqlgen_ro")
    password = src.get("MSSQL_TEST_PASSWORD", "Sqlgen_Ro0!Pass")

    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        return None

    try:
        return SQLMSSQLLocalDockerConnection(
            host=host, port=port, database=database, user=user, password=password,
        )
    except (SQLMSSQLAdapterContractError, ValueError):
        return None
