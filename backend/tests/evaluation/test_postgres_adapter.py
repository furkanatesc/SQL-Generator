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
    SQLPostgresLocalDockerConnection,
    SQLPostgresAdapterConfig,
    SQLPostgresAdapterExecutionRequest,
    SQLPostgresAdapterExecutionResult,
    SQLPostgresAdapterContract,
    default_local_docker_capability,
    validate_read_only_select,
)

EXPECTED_RESULT_KEYS = {
    "version", "case_id", "status", "sql_sha256",
    "rows", "row_count", "truncated", "error", "warnings", "columns", "duration_ms",
}


def _local_connection():
    return SQLPostgresLocalDockerConnection(
        host="localhost", port=5432, dbname="sqlgen_test",
        user="sqlgen", password="sqlgen",
    )


def _request(sql, *, case_id="c1", connection_ref=None):
    return SQLPostgresAdapterExecutionRequest(
        case_id=case_id,
        sql=sql,
        dialect="postgresql",
        config=SQLPostgresAdapterConfig(),
        connection_ref=connection_ref,
    )


def test_postgres_adapter_contract_version_is_stable():
    assert SQL_POSTGRES_ADAPTER_CONTRACT_VERSION == "sql_postgres_adapter_contract_v1"


def test_postgres_adapter_capability_is_immutable():
    cap = default_local_docker_capability()
    with pytest.raises((FrozenInstanceError, AttributeError)):
        cap.version = "new_version"  # type: ignore


def test_postgres_adapter_capability_supports_local_docker_read_only_only():
    cap = default_local_docker_capability()
    # Enabled: local-docker, driver, read-only, (local) network execution.
    assert cap.supports_local_docker_execution is True
    assert cap.supports_driver_execution is True
    assert cap.supports_read_only_queries is True
    assert cap.supports_network_execution is True
    # Forbidden: production / remote / live execution stay disabled.
    assert cap.supports_production_execution is False
    assert cap.supports_remote_execution is False
    assert cap.supports_live_execution is False


@pytest.mark.parametrize("field_name", [
    "supports_live_execution",
    "supports_remote_execution",
    "supports_production_execution",
])
def test_postgres_adapter_capability_rejects_unsafe_flag_true(field_name):
    kwargs = dict(
        version=SQL_POSTGRES_ADAPTER_CONTRACT_VERSION,
        dialect="postgresql",
        supports_live_execution=False,
        supports_driver_execution=True,
        supports_network_execution=True,
        supports_read_only_queries=True,
        supports_local_docker_execution=True,
        supports_remote_execution=False,
        supports_production_execution=False,
    )
    kwargs[field_name] = True
    with pytest.raises(SQLPostgresAdapterContractError):
        SQLPostgresAdapterCapability(**kwargs)


@pytest.mark.parametrize("field_name", [
    "supports_local_docker_execution",
    "supports_driver_execution",
    "supports_read_only_queries",
])
def test_postgres_adapter_capability_requires_local_docker_flag_true(field_name):
    kwargs = dict(
        version=SQL_POSTGRES_ADAPTER_CONTRACT_VERSION,
        dialect="postgresql",
        supports_live_execution=False,
        supports_driver_execution=True,
        supports_network_execution=True,
        supports_read_only_queries=True,
        supports_local_docker_execution=True,
        supports_remote_execution=False,
        supports_production_execution=False,
    )
    kwargs[field_name] = False
    with pytest.raises(SQLPostgresAdapterContractError):
        SQLPostgresAdapterCapability(**kwargs)


def test_postgres_adapter_rejects_remote_connection_config():
    with pytest.raises(SQLPostgresAdapterContractError, match="local Docker hosts"):
        SQLPostgresLocalDockerConnection(
            host="db.prod.internal", port=5432, dbname="app",
            user="app", password="secret",
        )


def test_postgres_adapter_rejects_production_environment():
    with pytest.raises(SQLPostgresAdapterContractError, match="local_docker"):
        SQLPostgresLocalDockerConnection(
            host="localhost", port=5432, dbname="app",
            user="app", password="secret", environment="production",
        )


def test_postgres_adapter_without_connection_is_inert():
    adapter = SQLPostgresAdapterContract()  # no connection wired
    result = adapter.execute(_request("SELECT 1", case_id="case-100"))
    assert result.status == SQLPostgresAdapterStatus.NOT_IMPLEMENTED
    assert result.sql_sha256 == hashlib.sha256(b"SELECT 1").hexdigest()
    assert result.rows == ()


@pytest.mark.parametrize("sql", [
    "INSERT INTO users (id) VALUES (1)",
    "UPDATE users SET name = 'x'",
    "DELETE FROM users",
])
def test_postgres_adapter_rejects_insert_update_delete(sql):
    adapter = SQLPostgresAdapterContract(connection=_local_connection())
    result = adapter.execute(_request(sql))
    assert result.status == SQLPostgresAdapterStatus.REJECTED
    assert result.rows == ()


@pytest.mark.parametrize("sql", [
    "DROP TABLE users",
    "ALTER TABLE users ADD COLUMN x int",
    "CREATE TABLE x (id int)",
    "TRUNCATE users",
    "COPY users TO '/tmp/x'",
    "CALL some_proc()",
])
def test_postgres_adapter_rejects_ddl_queries(sql):
    adapter = SQLPostgresAdapterContract(connection=_local_connection())
    result = adapter.execute(_request(sql))
    assert result.status == SQLPostgresAdapterStatus.REJECTED


def test_postgres_adapter_rejects_multi_statement_query():
    adapter = SQLPostgresAdapterContract(connection=_local_connection())
    result = adapter.execute(_request("SELECT * FROM users; DROP TABLE users;"))
    assert result.status == SQLPostgresAdapterStatus.REJECTED
    assert "single" in (result.error or "").lower()


def test_validate_read_only_select_allows_plain_select():
    assert validate_read_only_select("SELECT id, name FROM users") is None
    assert validate_read_only_select("  select 1  ") is None
    assert validate_read_only_select("SELECT 1;") is None  # single trailing semicolon ok


def test_postgres_adapter_rejection_path_opens_no_socket(monkeypatch):
    def _forbidden_socket(*args, **kwargs):
        raise RuntimeError("network access is forbidden on the rejection path")
    monkeypatch.setattr(socket, "socket", _forbidden_socket)

    adapter = SQLPostgresAdapterContract(connection=_local_connection())
    result = adapter.execute(_request("DELETE FROM users"))
    assert result.status == SQLPostgresAdapterStatus.REJECTED


def test_postgres_adapter_returns_deterministic_result_shape():
    adapter = SQLPostgresAdapterContract(connection=_local_connection())
    result = adapter.execute(_request("UPDATE users SET x = 1"))  # rejected, no DB needed
    serialized = result.to_dict()
    assert set(serialized.keys()) == EXPECTED_RESULT_KEYS
    assert serialized["status"] == "rejected"
    assert serialized["rows"] == []
    assert serialized["row_count"] == 0
    assert serialized["truncated"] is False
    # to_dict must be JSON-serializable
    json.dumps(serialized)


def test_postgres_adapter_does_not_leak_connection_ref_or_credentials():
    secret_conn = "postgres://user:password123@host:5432/dbname"
    adapter = SQLPostgresAdapterContract(connection=_local_connection())
    result = adapter.execute(_request("DROP TABLE secret", connection_ref=secret_conn))
    serialized_str = json.dumps(result.to_dict())
    assert secret_conn not in serialized_str
    assert "password123" not in serialized_str
    assert "sqlgen" not in serialized_str  # the connection user/password must not leak either


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
        check=True,
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
        check=True,
    )
    assert "FORBIDDEN" not in res.stdout, f"Importing postgres_adapter loaded network client: {res.stdout}"


def test_postgres_adapter_contract_rejects_unsafe_custom_capability():
    with pytest.raises(SQLPostgresAdapterContractError, match="capability must be a SQLPostgresAdapterCapability"):
        SQLPostgresAdapterContract(capability="not-a-capability-obj")  # type: ignore


def test_postgres_adapter_contract_rejects_invalid_connection_object():
    with pytest.raises(SQLPostgresAdapterContractError, match="connection must be a SQLPostgresLocalDockerConnection"):
        SQLPostgresAdapterContract(connection="not-a-connection")  # type: ignore


def test_execution_result_columns_defaults_empty():
    from app.evaluation.postgres_adapter import (
        SQLPostgresAdapterExecutionResult,
        SQL_POSTGRES_ADAPTER_CONTRACT_VERSION,
        SQLPostgresAdapterStatus,
    )
    import hashlib
    sql = "SELECT 1"
    res = SQLPostgresAdapterExecutionResult(
        version=SQL_POSTGRES_ADAPTER_CONTRACT_VERSION,
        case_id="c1",
        status=SQLPostgresAdapterStatus.NOT_IMPLEMENTED,
        sql_sha256=hashlib.sha256(sql.encode()).hexdigest(),
    )
    assert res.columns == ()
    assert res.to_dict()["columns"] == []


def test_execution_result_columns_roundtrip_and_validation():
    from app.evaluation.postgres_adapter import (
        SQLPostgresAdapterExecutionResult,
        SQL_POSTGRES_ADAPTER_CONTRACT_VERSION,
        SQLPostgresAdapterStatus,
        SQLPostgresAdapterContractError,
    )
    import hashlib, pytest
    sql = "SELECT id, name FROM customers"
    h = hashlib.sha256(sql.encode()).hexdigest()
    res = SQLPostgresAdapterExecutionResult(
        version=SQL_POSTGRES_ADAPTER_CONTRACT_VERSION,
        case_id="c1",
        status=SQLPostgresAdapterStatus.EXECUTED,
        sql_sha256=h,
        rows=((1, "a"),),
        row_count=1,
        columns=("id", "name"),
    )
    assert res.to_dict()["columns"] == ["id", "name"]
    with pytest.raises(SQLPostgresAdapterContractError):
        SQLPostgresAdapterExecutionResult(
            version=SQL_POSTGRES_ADAPTER_CONTRACT_VERSION, case_id="c1",
            status=SQLPostgresAdapterStatus.EXECUTED, sql_sha256=h,
            columns=("id", 5),  # non-str
        )


def test_adapter_config_explain_analyze_defaults_false():
    from app.evaluation.postgres_adapter import SQLPostgresAdapterConfig
    cfg = SQLPostgresAdapterConfig()
    assert cfg.explain_analyze is False


def test_adapter_config_explain_analyze_accepts_true():
    from app.evaluation.postgres_adapter import SQLPostgresAdapterConfig
    cfg = SQLPostgresAdapterConfig(explain_analyze=True)
    assert cfg.explain_analyze is True


def test_adapter_config_explain_analyze_rejects_non_bool():
    import pytest
    from app.evaluation.postgres_adapter import (
        SQLPostgresAdapterConfig,
        SQLPostgresAdapterContractError,
    )
    with pytest.raises(SQLPostgresAdapterContractError):
        SQLPostgresAdapterConfig(explain_analyze="yes")
