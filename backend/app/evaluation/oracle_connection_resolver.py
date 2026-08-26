"""Sprint 29.3 — Pure local-Docker Oracle connection resolver.

Single, reusable place a SQLOracleLocalDockerConnection is built from the
ORACLE_TEST_* env contract. Never connects and never raises: any invalid /
remote / missing value yields None (inert), matching the adapter's
connection=None inert path.
"""

import os
from typing import Mapping, Optional

from app.evaluation.oracle_adapter import (
    SQLOracleAdapterContractError,
    SQLOracleLocalDockerConnection,
)

ORACLE_CONNECTION_RESOLVER_VERSION = "v1"


def resolve_local_docker_connection(
    env: Optional[Mapping[str, str]] = None,
) -> Optional[SQLOracleLocalDockerConnection]:
    src = os.environ if env is None else env
    host = src.get("ORACLE_TEST_HOST", "localhost")
    port_raw = src.get("ORACLE_TEST_PORT", "1521")
    service_name = src.get("ORACLE_TEST_SERVICE", "FREEPDB1")
    user = src.get("ORACLE_TEST_USER", "sqlgen")
    password = src.get("ORACLE_TEST_PASSWORD", "sqlgen")

    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        return None

    try:
        return SQLOracleLocalDockerConnection(
            host=host,
            port=port,
            service_name=service_name,
            user=user,
            password=password,
        )
    except (SQLOracleAdapterContractError, ValueError):
        return None
