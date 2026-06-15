from dataclasses import FrozenInstanceError
import pytest
import sqlite3

from app.evaluation.multi_database_execution import (
    SQL_MULTI_DATABASE_EXECUTION_VERSION,
    SQLDatabaseDialect,
    SQLExecutionMode,
    SQLExecutionAdapterCapability,
    SQLDatabaseExecutionConfig,
    SQLDatabaseExecutionRequest,
    SQLDatabaseExecutionResult,
    SQLiteDatabaseExecutionAdapter,
    SQLDatabaseExecutionRouter,
    SQLMultiDatabaseExecutionContractError,
)


def test_multi_database_execution_version_is_v1():
    assert SQL_MULTI_DATABASE_EXECUTION_VERSION == "sql_multi_database_execution_v1"


def test_database_execution_config_is_frozen():
    config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE)
    with pytest.raises(FrozenInstanceError):
        config.timeout_seconds = 5.0  # type: ignore


def test_database_execution_config_rejects_invalid_timeout():
    with pytest.raises(SQLMultiDatabaseExecutionContractError):
        SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE, timeout_seconds=0.0)

    with pytest.raises(SQLMultiDatabaseExecutionContractError):
        SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE, timeout_seconds=-1.0)

    with pytest.raises(SQLMultiDatabaseExecutionContractError):
        SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE, timeout_seconds=True)  # type: ignore

    with pytest.raises(SQLMultiDatabaseExecutionContractError):
        SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE, timeout_seconds="invalid")  # type: ignore


def test_database_execution_config_rejects_invalid_max_rows():
    with pytest.raises(SQLMultiDatabaseExecutionContractError):
        SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE, max_rows=0)

    with pytest.raises(SQLMultiDatabaseExecutionContractError):
        SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE, max_rows=-10)

    with pytest.raises(SQLMultiDatabaseExecutionContractError):
        SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE, max_rows=True)  # type: ignore

    with pytest.raises(SQLMultiDatabaseExecutionContractError):
        SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE, max_rows="invalid")  # type: ignore


def test_database_execution_request_rejects_empty_sql():
    config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE)
    with pytest.raises(SQLMultiDatabaseExecutionContractError):
        SQLDatabaseExecutionRequest(
            case_id="case_001",
            sql="",
            dialect=SQLDatabaseDialect.SQLITE,
            fixture_ref="fixture",
            connection_ref=None,
            config=config
        )


def test_database_execution_request_rejects_empty_case_id():
    config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE)
    with pytest.raises(SQLMultiDatabaseExecutionContractError):
        SQLDatabaseExecutionRequest(
            case_id="",
            sql="SELECT 1",
            dialect=SQLDatabaseDialect.SQLITE,
            fixture_ref="fixture",
            connection_ref=None,
            config=config
        )


def test_database_execution_request_rejects_mismatched_config_dialect():
    config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE)
    with pytest.raises(SQLMultiDatabaseExecutionContractError):
        SQLDatabaseExecutionRequest(
            case_id="case_001",
            sql="SELECT 1",
            dialect=SQLDatabaseDialect.POSTGRESQL,
            fixture_ref="fixture",
            connection_ref=None,
            config=config
        )


def test_database_execution_request_rejects_both_fixture_and_connection_ref():
    config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE)
    with pytest.raises(SQLMultiDatabaseExecutionContractError):
        SQLDatabaseExecutionRequest(
            case_id="case_001",
            sql="SELECT 1",
            dialect=SQLDatabaseDialect.SQLITE,
            fixture_ref="fixture",
            connection_ref="conn_001",
            config=config
        )


def test_database_execution_request_requires_fixture_or_connection_ref():
    config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE)
    with pytest.raises(SQLMultiDatabaseExecutionContractError):
        SQLDatabaseExecutionRequest(
            case_id="case_001",
            sql="SELECT 1",
            dialect=SQLDatabaseDialect.SQLITE,
            fixture_ref=None,
            connection_ref=None,
            config=config
        )


def test_database_execution_result_is_frozen():
    result = SQLDatabaseExecutionResult(
        version=SQL_MULTI_DATABASE_EXECUTION_VERSION,
        case_id="case_001",
        dialect=SQLDatabaseDialect.SQLITE,
        sql="SELECT 1",
        sql_sha256="abc",
        rows=(),
        row_count=0,
        truncated=False,
        execution_error=None,
        duration_ms=1.5,
        warnings=()
    )
    with pytest.raises(FrozenInstanceError):
        result.row_count = 5  # type: ignore


def test_sqlite_adapter_declares_sqlite_dialect(tmp_path):
    adapter = SQLiteDatabaseExecutionAdapter(fixtures_dir=str(tmp_path))
    assert adapter.dialect == SQLDatabaseDialect.SQLITE
    assert SQLExecutionAdapterCapability.LOCAL_FIXTURE in adapter.capabilities()
    assert SQLExecutionAdapterCapability.READ_ONLY in adapter.capabilities()


def test_sqlite_adapter_rejects_non_sqlite_request(tmp_path):
    adapter = SQLiteDatabaseExecutionAdapter(fixtures_dir=str(tmp_path))
    config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.POSTGRESQL)
    # create request with postgresql dialect
    request = SQLDatabaseExecutionRequest(
        case_id="case_001",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        fixture_ref="fixture",
        connection_ref=None,
        config=config
    )
    with pytest.raises(SQLMultiDatabaseExecutionContractError):
        adapter.execute(request)


def test_sqlite_adapter_rejects_connection_ref(tmp_path):
    adapter = SQLiteDatabaseExecutionAdapter(fixtures_dir=str(tmp_path))
    config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE)
    # SQLite adapter does not support connection_ref
    request = SQLDatabaseExecutionRequest(
        case_id="case_001",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.SQLITE,
        fixture_ref=None,
        connection_ref="conn_001",
        config=config
    )
    with pytest.raises(SQLMultiDatabaseExecutionContractError):
        adapter.execute(request)


def test_sqlite_adapter_executes_local_fixture_read_only(tmp_path):
    db_file = tmp_path / "test_fixture.db"
    
    # Create the test db and insert a test table
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY, name TEXT)")
    cursor.execute("INSERT INTO test_table (id, name) VALUES (1, 'Alice'), (2, 'Bob')")
    conn.commit()
    conn.close()
    
    config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE)
    request = SQLDatabaseExecutionRequest(
        case_id="case_001",
        sql="SELECT * FROM test_table ORDER BY id ASC",
        dialect=SQLDatabaseDialect.SQLITE,
        fixture_ref="test_fixture",
        connection_ref=None,
        config=config
    )
    
    adapter = SQLiteDatabaseExecutionAdapter(fixtures_dir=str(tmp_path))
    result = adapter.execute(request)
    
    assert result.version == "sql_multi_database_execution_v1"
    assert result.case_id == "case_001"
    assert result.dialect == SQLDatabaseDialect.SQLITE
    assert result.row_count == 2
    assert result.rows == (
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"}
    )
    assert result.execution_error is None
    assert isinstance(result.sql_sha256, str)
    assert len(result.sql_sha256) == 64


def test_sqlite_adapter_rejects_unsafe_sql(tmp_path):
    db_file = tmp_path / "test_fixture.db"
    conn = sqlite3.connect(db_file)
    conn.close()

    adapter = SQLiteDatabaseExecutionAdapter(fixtures_dir=str(tmp_path))
    config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE)
    
    # Write operation check (INSERT)
    request = SQLDatabaseExecutionRequest(
        case_id="case_001",
        sql="INSERT INTO test_table (id, name) VALUES (3, 'Charlie')",
        dialect=SQLDatabaseDialect.SQLITE,
        fixture_ref="test_fixture",
        connection_ref=None,
        config=config
    )
    with pytest.raises(SQLMultiDatabaseExecutionContractError):
        adapter.execute(request)


def test_router_rejects_duplicate_adapter_dialects(tmp_path):
    adapter1 = SQLiteDatabaseExecutionAdapter(fixtures_dir=str(tmp_path))
    adapter2 = SQLiteDatabaseExecutionAdapter(fixtures_dir=str(tmp_path))
    
    with pytest.raises(SQLMultiDatabaseExecutionContractError):
        SQLDatabaseExecutionRouter(adapters=(adapter1, adapter2))


def test_router_rejects_unsupported_dialect(tmp_path):
    adapter = SQLiteDatabaseExecutionAdapter(fixtures_dir=str(tmp_path))
    router = SQLDatabaseExecutionRouter(adapters=(adapter,))
    
    config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.POSTGRESQL)
    # create request for postgresql
    request = SQLDatabaseExecutionRequest(
        case_id="case_001",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        fixture_ref="fixture",
        connection_ref=None,
        config=config
    )
    with pytest.raises(SQLMultiDatabaseExecutionContractError):
        router.execute(request)


def test_router_routes_sqlite_request_to_sqlite_adapter(tmp_path):
    db_file = tmp_path / "test_fixture.db"
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY, name TEXT)")
    cursor.execute("INSERT INTO test_table (id, name) VALUES (1, 'Alice')")
    conn.commit()
    conn.close()

    adapter = SQLiteDatabaseExecutionAdapter(fixtures_dir=str(tmp_path))
    router = SQLDatabaseExecutionRouter(adapters=(adapter,))
    
    config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE)
    request = SQLDatabaseExecutionRequest(
        case_id="case_001",
        sql="SELECT * FROM test_table",
        dialect=SQLDatabaseDialect.SQLITE,
        fixture_ref="test_fixture",
        connection_ref=None,
        config=config
    )
    
    result = router.execute(request)
    assert result.row_count == 1
    assert result.rows == ({"id": 1, "name": "Alice"},)
