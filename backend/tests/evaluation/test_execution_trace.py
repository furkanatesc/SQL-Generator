import pytest
import hashlib
import json
from dataclasses import FrozenInstanceError

from app.evaluation.execution_trace import (
    SQL_EXECUTION_TRACE_VERSION,
    SQLExecutionTraceContractError,
    SQLExecutionTraceRecord,
)
from app.evaluation.multi_database_execution import (
    SQLDatabaseDialect,
    SQLExecutionMode,
    SQLDatabaseExecutionConfig,
    SQLDatabaseExecutionRequest,
    SQLDatabaseExecutionResult,
)
from app.evaluation.connection_aware_execution_orchestrator import (
    SQLConnectionAwareExecutionOutcome,
    SQLConnectionAwareExecutionOutcomeStatus,
)
from app.evaluation.connection_aware_execution import SQLConnectionAwareExecutionPlan
from app.evaluation.connection_abstraction import (
    SQLResolvedConnection,
    SQLConnectionEnvironment,
    SQLConnectionEndpoint,
    SQLConnectionAccessMode,
    SQLConnectionAuthMode,
)


def make_mock_outcome(
    status: SQLConnectionAwareExecutionOutcomeStatus,
    error: str = None,
    sql: str = "SELECT * FROM users",
    connection_ref: str = None,
    fixture_ref: str = None,
    has_plan: bool = True
) -> SQLConnectionAwareExecutionOutcome:
    if connection_ref is None and fixture_ref is None:
        fixture_ref = "db_ref"

    uses_connection = (connection_ref is not None)
    uses_fixture = (fixture_ref is not None)

    config = SQLDatabaseExecutionConfig(
        dialect=SQLDatabaseDialect.SQLITE,
        timeout_seconds=2.0,
        max_rows=1000,
        execution_mode=SQLExecutionMode.READ_ONLY,
    )
    request = SQLDatabaseExecutionRequest(
        case_id="c1",
        sql=sql,
        dialect=SQLDatabaseDialect.SQLITE,
        fixture_ref=fixture_ref,
        connection_ref=connection_ref,
        config=config,
    )
    
    plan = None
    if has_plan:
        dummy_conn = None
        if uses_connection:
            dummy_conn = SQLResolvedConnection(
                version="sql_connection_abstraction_v1",
                connection_ref=connection_ref,
                dialect=SQLDatabaseDialect.SQLITE,
                environment=SQLConnectionEnvironment.DEV,
                endpoint=SQLConnectionEndpoint(host="dummy", port=5432, database="dummy"),
                access_mode=SQLConnectionAccessMode.READ_ONLY,
                auth_mode=SQLConnectionAuthMode.NONE,
                secret_ref=None,
                max_rows=1000,
                timeout_seconds=2.0,
            )
        plan = SQLConnectionAwareExecutionPlan(
            version="sql_connection_aware_execution_v1",
            request=request,
            resolved_connection=dummy_conn,
            effective_dialect=SQLDatabaseDialect.SQLITE,
            effective_max_rows=1000,
            effective_timeout_seconds=2.0,
            uses_fixture=uses_fixture,
            uses_connection=uses_connection,
            can_execute_locally=uses_fixture,
            requires_live_connection=uses_connection,
            warnings=(),
        )

    dummy_result = None
    if status == SQLConnectionAwareExecutionOutcomeStatus.EXECUTED:
        dummy_result = SQLDatabaseExecutionResult(
            version="sql_multi_database_execution_v1",
            case_id="c1",
            dialect=SQLDatabaseDialect.SQLITE,
            sql=sql,
            sql_sha256=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
            rows=(),
            row_count=0,
            truncated=False,
            execution_error=error,
            duration_ms=0.0,
            warnings=(),
        )

    return SQLConnectionAwareExecutionOutcome(
        version="sql_connection_aware_execution_orchestrator_v1",
        request=request,
        plan=plan,
        status=status,
        execution_result=dummy_result,
        error=error,
        warnings=(),
    )


def test_execution_trace_contract_version_is_stable():
    assert SQL_EXECUTION_TRACE_VERSION == "sql_execution_trace_v1"


def test_execution_trace_record_is_immutable():
    record = SQLExecutionTraceRecord(
        version=SQL_EXECUTION_TRACE_VERSION,
        case_id="c1",
        dialect="sqlite",
        execution_mode="read_only",
        has_fixture_ref=True,
        has_connection_ref=False,
        sql_sha256="hash",
        plan_status="planned",
        outcome_status="executed",
        warnings=(),
    )
    with pytest.raises((FrozenInstanceError, AttributeError)):
        record.case_id = "c2"  # type: ignore


def test_execution_trace_serialization_is_deterministic():
    record = SQLExecutionTraceRecord(
        version=SQL_EXECUTION_TRACE_VERSION,
        case_id="c1",
        dialect="sqlite",
        execution_mode="read_only",
        has_fixture_ref=True,
        has_connection_ref=False,
        sql_sha256="hash",
        plan_status="planned",
        outcome_status="executed",
        warnings=("warn1", "warn2"),
        failure_category="row_count_mismatch",
        duration_ms=15.5,
        error="err",
    )
    d1 = record.to_dict()
    d2 = record.to_dict()
    assert d1 == d2
    
    # Assert specific keys structure for serialization stability
    assert d1["version"] == SQL_EXECUTION_TRACE_VERSION
    assert d1["case_id"] == "c1"
    assert d1["dialect"] == "sqlite"
    assert d1["execution_mode"] == "read_only"
    assert d1["has_fixture_ref"] is True
    assert d1["has_connection_ref"] is False
    assert d1["sql_sha256"] == "hash"
    assert d1["plan_status"] == "planned"
    assert d1["outcome_status"] == "executed"
    assert d1["warnings"] == ["warn1", "warn2"]
    assert d1["failure_category"] == "row_count_mismatch"
    assert d1["duration_ms"] == 15.5
    assert d1["error"] == "err"


def test_execution_trace_maps_executed_outcome():
    outcome = make_mock_outcome(
        status=SQLConnectionAwareExecutionOutcomeStatus.EXECUTED,
        fixture_ref="db_ref"
    )
    record = SQLExecutionTraceRecord.from_outcome(outcome, failure_category="passed", duration_ms=45.0)
    assert record.outcome_status == "executed"
    assert record.plan_status == "planned"
    assert record.failure_category == "passed"
    assert record.duration_ms == 45.0
    assert record.error is None


def test_execution_trace_maps_blocked_live_connection_outcome():
    outcome = make_mock_outcome(
        status=SQLConnectionAwareExecutionOutcomeStatus.BLOCKED_LIVE_CONNECTION,
        error="Live connection execution is blocked in this version",
        connection_ref="pg_conn"
    )
    record = SQLExecutionTraceRecord.from_outcome(outcome, failure_category="blocked_live_connection")
    assert record.outcome_status == "blocked_live_connection"
    assert record.plan_status == "planned"
    assert record.failure_category == "blocked_live_connection"
    assert "Live connection execution is blocked" in str(record.error)


def test_execution_trace_maps_rejected_outcome():
    outcome = make_mock_outcome(
        status=SQLConnectionAwareExecutionOutcomeStatus.REJECTED,
        error="rejected_by_orchestrator: planner rejected request",
        fixture_ref="db_ref",
        has_plan=False
    )
    record = SQLExecutionTraceRecord.from_outcome(outcome, failure_category="rejected_by_orchestrator")
    assert record.outcome_status == "rejected"
    assert record.plan_status == "no_plan"
    assert record.failure_category == "rejected_by_orchestrator"
    assert "planner rejected request" in str(record.error)


def test_execution_trace_does_not_include_raw_sql():
    sql = "SELECT id, secret_key FROM sensitive_table WHERE id = 42"
    outcome = make_mock_outcome(
        status=SQLConnectionAwareExecutionOutcomeStatus.EXECUTED,
        sql=sql,
        fixture_ref="db_ref"
    )
    record = SQLExecutionTraceRecord.from_outcome(outcome)
    serialized = record.to_dict()
    
    # Raw SQL text must not be present in output keys/values
    for k, v in serialized.items():
        assert sql not in str(k)
        assert sql not in str(v)
        
    expected_hash = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    assert serialized["sql_sha256"] == expected_hash


def test_execution_trace_does_not_leak_connection_ref_or_fixture_ref():
    conn_ref = "super-sensitive-connection-ref-secret"
    fix_ref = "path/to/my_fixture_database.db"
    
    outcome = make_mock_outcome(
        status=SQLConnectionAwareExecutionOutcomeStatus.REJECTED,
        error="rejected_by_orchestrator: Failed connection to super-sensitive-connection-ref-secret: password: secret123; api_key: key456; Bearer token789",
        connection_ref=conn_ref,
        has_plan=False
    )
    record = SQLExecutionTraceRecord.from_outcome(outcome)
    serialized = record.to_dict()
    
    # Confirm references don't leak
    assert record.has_connection_ref is True
    assert record.has_fixture_ref is False
    
    # Scan dictionary serialization to verify no raw leakage of the connection_ref or credentials
    serialized_str = json.dumps(serialized)
    assert conn_ref not in serialized_str
    assert fix_ref not in serialized_str
    assert "secret123" not in serialized_str
    assert "key456" not in serialized_str
    assert "token789" not in serialized_str
    
    # Ensure redactions are present
    assert "password:[REDACTED]" in record.error
    assert "api_key:[REDACTED]" in record.error
    assert "Bearer [REDACTED]" in record.error


def test_execution_trace_does_not_import_network_or_db_drivers():
    import subprocess
    import sys
    code = (
        "import sys\n"
        "import app.evaluation.execution_trace\n"
        "forbidden = ['psycopg', 'psycopg2', 'oracledb', 'cx_Oracle', 'pymysql', 'pyodbc', 'mysql']\n"
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
    assert "FORBIDDEN" not in res.stdout, f"Importing execution_trace imported forbidden driver: {res.stdout}"
