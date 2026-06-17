import pytest
import hashlib
import json
import socket
from dataclasses import FrozenInstanceError

from app.evaluation.postgres_adapter import (
    SQL_POSTGRES_ADAPTER_CONTRACT_VERSION,
    SQLPostgresAdapterContractError,
    SQLPostgresAdapterStatus,
    SQLPostgresAdapterCapability,
    SQLPostgresAdapterConfig,
    SQLPostgresAdapterExecutionRequest,
    SQLPostgresAdapterExecutionResult,
    SQLPostgresAdapterContract,
)


def test_postgres_adapter_contract_version_is_stable():
    assert SQL_POSTGRES_ADAPTER_CONTRACT_VERSION == "sql_postgres_adapter_contract_v1"


def test_postgres_adapter_capability_is_immutable():
    cap = SQLPostgresAdapterCapability(
        version=SQL_POSTGRES_ADAPTER_CONTRACT_VERSION,
        dialect="postgresql",
        supports_live_execution=False,
        supports_driver_execution=False,
        supports_network_execution=False,
        supports_read_only_queries=False
    )
    with pytest.raises((FrozenInstanceError, AttributeError)):
        cap.version = "new_version"  # type: ignore


def test_postgres_adapter_capability_disables_live_execution():
    cap = SQLPostgresAdapterCapability(
        version=SQL_POSTGRES_ADAPTER_CONTRACT_VERSION,
        dialect="postgresql",
        supports_live_execution=False,
        supports_driver_execution=False,
        supports_network_execution=False,
        supports_read_only_queries=False
    )
    assert cap.supports_live_execution is False
    assert cap.supports_driver_execution is False
    assert cap.supports_network_execution is False
    assert cap.supports_read_only_queries is False


def test_postgres_adapter_execute_returns_not_implemented_without_driver():
    config = SQLPostgresAdapterConfig(
        timeout_seconds=5.0,
        max_rows=500,
        execution_mode="read_only"
    )
    request = SQLPostgresAdapterExecutionRequest(
        case_id="case-100",
        sql="SELECT * FROM my_table",
        dialect="postgresql",
        config=config,
        connection_ref="pg-conn-ref"
    )
    adapter = SQLPostgresAdapterContract()
    result = adapter.execute(request)
    
    assert isinstance(result, SQLPostgresAdapterExecutionResult)
    assert result.status == SQLPostgresAdapterStatus.NOT_IMPLEMENTED
    assert result.version == SQL_POSTGRES_ADAPTER_CONTRACT_VERSION
    assert result.case_id == "case-100"
    
    expected_hash = hashlib.sha256("SELECT * FROM my_table".encode("utf-8")).hexdigest()
    assert result.sql_sha256 == expected_hash
    assert "not implemented" in result.error.lower()


def test_postgres_adapter_rejects_without_network_or_secret_resolution(monkeypatch):
    # Intercept socket creation to ensure no network calls are made
    def mock_socket(*args, **kwargs):
        raise RuntimeError("Network socket usage is forbidden in this contract stub")
    monkeypatch.setattr(socket, "socket", mock_socket)

    # Intercept os.environ to ensure no env-var secret loading
    def mock_environ_get(*args, **kwargs):
        raise RuntimeError("Environment secret loading is forbidden in this contract stub")
    monkeypatch.setattr("os.environ.get", mock_environ_get)

    config = SQLPostgresAdapterConfig()
    request = SQLPostgresAdapterExecutionRequest(
        case_id="c1",
        sql="SELECT 1",
        dialect="postgresql",
        config=config
    )
    adapter = SQLPostgresAdapterContract()
    
    # Execute should run successfully (meaning it doesn't trigger our blocked socket/environ methods)
    result = adapter.execute(request)
    assert result.status == SQLPostgresAdapterStatus.NOT_IMPLEMENTED


def test_postgres_adapter_result_does_not_leak_connection_ref_or_secret():
    secret_conn = "postgres://user:password123@host:5432/dbname"
    config = SQLPostgresAdapterConfig()
    request = SQLPostgresAdapterExecutionRequest(
        case_id="c1",
        sql="SELECT * FROM secret_table",
        dialect="postgresql",
        config=config,
        connection_ref=secret_conn
    )
    adapter = SQLPostgresAdapterContract()
    result = adapter.execute(request)
    
    serialized = result.to_dict()
    serialized_str = json.dumps(serialized)
    
    # Assert connection_ref string or credentials never leak to the trace dictionary
    assert secret_conn not in serialized_str
    assert "password123" not in serialized_str


def test_postgres_adapter_import_does_not_load_db_drivers():
    import os
    import subprocess
    import sys
    import app.evaluation
    eval_dir = os.path.dirname(app.evaluation.__file__)
    
    code = (
        "import sys\n"
        f"sys.path.insert(0, {repr(eval_dir)})\n"
        "import postgres_adapter\n"
        "forbidden = ['psycopg', 'psycopg2', 'asyncpg', 'sqlalchemy']\n"
        "for mod in forbidden:\n"
        "    if mod in sys.modules:\n"
        "        print(f'FORBIDDEN:{mod}')\n"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True
    )
    assert "FORBIDDEN" not in res.stdout, f"Importing postgres_adapter loaded forbidden driver: {res.stdout}"


def test_postgres_adapter_import_does_not_load_socket_or_network_clients():
    import os
    import subprocess
    import sys
    import app.evaluation
    eval_dir = os.path.dirname(app.evaluation.__file__)
    
    code = (
        "import sys\n"
        f"sys.path.insert(0, {repr(eval_dir)})\n"
        "import postgres_adapter\n"
        "forbidden = ['requests', 'urllib', 'http.client', 'asyncio', 'socket']\n"
        "for mod in forbidden:\n"
        "    if mod in sys.modules:\n"
        "        print(f'FORBIDDEN:{mod}')\n"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True
    )
    assert "FORBIDDEN" not in res.stdout, f"Importing postgres_adapter loaded network client: {res.stdout}"


def test_postgres_adapter_capability_rejects_live_execution_true():
    with pytest.raises(SQLPostgresAdapterContractError, match="cannot support live execution"):
        SQLPostgresAdapterCapability(
            version=SQL_POSTGRES_ADAPTER_CONTRACT_VERSION,
            dialect="postgresql",
            supports_live_execution=True,
            supports_driver_execution=False,
            supports_network_execution=False,
            supports_read_only_queries=False,
        )


def test_postgres_adapter_capability_rejects_driver_execution_true():
    with pytest.raises(SQLPostgresAdapterContractError, match="cannot support driver execution"):
        SQLPostgresAdapterCapability(
            version=SQL_POSTGRES_ADAPTER_CONTRACT_VERSION,
            dialect="postgresql",
            supports_live_execution=False,
            supports_driver_execution=True,
            supports_network_execution=False,
            supports_read_only_queries=False,
        )


def test_postgres_adapter_capability_rejects_network_execution_true():
    with pytest.raises(SQLPostgresAdapterContractError, match="cannot support network execution"):
        SQLPostgresAdapterCapability(
            version=SQL_POSTGRES_ADAPTER_CONTRACT_VERSION,
            dialect="postgresql",
            supports_live_execution=False,
            supports_driver_execution=False,
            supports_network_execution=True,
            supports_read_only_queries=False,
        )


def test_postgres_adapter_capability_rejects_read_only_queries_true():
    with pytest.raises(SQLPostgresAdapterContractError, match="cannot support read-only query execution yet"):
        SQLPostgresAdapterCapability(
            version=SQL_POSTGRES_ADAPTER_CONTRACT_VERSION,
            dialect="postgresql",
            supports_live_execution=False,
            supports_driver_execution=False,
            supports_network_execution=False,
            supports_read_only_queries=True,
        )


def test_postgres_adapter_contract_rejects_unsafe_custom_capability():
    with pytest.raises(SQLPostgresAdapterContractError, match="capability must be a SQLPostgresAdapterCapability"):
        SQLPostgresAdapterContract(capability="not-a-capability-obj")  # type: ignore
