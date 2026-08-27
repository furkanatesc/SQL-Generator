import hashlib
import pytest

from app.evaluation.multi_database_execution import (
    SQLDatabaseDialect, SQLExecutionMode, SQLExecutionAdapterCapability,
    SQLDatabaseExecutionConfig, SQLDatabaseExecutionRequest,
    SQLMultiDatabaseExecutionContractError, SQLDatabaseExecutionRouter,
)
from app.evaluation.mysql_execution_adapter import (
    MySQLDatabaseExecutionAdapter, normalize_mysql_execution_result, _rows_to_dicts,
)
from app.evaluation.mysql_adapter import (
    SQLMySQLAdapterExecutionResult, SQL_MYSQL_ADAPTER_CONTRACT_VERSION,
    SQLMySQLAdapterStatus,
)


def _request(sql, mode=SQLExecutionMode.READ_ONLY):
    cfg = SQLDatabaseExecutionConfig(
        dialect=SQLDatabaseDialect.MYSQL, timeout_seconds=2.0, max_rows=1000,
        execution_mode=mode,
    )
    return SQLDatabaseExecutionRequest(
        case_id="c1", sql=sql, dialect=SQLDatabaseDialect.MYSQL,
        fixture_ref=None, connection_ref="local_docker", config=cfg,
    )


def test_capabilities_are_connection_ref_and_read_only():
    caps = MySQLDatabaseExecutionAdapter().capabilities()
    assert SQLExecutionAdapterCapability.CONNECTION_REF in caps
    assert SQLExecutionAdapterCapability.READ_ONLY in caps
    assert SQLExecutionAdapterCapability.EXPLAIN_ONLY not in caps


def test_dialect_is_mysql():
    assert MySQLDatabaseExecutionAdapter().dialect == SQLDatabaseDialect.MYSQL


def test_no_connection_returns_graceful_empty_result():
    adapter = MySQLDatabaseExecutionAdapter(connection_resolver=lambda env=None: None)
    res = adapter.execute(_request("SELECT 1"))
    assert res.rows == ()
    assert res.execution_error == "No local Docker MySQL connection available"
    assert res.sql_sha256 == hashlib.sha256(b"SELECT 1").hexdigest()


def test_explain_only_mode_is_rejected():
    adapter = MySQLDatabaseExecutionAdapter(connection_resolver=lambda env=None: None)
    with pytest.raises(SQLMultiDatabaseExecutionContractError):
        adapter.execute(_request("SELECT 1", mode=SQLExecutionMode.EXPLAIN_ONLY))


def test_fixture_ref_is_rejected():
    cfg = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.MYSQL)
    req = SQLDatabaseExecutionRequest(
        case_id="c1", sql="SELECT 1", dialect=SQLDatabaseDialect.MYSQL,
        fixture_ref="f", connection_ref=None, config=cfg,
    )
    adapter = MySQLDatabaseExecutionAdapter(connection_resolver=lambda env=None: None)
    with pytest.raises(SQLMultiDatabaseExecutionContractError):
        adapter.execute(req)


def test_normalize_builds_named_dict_rows():
    h = hashlib.sha256(b"SELECT a, b FROM t").hexdigest()
    mysql = SQLMySQLAdapterExecutionResult(
        version=SQL_MYSQL_ADAPTER_CONTRACT_VERSION, case_id="c1",
        status=SQLMySQLAdapterStatus.EXECUTED, sql_sha256=h,
        rows=((1, "x"),), row_count=1, columns=("a", "b"),
    )
    out = normalize_mysql_execution_result(mysql, _request("SELECT a, b FROM t"))
    assert out.rows == ({"a": 1, "b": "x"},)


def test_rows_to_dicts_arity_mismatch_falls_back_to_positional():
    dict_rows, warnings = _rows_to_dicts(((1, 2, 3),), ("a", "b"))
    assert dict_rows == ({"col_0": 1, "col_1": 2, "col_2": 3},)
    assert warnings  # non-empty warning


def test_adapter_plugs_into_router():
    router = SQLDatabaseExecutionRouter(adapters=(MySQLDatabaseExecutionAdapter(),))
    assert router.get_adapter(SQLDatabaseDialect.MYSQL).dialect == SQLDatabaseDialect.MYSQL


def test_execution_adapter_import_does_not_load_db_drivers():
    import os, subprocess, sys
    import app.evaluation
    eval_dir = os.path.dirname(app.evaluation.__file__)
    code = (
        "import sys\n"
        f"sys.path.insert(0, {repr(eval_dir)})\n"
        "import mysql_execution_adapter\n"
        "forbidden = ['pymysql', 'MySQLdb', 'sqlalchemy']\n"
        "for mod in forbidden:\n"
        "    if mod in sys.modules:\n"
        "        print(f'FORBIDDEN:{mod}')\n"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert "FORBIDDEN" not in res.stdout, res.stdout
    # NOTE: the network-client forbidden-list (socket/asyncio/...) is deliberately
    # NOT ported here — the eval package's eager re-exports pull pydantic, which
    # incidentally references asyncio/socket (no real I/O), a known false positive
    # documented for the PostgreSQL execution adapter.


def test_execute_with_resolved_connection_delegates_to_low_level(monkeypatch):
    # Exercise the resolver-non-None branch end to end without Docker.
    import sys, types
    from app.evaluation.mysql_adapter import SQLMySQLLocalDockerConnection

    captured = []

    class _FakeCursor:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql): captured.append(sql)
        def fetchmany(self, n): return [(1, "x")][:n]
        @property
        def description(self):
            return [("a", None, None, None, None, None, None),
                    ("b", None, None, None, None, None, None)]

    class _FakeConn:
        def cursor(self): return _FakeCursor()
        def rollback(self): pass
        def close(self): pass

    fake = types.ModuleType("pymysql")
    fake.connect = lambda **kw: _FakeConn()
    monkeypatch.setitem(sys.modules, "pymysql", fake)

    conn = SQLMySQLLocalDockerConnection(host="localhost", port=3306, database="d", user="u", password="p")
    adapter = MySQLDatabaseExecutionAdapter(connection_resolver=lambda: conn)
    res = adapter.execute(_request("SELECT a, b FROM t"))

    assert res.execution_error is None
    assert res.rows == ({"a": 1, "b": "x"},)   # lowercase keys — MySQL preserves case
    assert res.row_count == 1
    assert "SELECT a, b FROM t" in captured
    assert any(s == "START TRANSACTION READ ONLY" for s in captured)
