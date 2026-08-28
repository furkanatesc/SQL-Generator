import socket, sys, types
import pytest
from app.evaluation.mssql_adapter import (
    SQL_MSSQL_ADAPTER_CONTRACT_VERSION, SQLMSSQLAdapterContract,
    SQLMSSQLAdapterStatus, SQLMSSQLLocalDockerConnection,
    SQLMSSQLAdapterConfig, SQLMSSQLAdapterExecutionRequest,
    default_mssql_stub_capability, default_local_docker_capability,
)


def _install_fake_pymssql(monkeypatch, captured, rows, description, raise_exc=None):
    class _FakeCursor:
        def execute(self, sql):
            captured.append(sql)
            if raise_exc is not None:
                raise raise_exc
        def fetchmany(self, n): return list(rows)[:n]
        def close(self): pass
        @property
        def description(self): return description
    class _FakeConn:
        def __init__(self): self.rolled_back = False; self.closed = False
        def cursor(self): return _FakeCursor()
        def rollback(self): self.rolled_back = True
        def close(self): self.closed = True
    holder = {}
    def _connect(**kw):
        holder["conn"] = _FakeConn(); holder["connect_kwargs"] = kw; return holder["conn"]
    fake = types.ModuleType("pymssql")
    fake.connect = _connect
    monkeypatch.setitem(sys.modules, "pymssql", fake)
    return holder


def _local_conn():
    return SQLMSSQLLocalDockerConnection(host="localhost", port=1433, database="sqlgen_test", user="sqlgen_ro", password="p")


def _read_only_request(sql, timeout=3.0, max_rows=1000):
    return SQLMSSQLAdapterExecutionRequest(
        case_id="c1", sql=sql, dialect="sqlserver",
        config=SQLMSSQLAdapterConfig(timeout_seconds=timeout, max_rows=max_rows),
    )


def test_execute_runs_select_with_query_timeout_and_rolls_back(monkeypatch):
    captured = []
    holder = _install_fake_pymssql(monkeypatch, captured, rows=[(1,)], description=[("n", None, None, None, None, None, None)])
    res = SQLMSSQLAdapterContract(connection=_local_conn()).execute(_read_only_request("SELECT 1 AS n", timeout=3.0))
    assert res.status == SQLMSSQLAdapterStatus.EXECUTED
    assert res.columns == ("n",)
    assert res.rows == ((1,),)
    # No pre-statements: read-only is enforced by the db_datareader login, not a tx statement.
    assert captured == ["SELECT 1 AS n"]
    assert holder["connect_kwargs"]["timeout"] == 3      # query timeout applied at connect
    assert holder["conn"].rolled_back is True            # always rollback
    assert holder["conn"].closed is True


def test_execute_truncates_to_max_rows(monkeypatch):
    _install_fake_pymssql(monkeypatch, [], rows=[(1,), (2,), (3,)], description=[("n", None, None, None, None, None, None)])
    res = SQLMSSQLAdapterContract(connection=_local_conn()).execute(_read_only_request("SELECT n FROM t", max_rows=2))
    assert res.truncated is True
    assert res.row_count == 2


def test_execute_driver_error_returns_execution_error(monkeypatch):
    _install_fake_pymssql(monkeypatch, [], rows=[], description=None, raise_exc=RuntimeError("boom"))
    res = SQLMSSQLAdapterContract(connection=_local_conn()).execute(_read_only_request("SELECT 1"))
    assert res.status == SQLMSSQLAdapterStatus.EXECUTION_ERROR
    assert "boom" not in (res.error or "")


def test_execute_rejects_write_before_touching_driver(monkeypatch):
    captured = []
    _install_fake_pymssql(monkeypatch, captured, rows=[], description=None)
    res = SQLMSSQLAdapterContract(connection=_local_conn()).execute(_read_only_request("UPDATE t SET x=1"))
    assert res.status == SQLMSSQLAdapterStatus.REJECTED
    assert captured == []


def test_execute_no_connection_is_inert_not_implemented():
    res = SQLMSSQLAdapterContract().execute(_read_only_request("SELECT 1"))
    assert res.status == SQLMSSQLAdapterStatus.NOT_IMPLEMENTED


def test_capability_cannot_enable_live_remote_production():
    cap = default_local_docker_capability()
    assert cap.supports_live_execution is False
    assert cap.supports_remote_execution is False
    assert cap.supports_production_execution is False
    assert cap.supports_mssql_execution is True


def test_stub_capability_is_all_false():
    cap = default_mssql_stub_capability()
    assert cap.supports_mssql_execution is False
    assert cap.supports_local_docker_execution is False


def test_connection_rejects_remote_host():
    from app.evaluation.mssql_adapter import SQLMSSQLAdapterContractError
    with pytest.raises(SQLMSSQLAdapterContractError):
        SQLMSSQLLocalDockerConnection(host="db.prod.example.com", port=1433, database="d", user="u", password="p")


def test_adapter_import_does_not_load_db_drivers():
    import os, subprocess
    import app.evaluation
    eval_dir = os.path.dirname(app.evaluation.__file__)
    code = (
        "import sys\n"
        f"sys.path.insert(0, {repr(eval_dir)})\n"
        "import mssql_adapter\n"
        "for mod in ['pymssql', '_mssql', 'sqlalchemy', 'pyodbc']:\n"
        "    if mod in sys.modules:\n"
        "        print(f'FORBIDDEN:{mod}')\n"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert "FORBIDDEN" not in res.stdout, res.stdout


def test_rejection_path_opens_no_socket(monkeypatch):
    def _forbidden(*a, **k): raise AssertionError("socket opened on rejection path")
    monkeypatch.setattr(socket, "socket", _forbidden)
    res = SQLMSSQLAdapterContract(connection=_local_conn()).execute(_read_only_request("DROP TABLE t"))
    assert res.status == SQLMSSQLAdapterStatus.REJECTED
