import pytest
import hashlib
import json
import os
import socket
from dataclasses import FrozenInstanceError

from app.evaluation.oracle_adapter import (
    SQL_ORACLE_ADAPTER_CONTRACT_VERSION,
    SQLOracleAdapterContractError,
    SQLOracleAdapterStatus,
    SQLOracleAdapterCapability,
    SQLOracleAdapterConfig,
    SQLOracleAdapterExecutionRequest,
    SQLOracleAdapterExecutionResult,
    SQLOracleAdapterContract,
    default_oracle_stub_capability,
    validate_read_only_select,
)

EXPECTED_RESULT_KEYS = {
    "version", "case_id", "status", "sql_sha256",
    "rows", "row_count", "truncated", "error", "warnings", "duration_ms", "columns",
}

_CAPABILITY_FLAGS = (
    "supports_live_execution",
    "supports_driver_execution",
    "supports_network_execution",
    "supports_read_only_queries",
    "supports_local_docker_execution",
    "supports_remote_execution",
    "supports_production_execution",
    "supports_oracle_execution",
)


def _request(sql, *, case_id="c1", connection_ref=None):
    return SQLOracleAdapterExecutionRequest(
        case_id=case_id,
        sql=sql,
        dialect="oracle",
        config=SQLOracleAdapterConfig(),
        connection_ref=connection_ref,
    )


def _capability_kwargs(**overrides):
    kwargs = dict(
        version=SQL_ORACLE_ADAPTER_CONTRACT_VERSION,
        dialect="oracle",
        supports_live_execution=False,
        supports_driver_execution=False,
        supports_network_execution=False,
        supports_read_only_queries=False,
        supports_local_docker_execution=False,
        supports_remote_execution=False,
        supports_production_execution=False,
        supports_oracle_execution=False,
    )
    kwargs.update(overrides)
    return kwargs


def test_oracle_adapter_contract_version_is_stable():
    assert SQL_ORACLE_ADAPTER_CONTRACT_VERSION == "sql_oracle_adapter_contract_v1"


def test_oracle_adapter_capability_is_immutable():
    cap = default_oracle_stub_capability()
    with pytest.raises((FrozenInstanceError, AttributeError)):
        cap.version = "new_version"  # type: ignore


def test_oracle_adapter_capability_disables_all_execution_modes():
    cap = default_oracle_stub_capability()
    for flag in _CAPABILITY_FLAGS:
        assert getattr(cap, flag) is False, f"{flag} must be False in the Oracle stub"


@pytest.mark.parametrize("field_name", [
    "supports_live_execution",
    "supports_remote_execution",
    "supports_production_execution",
])
def test_oracle_adapter_capability_rejects_dangerous_flag_true(field_name):
    with pytest.raises(SQLOracleAdapterContractError):
        SQLOracleAdapterCapability(**_capability_kwargs(**{field_name: True}))


@pytest.mark.parametrize("field_name", [
    "supports_driver_execution",
    "supports_network_execution",
    "supports_read_only_queries",
    "supports_local_docker_execution",
    "supports_oracle_execution",
])
def test_oracle_adapter_capability_allows_local_docker_flag_true(field_name):
    cap = SQLOracleAdapterCapability(**_capability_kwargs(**{field_name: True}))
    assert getattr(cap, field_name) is True


def test_oracle_adapter_capability_rejects_live_execution_true():
    with pytest.raises(SQLOracleAdapterContractError):
        SQLOracleAdapterCapability(**_capability_kwargs(supports_live_execution=True))


def test_oracle_adapter_capability_rejects_wrong_dialect():
    with pytest.raises(SQLOracleAdapterContractError, match="oracle"):
        SQLOracleAdapterCapability(**_capability_kwargs(dialect="postgresql"))


def test_oracle_adapter_without_connection_is_not_implemented():
    adapter = SQLOracleAdapterContract()  # no connection path exists at all
    result = adapter.execute(_request("SELECT 1", case_id="case-100"))
    assert result.status == SQLOracleAdapterStatus.NOT_IMPLEMENTED
    assert result.sql_sha256 == hashlib.sha256(b"SELECT 1").hexdigest()
    assert result.rows == ()
    assert result.row_count == 0


@pytest.mark.parametrize("sql", [
    "INSERT INTO users (id) VALUES (1)",
    "UPDATE users SET name = 'x'",
    "DELETE FROM users",
    "DROP TABLE users",
    "ALTER TABLE users ADD (x NUMBER)",
    "CREATE TABLE x (id NUMBER)",
    "TRUNCATE TABLE users",
    "MERGE INTO users u USING dual ON (1=1) WHEN MATCHED THEN UPDATE SET u.x = 1",
    "BEGIN proc; END;",
    "CALL some_proc()",
    "SELECT * FROM users; DROP TABLE users;",
])
def test_oracle_adapter_rejects_unsafe_sql(sql):
    adapter = SQLOracleAdapterContract()
    result = adapter.execute(_request(sql))
    assert result.status == SQLOracleAdapterStatus.REJECTED
    assert result.rows == ()


def test_validate_read_only_select_allows_plain_select():
    assert validate_read_only_select("SELECT id, name FROM users") is None
    assert validate_read_only_select("  select 1  ") is None
    assert validate_read_only_select("SELECT 1;") is None  # single trailing semicolon ok


def test_oracle_adapter_result_shape_is_deterministic():
    adapter = SQLOracleAdapterContract()
    result = adapter.execute(_request("SELECT id FROM users"))
    serialized = result.to_dict()
    assert set(serialized.keys()) == EXPECTED_RESULT_KEYS
    assert serialized["version"] == SQL_ORACLE_ADAPTER_CONTRACT_VERSION
    assert serialized["status"] == "not_implemented"
    assert serialized["rows"] == []
    assert serialized["row_count"] == 0
    assert serialized["truncated"] is False
    # to_dict must be JSON-serializable
    json.dumps(serialized)


def test_oracle_adapter_result_does_not_leak_connection_ref_or_credentials():
    secret_ref = "jdbc:oracle:thin:scott/tiger@//db.prod.internal:1521/ORCLPDB1"
    raw_sql = "SELECT secret_salary FROM hr.employees"
    adapter = SQLOracleAdapterContract()
    result = adapter.execute(_request(raw_sql, connection_ref=secret_ref))
    serialized_str = json.dumps(result.to_dict())
    # No DSN / wallet / credential material.
    assert secret_ref not in serialized_str
    assert "tiger" not in serialized_str
    assert "db.prod.internal" not in serialized_str
    # Raw SQL must never be echoed; only its sha256 is carried.
    assert raw_sql not in serialized_str
    assert result.sql_sha256 == hashlib.sha256(raw_sql.encode("utf-8")).hexdigest()


def test_oracle_adapter_import_does_not_load_oracle_drivers():
    import subprocess
    import sys
    import app.evaluation
    eval_dir = os.path.dirname(app.evaluation.__file__)

    code = (
        "import sys\n"
        f"sys.path.insert(0, {repr(eval_dir)})\n"
        "import oracle_adapter\n"
        "forbidden = ['cx_Oracle', 'oracledb', 'sqlalchemy', 'jaydebeapi', 'jpype']\n"
        "for mod in forbidden:\n"
        "    if mod in sys.modules:\n"
        "        print(f'FORBIDDEN:{mod}')\n"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert "FORBIDDEN" not in res.stdout, f"Importing oracle_adapter loaded forbidden driver: {res.stdout}"


def test_oracle_adapter_import_does_not_load_socket_or_network_clients():
    import subprocess
    import sys
    import app.evaluation
    eval_dir = os.path.dirname(app.evaluation.__file__)

    code = (
        "import sys\n"
        f"sys.path.insert(0, {repr(eval_dir)})\n"
        "import oracle_adapter\n"
        "forbidden = ['socket', 'requests', 'urllib', 'http.client', 'asyncio']\n"
        "for mod in forbidden:\n"
        "    if mod in sys.modules:\n"
        "        print(f'FORBIDDEN:{mod}')\n"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert "FORBIDDEN" not in res.stdout, f"Importing oracle_adapter loaded network client: {res.stdout}"


def test_oracle_adapter_does_not_read_env_or_secret_manager(monkeypatch):
    def _forbidden(*args, **kwargs):
        raise AssertionError("Oracle adapter must not read env vars / secret manager")

    monkeypatch.setattr(os, "getenv", _forbidden)
    monkeypatch.setattr(os.environ, "get", _forbidden)

    adapter = SQLOracleAdapterContract()
    result = adapter.execute(_request("SELECT 1"))
    assert result.status == SQLOracleAdapterStatus.NOT_IMPLEMENTED


def test_oracle_adapter_contract_rejects_unsafe_custom_capability():
    with pytest.raises(SQLOracleAdapterContractError, match="capability must be a SQLOracleAdapterCapability"):
        SQLOracleAdapterContract(capability="not-a-capability-obj")  # type: ignore


def test_oracle_adapter_execute_rejects_non_request_object():
    adapter = SQLOracleAdapterContract()
    with pytest.raises(SQLOracleAdapterContractError, match="request must be a SQLOracleAdapterExecutionRequest"):
        adapter.execute("SELECT 1")  # type: ignore


def test_oracle_adapter_rejection_path_opens_no_socket(monkeypatch):
    def _forbidden_socket(*args, **kwargs):
        raise RuntimeError("network access is forbidden on the rejection path")
    monkeypatch.setattr(socket, "socket", _forbidden_socket)

    adapter = SQLOracleAdapterContract()
    result = adapter.execute(_request("DELETE FROM users"))
    assert result.status == SQLOracleAdapterStatus.REJECTED


def test_default_local_docker_capability_flags():
    from app.evaluation.oracle_adapter import default_local_docker_capability
    cap = default_local_docker_capability()
    assert cap.supports_live_execution is False
    assert cap.supports_remote_execution is False
    assert cap.supports_production_execution is False
    assert cap.supports_driver_execution is True
    assert cap.supports_network_execution is True
    assert cap.supports_read_only_queries is True
    assert cap.supports_local_docker_execution is True
    assert cap.supports_oracle_execution is True


def test_local_docker_connection_accepts_local_host():
    from app.evaluation.oracle_adapter import SQLOracleLocalDockerConnection
    conn = SQLOracleLocalDockerConnection(
        host="localhost", port=1521, service_name="FREEPDB1", user="u", password="p"
    )
    assert conn.service_name == "FREEPDB1"


def test_local_docker_connection_rejects_remote_host():
    import pytest
    from app.evaluation.oracle_adapter import (
        SQLOracleLocalDockerConnection, SQLOracleAdapterContractError,
    )
    with pytest.raises(SQLOracleAdapterContractError):
        SQLOracleLocalDockerConnection(
            host="db.prod.example.com", port=1521, service_name="P", user="u"
        )


def test_local_docker_connection_rejects_bad_port_and_empty_service():
    import pytest
    from app.evaluation.oracle_adapter import (
        SQLOracleLocalDockerConnection, SQLOracleAdapterContractError,
    )
    with pytest.raises(SQLOracleAdapterContractError):
        SQLOracleLocalDockerConnection(host="localhost", port=0, service_name="S", user="u")
    with pytest.raises(SQLOracleAdapterContractError):
        SQLOracleLocalDockerConnection(host="localhost", port=1521, service_name="", user="u")


def test_oracle_execution_result_columns_default_and_roundtrip():
    import hashlib, pytest
    from app.evaluation.oracle_adapter import (
        SQLOracleAdapterExecutionResult, SQL_ORACLE_ADAPTER_CONTRACT_VERSION,
        SQLOracleAdapterStatus, SQLOracleAdapterContractError,
    )
    h = hashlib.sha256(b"SELECT 1 FROM DUAL").hexdigest()
    res = SQLOracleAdapterExecutionResult(
        version=SQL_ORACLE_ADAPTER_CONTRACT_VERSION, case_id="c1",
        status=SQLOracleAdapterStatus.EXECUTED, sql_sha256=h,
        rows=((1,),), row_count=1, columns=("N",),
    )
    assert res.columns == ("N",)
    assert res.to_dict()["columns"] == ["N"]
    with pytest.raises(SQLOracleAdapterContractError):
        SQLOracleAdapterExecutionResult(
            version=SQL_ORACLE_ADAPTER_CONTRACT_VERSION, case_id="c1",
            status=SQLOracleAdapterStatus.EXECUTED, sql_sha256=h, columns=("N", 5),
        )


def test_status_has_executed_and_execution_error():
    from app.evaluation.oracle_adapter import SQLOracleAdapterStatus
    assert SQLOracleAdapterStatus.EXECUTED.value == "executed"
    assert SQLOracleAdapterStatus.EXECUTION_ERROR.value == "execution_error"


def _install_fake_oracledb(monkeypatch, captured, rows, description, raise_exc=None):
    import sys, types

    class _FakeCursor:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def execute(self, sql):
            captured.append(sql)
            if raise_exc is not None and sql != "SET TRANSACTION READ ONLY":
                raise raise_exc
        def fetchmany(self, n):
            return list(rows)[:n]
        @property
        def description(self):
            return description

    class _FakeConn:
        def __init__(self):
            self.autocommit = None
            self.call_timeout = None
            self.rolled_back = False
            self.closed = False
        def cursor(self):
            return _FakeCursor()
        def rollback(self):
            self.rolled_back = True
        def close(self):
            self.closed = True

    holder = {}
    def _connect(**kw):
        holder["conn"] = _FakeConn()
        holder["connect_kwargs"] = kw
        return holder["conn"]

    fake = types.ModuleType("oracledb")
    fake.connect = _connect
    monkeypatch.setitem(sys.modules, "oracledb", fake)
    return holder


def _oracle_local_conn():
    from app.evaluation.oracle_adapter import SQLOracleLocalDockerConnection
    return SQLOracleLocalDockerConnection(
        host="localhost", port=1521, service_name="FREEPDB1", user="u", password="p"
    )


def _read_only_request(sql, timeout=2.0, max_rows=1000):
    from app.evaluation.oracle_adapter import (
        SQLOracleAdapterConfig, SQLOracleAdapterExecutionRequest,
    )
    return SQLOracleAdapterExecutionRequest(
        case_id="c1", sql=sql, dialect="oracle",
        config=SQLOracleAdapterConfig(timeout_seconds=timeout, max_rows=max_rows),
    )


def test_execute_read_only_sets_transaction_read_only_then_runs_sql(monkeypatch):
    from app.evaluation.oracle_adapter import (
        SQLOracleAdapterContract, SQLOracleAdapterStatus,
    )
    captured = []
    holder = _install_fake_oracledb(
        monkeypatch, captured,
        rows=[(1,)], description=[("N", None, None, None, None, None, None)],
    )
    res = SQLOracleAdapterContract(connection=_oracle_local_conn()).execute(
        _read_only_request("SELECT 1 AS n FROM DUAL")
    )
    assert captured == ["SET TRANSACTION READ ONLY", "SELECT 1 AS n FROM DUAL"]
    assert res.status == SQLOracleAdapterStatus.EXECUTED
    assert res.columns == ("N",)
    assert res.rows == ((1,),)
    assert holder["conn"].autocommit is False
    assert holder["conn"].call_timeout == 2000
    assert holder["conn"].rolled_back is True
    assert holder["conn"].closed is True


def test_execute_truncates_to_max_rows(monkeypatch):
    from app.evaluation.oracle_adapter import (
        SQLOracleAdapterContract, SQLOracleAdapterStatus,
    )
    captured = []
    _install_fake_oracledb(
        monkeypatch, captured,
        rows=[(1,), (2,), (3,)], description=[("LVL", None, None, None, None, None, None)],
    )
    res = SQLOracleAdapterContract(connection=_oracle_local_conn()).execute(
        _read_only_request("SELECT LEVEL AS lvl FROM DUAL CONNECT BY LEVEL <= 3", max_rows=2)
    )
    assert res.status == SQLOracleAdapterStatus.EXECUTED
    assert res.truncated is True
    assert res.row_count == 2
    assert "result truncated to max_rows" in res.warnings


def test_execute_driver_error_returns_execution_error(monkeypatch):
    from app.evaluation.oracle_adapter import (
        SQLOracleAdapterContract, SQLOracleAdapterStatus,
    )
    captured = []
    boom = RuntimeError("ORA-00942: table or view does not exist; user=secret")
    _install_fake_oracledb(
        monkeypatch, captured, rows=[], description=None, raise_exc=boom,
    )
    res = SQLOracleAdapterContract(connection=_oracle_local_conn()).execute(
        _read_only_request("SELECT * FROM missing")
    )
    assert res.status == SQLOracleAdapterStatus.EXECUTION_ERROR
    assert "secret" not in (res.error or "")
    assert "ORA-00942" not in (res.error or "")


def test_execute_timeout_error_maps_to_timeout_message(monkeypatch):
    from app.evaluation.oracle_adapter import (
        SQLOracleAdapterContract, SQLOracleAdapterStatus,
    )
    class _Err:
        full_code = "DPY-4024"
    class _Timeout(Exception):
        def __init__(self):
            super().__init__("DPY-4024: call timeout of 50 ms exceeded")
            self.args = (_Err(),)
    captured = []
    _install_fake_oracledb(monkeypatch, captured, rows=[], description=None, raise_exc=_Timeout())
    res = SQLOracleAdapterContract(connection=_oracle_local_conn()).execute(
        _read_only_request("SELECT 1 FROM DUAL", timeout=0.05)
    )
    assert res.status == SQLOracleAdapterStatus.EXECUTION_ERROR
    assert "timed out" in (res.error or "").lower()


def test_execute_rejects_write_before_touching_driver(monkeypatch):
    from app.evaluation.oracle_adapter import (
        SQLOracleAdapterContract, SQLOracleAdapterStatus,
    )
    captured = []
    _install_fake_oracledb(monkeypatch, captured, rows=[], description=None)
    res = SQLOracleAdapterContract(connection=_oracle_local_conn()).execute(
        _read_only_request("DELETE FROM customers")
    )
    assert res.status == SQLOracleAdapterStatus.REJECTED
    assert captured == []  # never reached the driver


def test_execute_no_connection_is_inert_not_implemented():
    from app.evaluation.oracle_adapter import (
        SQLOracleAdapterContract, SQLOracleAdapterStatus,
    )
    res = SQLOracleAdapterContract().execute(_read_only_request("SELECT 1 FROM DUAL"))
    assert res.status == SQLOracleAdapterStatus.NOT_IMPLEMENTED


def test_oracle_adapter_import_does_not_load_db_drivers():
    import os, subprocess, sys
    import app.evaluation
    eval_dir = os.path.dirname(app.evaluation.__file__)
    code = (
        "import sys\n"
        f"sys.path.insert(0, {repr(eval_dir)})\n"
        "import oracle_adapter\n"
        "forbidden = ['oracledb', 'cx_Oracle', 'sqlalchemy']\n"
        "for mod in forbidden:\n"
        "    if mod in sys.modules:\n"
        "        print(f'FORBIDDEN:{mod}')\n"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert "FORBIDDEN" not in res.stdout, res.stdout
