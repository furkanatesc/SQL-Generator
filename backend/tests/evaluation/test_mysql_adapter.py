import hashlib, re, socket, sys, types
import pytest
from app.evaluation.mysql_adapter import (
    SQL_MYSQL_ADAPTER_CONTRACT_VERSION, SQLMySQLAdapterContract,
    SQLMySQLAdapterStatus, SQLMySQLLocalDockerConnection,
    SQLMySQLAdapterConfig, SQLMySQLAdapterExecutionRequest,
    default_mysql_stub_capability, default_local_docker_capability,
)


def _install_fake_pymysql(monkeypatch, captured, rows, description, raise_exc=None):
    class _FakeCursor:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql):
            captured.append(sql)
            if raise_exc is not None and sql not in ("START TRANSACTION READ ONLY",) and not sql.startswith("SET SESSION max_execution_time"):
                raise raise_exc
        def fetchmany(self, n): return list(rows)[:n]
        @property
        def description(self): return description
    class _FakeConn:
        def __init__(self): self.autocommit_flag=None; self.rolled_back=False; self.closed=False
        def cursor(self): return _FakeCursor()
        def rollback(self): self.rolled_back=True
        def close(self): self.closed=True
    holder = {}
    def _connect(**kw):
        holder["conn"]=_FakeConn(); holder["connect_kwargs"]=kw; return holder["conn"]
    fake = types.ModuleType("pymysql")
    fake.connect = _connect
    monkeypatch.setitem(sys.modules, "pymysql", fake)
    return holder


def _local_conn():
    return SQLMySQLLocalDockerConnection(host="localhost", port=3306, database="sqlgen_test", user="u", password="p")


def _read_only_request(sql, timeout=2.0, max_rows=1000):
    return SQLMySQLAdapterExecutionRequest(
        case_id="c1", sql=sql, dialect="mysql",
        config=SQLMySQLAdapterConfig(timeout_seconds=timeout, max_rows=max_rows),
    )


def test_execute_sets_max_execution_time_and_read_only_tx_before_sql(monkeypatch):
    captured = []
    _install_fake_pymysql(monkeypatch, captured, rows=[(1,)], description=[("n", None, None, None, None, None, None)])
    res = SQLMySQLAdapterContract(connection=_local_conn()).execute(_read_only_request("SELECT 1 AS n"))
    assert res.status == SQLMySQLAdapterStatus.EXECUTED
    assert res.columns == ("n",)
    assert res.rows == ((1,),)
    # max_execution_time set, then read-only tx, then the SELECT — in that order
    assert captured[0].startswith("SET SESSION max_execution_time")
    assert captured[1] == "START TRANSACTION READ ONLY"
    assert captured[2] == "SELECT 1 AS n"


def test_execute_truncates_to_max_rows(monkeypatch):
    captured = []
    _install_fake_pymysql(monkeypatch, captured, rows=[(1,), (2,), (3,)], description=[("n", None, None, None, None, None, None)])
    res = SQLMySQLAdapterContract(connection=_local_conn()).execute(_read_only_request("SELECT n FROM t", max_rows=2))
    assert res.truncated is True
    assert res.row_count == 2


def test_execute_driver_error_returns_execution_error(monkeypatch):
    captured = []
    _install_fake_pymysql(monkeypatch, captured, rows=[], description=None, raise_exc=RuntimeError("boom"))
    res = SQLMySQLAdapterContract(connection=_local_conn()).execute(_read_only_request("SELECT 1"))
    assert res.status == SQLMySQLAdapterStatus.EXECUTION_ERROR
    assert "boom" not in (res.error or "")  # sanitized, no leak


def test_execute_rejects_write_before_touching_driver(monkeypatch):
    captured = []
    _install_fake_pymysql(monkeypatch, captured, rows=[], description=None)
    res = SQLMySQLAdapterContract(connection=_local_conn()).execute(_read_only_request("UPDATE t SET x=1"))
    assert res.status == SQLMySQLAdapterStatus.REJECTED
    assert captured == []  # never touched the driver


def test_execute_no_connection_is_inert_not_implemented():
    res = SQLMySQLAdapterContract().execute(_read_only_request("SELECT 1"))
    assert res.status == SQLMySQLAdapterStatus.NOT_IMPLEMENTED


def test_capability_cannot_enable_live_remote_production():
    cap = default_local_docker_capability()
    assert cap.supports_live_execution is False
    assert cap.supports_remote_execution is False
    assert cap.supports_production_execution is False
    assert cap.supports_mysql_execution is True


def test_stub_capability_is_all_false():
    cap = default_mysql_stub_capability()
    assert cap.supports_mysql_execution is False
    assert cap.supports_local_docker_execution is False


def test_connection_rejects_remote_host():
    import pytest as _pt
    from app.evaluation.mysql_adapter import SQLMySQLAdapterContractError
    with _pt.raises(SQLMySQLAdapterContractError):
        SQLMySQLLocalDockerConnection(host="db.prod.example.com", port=3306, database="d", user="u", password="p")


def test_adapter_import_does_not_load_db_drivers():
    import os, subprocess
    import app.evaluation
    eval_dir = os.path.dirname(app.evaluation.__file__)
    code = (
        "import sys\n"
        f"sys.path.insert(0, {repr(eval_dir)})\n"
        "import mysql_adapter\n"
        "for mod in ['pymysql', 'mysqlclient', 'MySQLdb', 'sqlalchemy']:\n"
        "    if mod in sys.modules:\n"
        "        print(f'FORBIDDEN:{mod}')\n"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert "FORBIDDEN" not in res.stdout, res.stdout


def test_rejection_path_opens_no_socket(monkeypatch):
    def _forbidden(*a, **k): raise AssertionError("socket opened on rejection path")
    monkeypatch.setattr(socket, "socket", _forbidden)
    res = SQLMySQLAdapterContract(connection=_local_conn()).execute(_read_only_request("DROP TABLE t"))
    assert res.status == SQLMySQLAdapterStatus.REJECTED
