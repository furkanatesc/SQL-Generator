"""Sprint 29.0 — Pure local-Docker PostgreSQL connection resolver.

Single, reusable place a SQLPostgresLocalDockerConnection is built from the
POSTGRES_TEST_* env contract. Never connects to a database and never raises:
any invalid / remote / missing value yields None (inert), matching the 25.8
adapter's connection=None inert path.
"""

import os
from typing import Mapping, Optional

from app.evaluation.postgres_adapter import (
    SQLPostgresAdapterContractError,
    SQLPostgresLocalDockerConnection,
)

POSTGRES_CONNECTION_RESOLVER_VERSION = "v1"


def resolve_local_docker_connection(
    env: Optional[Mapping[str, str]] = None,
) -> Optional[SQLPostgresLocalDockerConnection]:
    src = os.environ if env is None else env
    host = src.get("POSTGRES_TEST_HOST", "localhost")
    port_raw = src.get("POSTGRES_TEST_PORT", "5432")
    dbname = src.get("POSTGRES_TEST_DB", "sqlgen_test")
    user = src.get("POSTGRES_TEST_USER", "sqlgen")
    password = src.get("POSTGRES_TEST_PASSWORD", "sqlgen")

    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        return None

    try:
        return SQLPostgresLocalDockerConnection(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
        )
    except (SQLPostgresAdapterContractError, ValueError):
        return None
