import hashlib
import pytest

from app.evaluation.multi_database_execution import (
    SQLDatabaseDialect, SQLExecutionMode, SQLExecutionAdapterCapability,
    SQLDatabaseExecutionConfig, SQLDatabaseExecutionRequest,
    SQLMultiDatabaseExecutionContractError, SQLDatabaseExecutionRouter,
)
from app.evaluation.oracle_execution_adapter import (
    OracleDatabaseExecutionAdapter, normalize_oracle_execution_result, _rows_to_dicts,
)
from app.evaluation.oracle_adapter import (
    SQLOracleAdapterExecutionResult, SQL_ORACLE_ADAPTER_CONTRACT_VERSION,
    SQLOracleAdapterStatus,
)


def _request(sql, mode=SQLExecutionMode.READ_ONLY):
    cfg = SQLDatabaseExecutionConfig(
        dialect=SQLDatabaseDialect.ORACLE, timeout_seconds=2.0, max_rows=1000,
        execution_mode=mode,
    )
    return SQLDatabaseExecutionRequest(
        case_id="c1", sql=sql, dialect=SQLDatabaseDialect.ORACLE,
        fixture_ref=None, connection_ref="local_docker", config=cfg,
    )


def test_capabilities_are_connection_ref_and_read_only():
    caps = OracleDatabaseExecutionAdapter().capabilities()
    assert SQLExecutionAdapterCapability.CONNECTION_REF in caps
    assert SQLExecutionAdapterCapability.READ_ONLY in caps
    assert SQLExecutionAdapterCapability.EXPLAIN_ONLY not in caps


def test_dialect_is_oracle():
    assert OracleDatabaseExecutionAdapter().dialect == SQLDatabaseDialect.ORACLE


def test_no_connection_returns_graceful_empty_result():
    adapter = OracleDatabaseExecutionAdapter(connection_resolver=lambda env=None: None)
    res = adapter.execute(_request("SELECT 1 FROM DUAL"))
    assert res.rows == ()
    assert res.execution_error == "No local Docker Oracle connection available"
    assert res.sql_sha256 == hashlib.sha256(b"SELECT 1 FROM DUAL").hexdigest()


def test_explain_only_mode_is_rejected():
    adapter = OracleDatabaseExecutionAdapter(connection_resolver=lambda env=None: None)
    with pytest.raises(SQLMultiDatabaseExecutionContractError):
        adapter.execute(_request("SELECT 1 FROM DUAL", mode=SQLExecutionMode.EXPLAIN_ONLY))


def test_fixture_ref_is_rejected():
    cfg = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.ORACLE)
    req = SQLDatabaseExecutionRequest(
        case_id="c1", sql="SELECT 1 FROM DUAL", dialect=SQLDatabaseDialect.ORACLE,
        fixture_ref="f", connection_ref=None, config=cfg,
    )
    adapter = OracleDatabaseExecutionAdapter(connection_resolver=lambda env=None: None)
    with pytest.raises(SQLMultiDatabaseExecutionContractError):
        adapter.execute(req)


def test_normalize_builds_named_dict_rows():
    h = hashlib.sha256(b"SELECT a, b FROM t").hexdigest()
    oracle = SQLOracleAdapterExecutionResult(
        version=SQL_ORACLE_ADAPTER_CONTRACT_VERSION, case_id="c1",
        status=SQLOracleAdapterStatus.EXECUTED, sql_sha256=h,
        rows=((1, "x"),), row_count=1, columns=("A", "B"),
    )
    out = normalize_oracle_execution_result(oracle, _request("SELECT a, b FROM t"))
    assert out.rows == ({"A": 1, "B": "x"},)


def test_rows_to_dicts_arity_mismatch_falls_back_to_positional():
    dict_rows, warnings = _rows_to_dicts(((1, 2, 3),), ("A", "B"))
    assert dict_rows == ({"col_0": 1, "col_1": 2, "col_2": 3},)
    assert warnings  # non-empty warning


def test_adapter_plugs_into_router():
    router = SQLDatabaseExecutionRouter(adapters=(OracleDatabaseExecutionAdapter(),))
    assert router.get_adapter(SQLDatabaseDialect.ORACLE).dialect == SQLDatabaseDialect.ORACLE


def test_execution_adapter_import_does_not_load_db_drivers():
    import os, subprocess, sys
    import app.evaluation
    eval_dir = os.path.dirname(app.evaluation.__file__)
    code = (
        "import sys\n"
        f"sys.path.insert(0, {repr(eval_dir)})\n"
        "import oracle_execution_adapter\n"
        "forbidden = ['oracledb', 'cx_Oracle', 'sqlalchemy']\n"
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
