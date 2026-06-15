from dataclasses import FrozenInstanceError
import pytest
import sqlite3

from app.evaluation.multi_database_execution import (
    SQLDatabaseDialect,
    SQLDatabaseExecutionConfig,
    SQLDatabaseExecutionRequest,
    SQLDatabaseExecutionResult,
    SQLiteDatabaseExecutionAdapter,
    SQLDatabaseExecutionRouter,
)
from app.evaluation.connection_abstraction import (
    SQLConnectionEnvironment,
    SQLConnectionAuthMode,
    SQLConnectionAccessMode,
    SQLConnectionEndpoint,
    SQLConnectionProfile,
    SQLConnectionRegistry,
    SQLConnectionPolicy,
    SQLConnectionResolver,
    SQLResolvedConnection,
)
from app.evaluation.connection_aware_execution import (
    SQLConnectionAwareExecutionPlan,
    SQLConnectionAwareExecutionPlanner,
    SQLConnectionAwareExecutionConfig,
)
from app.evaluation.connection_aware_execution_orchestrator import (
    SQL_CONNECTION_AWARE_EXECUTION_ORCHESTRATOR_VERSION,
    SQLConnectionAwareExecutionOrchestratorContractError,
    SQLConnectionAwareExecutionOrchestratorConfig,
    SQLConnectionAwareExecutionOutcomeStatus,
    SQLConnectionAwareExecutionOutcome,
    SQLConnectionAwareExecutionOrchestrator,
)


def test_orchestrator_version_is_v1():
    assert (
        SQL_CONNECTION_AWARE_EXECUTION_ORCHESTRATOR_VERSION
        == "sql_connection_aware_execution_orchestrator_v1"
    )


def test_orchestrator_config_is_frozen():
    config = SQLConnectionAwareExecutionOrchestratorConfig()
    with pytest.raises(FrozenInstanceError):
        config.allow_live_connection_execution = True  # type: ignore


def test_orchestrator_config_disallows_live_execution_by_default():
    config = SQLConnectionAwareExecutionOrchestratorConfig()
    assert config.allow_live_connection_execution is False

    # True is treated as unsupported and rejected
    with pytest.raises(SQLConnectionAwareExecutionOrchestratorContractError) as exc_info:
        SQLConnectionAwareExecutionOrchestratorConfig(allow_live_connection_execution=True)
    assert "not supported" in str(exc_info.value)


def test_outcome_is_frozen():
    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.SQLITE,
        fixture_ref="my_fixture",
        connection_ref=None,
        config=req_config,
    )
    outcome = SQLConnectionAwareExecutionOutcome(
        version=SQL_CONNECTION_AWARE_EXECUTION_ORCHESTRATOR_VERSION,
        request=req,
        plan=None,
        status=SQLConnectionAwareExecutionOutcomeStatus.REJECTED,
        execution_result=None,
        error="some error",
        warnings=(),
    )
    with pytest.raises(FrozenInstanceError):
        outcome.status = SQLConnectionAwareExecutionOutcomeStatus.EXECUTED  # type: ignore


def test_outcome_rejects_invalid_version():
    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.SQLITE,
        fixture_ref="my_fixture",
        connection_ref=None,
        config=req_config,
    )
    with pytest.raises(SQLConnectionAwareExecutionOrchestratorContractError):
        SQLConnectionAwareExecutionOutcome(
            version="wrong_version",
            request=req,
            plan=None,
            status=SQLConnectionAwareExecutionOutcomeStatus.REJECTED,
            execution_result=None,
            error="error",
            warnings=(),
        )


def test_outcome_rejects_executed_without_execution_result():
    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.SQLITE,
        fixture_ref="my_fixture",
        connection_ref=None,
        config=req_config,
    )
    plan = SQLConnectionAwareExecutionPlan(
        version="sql_connection_aware_execution_v1",
        request=req,
        resolved_connection=None,
        effective_dialect=SQLDatabaseDialect.SQLITE,
        effective_max_rows=1000,
        effective_timeout_seconds=2.0,
        uses_fixture=True,
        uses_connection=False,
        can_execute_locally=True,
        requires_live_connection=False,
        warnings=(),
    )
    with pytest.raises(SQLConnectionAwareExecutionOrchestratorContractError) as exc_info:
        SQLConnectionAwareExecutionOutcome(
            version=SQL_CONNECTION_AWARE_EXECUTION_ORCHESTRATOR_VERSION,
            request=req,
            plan=plan,
            status=SQLConnectionAwareExecutionOutcomeStatus.EXECUTED,
            execution_result=None,  # Missing execution_result
            error=None,
            warnings=(),
        )
    assert "execution_result is required" in str(exc_info.value)


def test_outcome_rejects_blocked_without_error():
    endpoint = SQLConnectionEndpoint(host="dev-host", port=5432, database="devdb")
    resolved = SQLResolvedConnection(
        version="sql_connection_abstraction_v1",
        connection_ref="pg_conn",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        environment=SQLConnectionEnvironment.DEV,
        endpoint=endpoint,
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.NONE,
        secret_ref=None,
        max_rows=1000,
        timeout_seconds=2.0
    )
    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.POSTGRESQL)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        fixture_ref=None,
        connection_ref="pg_conn",
        config=req_config,
    )
    plan = SQLConnectionAwareExecutionPlan(
        version="sql_connection_aware_execution_v1",
        request=req,
        resolved_connection=resolved,
        effective_dialect=SQLDatabaseDialect.POSTGRESQL,
        effective_max_rows=1000,
        effective_timeout_seconds=2.0,
        uses_fixture=False,
        uses_connection=True,
        can_execute_locally=False,
        requires_live_connection=True,
        warnings=(),
    )
    with pytest.raises(SQLConnectionAwareExecutionOrchestratorContractError) as exc_info:
        SQLConnectionAwareExecutionOutcome(
            version=SQL_CONNECTION_AWARE_EXECUTION_ORCHESTRATOR_VERSION,
            request=req,
            plan=plan,
            status=SQLConnectionAwareExecutionOutcomeStatus.BLOCKED_LIVE_CONNECTION,
            execution_result=None,
            error=None,  # Missing error
            warnings=(),
        )
    assert "error description is required" in str(exc_info.value)


def test_orchestrator_executes_sqlite_fixture_request(tmp_path):
    # Setup SQLite fixture
    db_file = tmp_path / "test_fixture.db"
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY, name TEXT)")
    cursor.execute("INSERT INTO test_table (id, name) VALUES (1, 'Alice')")
    conn.commit()
    conn.close()

    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01",
        sql="SELECT * FROM test_table",
        dialect=SQLDatabaseDialect.SQLITE,
        fixture_ref="test_fixture",
        connection_ref=None,
        config=req_config,
    )

    planner = SQLConnectionAwareExecutionPlanner(resolver=None)
    adapter = SQLiteDatabaseExecutionAdapter(fixtures_dir=str(tmp_path))
    router = SQLDatabaseExecutionRouter(adapters=(adapter,))

    orchestrator = SQLConnectionAwareExecutionOrchestrator(planner=planner, router=router)
    outcome = orchestrator.execute(req)

    assert outcome.status == SQLConnectionAwareExecutionOutcomeStatus.EXECUTED
    assert outcome.execution_result is not None
    assert outcome.execution_result.row_count == 1
    assert outcome.execution_result.rows == ({"id": 1, "name": "Alice"},)
    assert outcome.error is None


def test_orchestrator_routes_fixture_request_through_planner(tmp_path):
    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.SQLITE,
        fixture_ref="non_existing_fixture",
        connection_ref=None,
        config=req_config,
    )

    # Let's verify that planner is called. We use a planner with mock or bad config that will raise error.
    planner = SQLConnectionAwareExecutionPlanner(resolver=None)
    adapter = SQLiteDatabaseExecutionAdapter(fixtures_dir=str(tmp_path))
    router = SQLDatabaseExecutionRouter(adapters=(adapter,))
    orchestrator = SQLConnectionAwareExecutionOrchestrator(planner=planner, router=router)

    outcome = orchestrator.execute(req)
    # Rejects because resolved db path is not found (raised by planner _resolve_db_path during SQLite adapter check if planner executes path validation?
    # Wait, SQLite adapter resolves path in execute(), but planner checks can_execute_locally based on dialect).
    # Since sqlite file does not exist, planner.plan(req) succeeds (planner does not look up file existance, adapter does!).
    # Then router.execute(req) raises "Fixture database not found".
    # This exception is caught by orchestrator and returned as REJECTED.
    assert outcome.status == SQLConnectionAwareExecutionOutcomeStatus.REJECTED
    assert "Fixture database not found" in outcome.error
    assert outcome.plan is not None  # plan was generated!


def test_orchestrator_blocks_connection_ref_request():
    endpoint = SQLConnectionEndpoint(host="dev-host", port=5432, database="devdb")
    p = SQLConnectionProfile(
        connection_ref="pg_conn",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        environment=SQLConnectionEnvironment.DEV,
        endpoint=endpoint,
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.NONE,
        secret_ref=None,
    )
    registry = SQLConnectionRegistry(profiles=(p,))
    policy = SQLConnectionPolicy()
    resolver = SQLConnectionResolver(registry=registry, policy=policy)

    planner = SQLConnectionAwareExecutionPlanner(
        resolver=resolver,
        config=SQLConnectionAwareExecutionConfig(allow_live_connection_plans=True),
    )
    router = SQLDatabaseExecutionRouter(adapters=())

    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.POSTGRESQL)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        fixture_ref=None,
        connection_ref="pg_conn",
        config=req_config,
    )

    orchestrator = SQLConnectionAwareExecutionOrchestrator(planner=planner, router=router)
    outcome = orchestrator.execute(req)

    assert outcome.status == SQLConnectionAwareExecutionOutcomeStatus.BLOCKED_LIVE_CONNECTION
    assert outcome.execution_result is None
    assert "blocked" in outcome.error
    assert outcome.plan is not None
    assert outcome.plan.requires_live_connection is True


def test_orchestrator_does_not_call_router_for_connection_ref():
    class ExplodingRouter(SQLDatabaseExecutionRouter):
        def __init__(self):
            super().__init__(adapters=())

        def execute(self, request):
            raise AssertionError("router must not be called for connection_ref")

    endpoint = SQLConnectionEndpoint(host="dev-host", port=5432, database="devdb")
    p = SQLConnectionProfile(
        connection_ref="pg_conn",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        environment=SQLConnectionEnvironment.DEV,
        endpoint=endpoint,
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.NONE,
        secret_ref=None,
    )
    registry = SQLConnectionRegistry(profiles=(p,))
    policy = SQLConnectionPolicy()
    resolver = SQLConnectionResolver(registry=registry, policy=policy)

    planner = SQLConnectionAwareExecutionPlanner(
        resolver=resolver,
        config=SQLConnectionAwareExecutionConfig(allow_live_connection_plans=True),
    )
    router = ExplodingRouter()

    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.POSTGRESQL)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        fixture_ref=None,
        connection_ref="pg_conn",
        config=req_config,
    )

    orchestrator = SQLConnectionAwareExecutionOrchestrator(
        planner=planner, router=router  # type: ignore
    )
    outcome = orchestrator.execute(req)
    assert outcome.status == SQLConnectionAwareExecutionOutcomeStatus.BLOCKED_LIVE_CONNECTION


def test_orchestrator_rejects_non_local_fixture_dialect(tmp_path):
    # Oracle is a non-local fixture dialect (only SQLite can execute locally)
    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.ORACLE)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.ORACLE,
        fixture_ref="oracle_fixture",
        connection_ref=None,
        config=req_config,
    )

    planner = SQLConnectionAwareExecutionPlanner(resolver=None)
    adapter = SQLiteDatabaseExecutionAdapter(fixtures_dir=str(tmp_path))
    router = SQLDatabaseExecutionRouter(adapters=(adapter,))
    orchestrator = SQLConnectionAwareExecutionOrchestrator(planner=planner, router=router)

    outcome = orchestrator.execute(req)
    assert outcome.status == SQLConnectionAwareExecutionOutcomeStatus.REJECTED
    assert "Local execution is not supported" in outcome.error


def test_orchestrator_returns_rejected_outcome_for_planner_error():
    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.SQLITE,
        fixture_ref=None,
        connection_ref="sqlite_conn",  # connection_ref rejects by default
        config=req_config,
    )

    planner = SQLConnectionAwareExecutionPlanner()  # allow_live_connection_plans is False
    router = SQLDatabaseExecutionRouter(adapters=())
    orchestrator = SQLConnectionAwareExecutionOrchestrator(planner=planner, router=router)

    outcome = orchestrator.execute(req)
    assert outcome.status == SQLConnectionAwareExecutionOutcomeStatus.REJECTED
    assert "disabled by default" in outcome.error


def test_orchestrator_returns_rejected_outcome_for_router_error(tmp_path):
    # Setup database file
    db_file = tmp_path / "test_fixture.db"
    conn = sqlite3.connect(db_file)
    conn.close()

    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE)
    # Unsafe SQL causes router exception
    req = SQLDatabaseExecutionRequest(
        case_id="case_01",
        sql="DELETE FROM test_table",
        dialect=SQLDatabaseDialect.SQLITE,
        fixture_ref="test_fixture",
        connection_ref=None,
        config=req_config,
    )

    planner = SQLConnectionAwareExecutionPlanner(resolver=None)
    adapter = SQLiteDatabaseExecutionAdapter(fixtures_dir=str(tmp_path))
    router = SQLDatabaseExecutionRouter(adapters=(adapter,))
    orchestrator = SQLConnectionAwareExecutionOrchestrator(planner=planner, router=router)

    outcome = orchestrator.execute(req)
    assert outcome.status == SQLConnectionAwareExecutionOutcomeStatus.REJECTED
    assert "Unsafe SQL query" in outcome.error


def test_orchestrator_does_not_import_network_or_db_drivers():
    from app.evaluation import connection_aware_execution_orchestrator

    source_file = connection_aware_execution_orchestrator.__file__
    with open(source_file, "r", encoding="utf-8") as f:
        content = f.read()

    forbidden = [
        "psycopg",
        "oracledb",
        "cx_Oracle",
        "sqlalchemy",
        "requests",
        "urllib",
        "http.client",
        "socket",
    ]
    for mod in forbidden:
        assert f"import {mod}" not in content, f"Forbidden import found: {mod}"
        assert f"from {mod}" not in content, f"Forbidden import found: {mod}"
