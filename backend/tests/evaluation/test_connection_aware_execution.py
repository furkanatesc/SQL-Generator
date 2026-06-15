from dataclasses import FrozenInstanceError
import pytest

from app.evaluation.multi_database_execution import (
    SQLDatabaseDialect,
    SQLDatabaseExecutionConfig,
    SQLDatabaseExecutionRequest,
)
from app.evaluation.connection_abstraction import (
    SQLConnectionEnvironment,
    SQLConnectionAuthMode,
    SQLConnectionAccessMode,
    SQLConnectionSecretRef,
    SQLConnectionEndpoint,
    SQLConnectionProfile,
    SQLConnectionRegistry,
    SQLConnectionPolicy,
    SQLConnectionResolver,
    SQLResolvedConnection,
)
from app.evaluation.connection_aware_execution import (
    SQL_CONNECTION_AWARE_EXECUTION_VERSION,
    SQLConnectionAwareExecutionContractError,
    SQLConnectionAwareExecutionConfig,
    SQLConnectionAwareExecutionPlan,
    SQLConnectionAwareExecutionPlanner,
)


def test_connection_aware_execution_version_is_v1():
    assert SQL_CONNECTION_AWARE_EXECUTION_VERSION == "sql_connection_aware_execution_v1"


def test_plan_is_frozen():
    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.SQLITE,
        fixture_ref="my_fixture",
        connection_ref=None,
        config=req_config
    )
    plan = SQLConnectionAwareExecutionPlan(
        version=SQL_CONNECTION_AWARE_EXECUTION_VERSION,
        request=req,
        resolved_connection=None,
        effective_dialect=SQLDatabaseDialect.SQLITE,
        effective_max_rows=1000,
        effective_timeout_seconds=2.0,
        uses_fixture=True,
        uses_connection=False,
        can_execute_locally=True,
        requires_live_connection=False,
        warnings=()
    )
    with pytest.raises(FrozenInstanceError):
        plan.effective_max_rows = 500  # type: ignore


def test_planner_rejects_invalid_request():
    planner = SQLConnectionAwareExecutionPlanner()
    with pytest.raises(SQLConnectionAwareExecutionContractError):
        planner.plan("not_a_request")  # type: ignore


def test_planner_plans_sqlite_fixture_without_resolver():
    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE, max_rows=500, timeout_seconds=1.5)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.SQLITE,
        fixture_ref="my_fixture",
        connection_ref=None,
        config=req_config
    )
    planner = SQLConnectionAwareExecutionPlanner(resolver=None)
    plan = planner.plan(req)
    
    assert plan.uses_fixture is True
    assert plan.uses_connection is False
    assert plan.resolved_connection is None
    assert plan.effective_dialect == SQLDatabaseDialect.SQLITE
    assert plan.effective_max_rows == 500
    assert plan.effective_timeout_seconds == 1.5
    assert plan.can_execute_locally is True
    assert plan.requires_live_connection is False


def test_planner_marks_sqlite_fixture_as_locally_executable():
    # SQLite is executable locally
    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE)
    req_sqlite = SQLDatabaseExecutionRequest(
        case_id="case_01", sql="SELECT 1", dialect=SQLDatabaseDialect.SQLITE,
        fixture_ref="my_fixture", connection_ref=None, config=req_config
    )
    planner = SQLConnectionAwareExecutionPlanner()
    plan_sqlite = planner.plan(req_sqlite)
    assert plan_sqlite.can_execute_locally is True

    # PostgreSQL is not executable locally
    req_config_pg = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.POSTGRESQL)
    req_pg = SQLDatabaseExecutionRequest(
        case_id="case_02", sql="SELECT 1", dialect=SQLDatabaseDialect.POSTGRESQL,
        fixture_ref="my_fixture", connection_ref=None, config=req_config_pg
    )
    plan_pg = planner.plan(req_pg)
    assert plan_pg.can_execute_locally is False


def test_planner_rejects_connection_ref_without_resolver():
    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.POSTGRESQL)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        fixture_ref=None,
        connection_ref="pg_conn",
        config=req_config
    )
    planner = SQLConnectionAwareExecutionPlanner(
        resolver=None,
        config=SQLConnectionAwareExecutionConfig(allow_live_connection_plans=True)
    )
    with pytest.raises(SQLConnectionAwareExecutionContractError) as exc_info:
        planner.plan(req)
    assert "resolver is required" in str(exc_info.value)



def test_planner_rejects_connection_ref_by_default():
    # Setup resolver
    endpoint = SQLConnectionEndpoint(host="dev-host", port=5432, database="devdb")
    p = SQLConnectionProfile(
        connection_ref="pg_conn",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        environment=SQLConnectionEnvironment.DEV,
        endpoint=endpoint,
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.NONE,
        secret_ref=None
    )
    registry = SQLConnectionRegistry(profiles=(p,))
    policy = SQLConnectionPolicy(
        allowed_environments=(SQLConnectionEnvironment.DEV,),
        allowed_dialects=(SQLDatabaseDialect.POSTGRESQL,)
    )
    resolver = SQLConnectionResolver(registry=registry, policy=policy)
    
    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.POSTGRESQL)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        fixture_ref=None,
        connection_ref="pg_conn",
        config=req_config
    )
    
    # Planner with allow_live_connection_plans = False by default
    planner = SQLConnectionAwareExecutionPlanner(resolver=resolver)
    with pytest.raises(SQLConnectionAwareExecutionContractError) as exc_info:
        planner.plan(req)
    assert "disabled by default" in str(exc_info.value)


def test_planner_resolves_connection_ref_when_live_plans_enabled():
    endpoint = SQLConnectionEndpoint(host="dev-host", port=5432, database="devdb")
    p = SQLConnectionProfile(
        connection_ref="pg_conn",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        environment=SQLConnectionEnvironment.DEV,
        endpoint=endpoint,
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.NONE,
        secret_ref=None,
        max_rows=1000,
        timeout_seconds=5.0
    )
    registry = SQLConnectionRegistry(profiles=(p,))
    policy = SQLConnectionPolicy(
        allowed_environments=(SQLConnectionEnvironment.DEV,),
        allowed_dialects=(SQLDatabaseDialect.POSTGRESQL,)
    )
    resolver = SQLConnectionResolver(registry=registry, policy=policy)
    
    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.POSTGRESQL, max_rows=500, timeout_seconds=2.0)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        fixture_ref=None,
        connection_ref="pg_conn",
        config=req_config
    )
    
    planner = SQLConnectionAwareExecutionPlanner(
        resolver=resolver,
        config=SQLConnectionAwareExecutionConfig(allow_live_connection_plans=True)
    )
    plan = planner.plan(req)
    
    assert plan.uses_fixture is False
    assert plan.uses_connection is True
    assert plan.resolved_connection is not None
    assert plan.resolved_connection.connection_ref == "pg_conn"
    assert plan.effective_dialect == SQLDatabaseDialect.POSTGRESQL
    assert plan.can_execute_locally is False
    assert plan.requires_live_connection is True


def test_planner_rejects_resolved_dialect_mismatch():
    endpoint = SQLConnectionEndpoint(host="dev-host", port=5432, database="devdb")
    # resolved dialect is POSTGRESQL
    p = SQLConnectionProfile(
        connection_ref="pg_conn",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        environment=SQLConnectionEnvironment.DEV,
        endpoint=endpoint,
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.NONE,
        secret_ref=None
    )
    registry = SQLConnectionRegistry(profiles=(p,))
    policy = SQLConnectionPolicy(
        allowed_environments=(SQLConnectionEnvironment.DEV,),
        allowed_dialects=(SQLDatabaseDialect.POSTGRESQL, SQLDatabaseDialect.ORACLE)
    )
    resolver = SQLConnectionResolver(registry=registry, policy=policy)
    
    # Request dialect is ORACLE (mismatch)
    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.ORACLE)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.ORACLE,
        fixture_ref=None,
        connection_ref="pg_conn",
        config=req_config
    )
    
    planner = SQLConnectionAwareExecutionPlanner(
        resolver=resolver,
        config=SQLConnectionAwareExecutionConfig(allow_live_connection_plans=True)
    )
    with pytest.raises(SQLConnectionAwareExecutionContractError) as exc_info:
        planner.plan(req)
    assert "dialect does not match" in str(exc_info.value)


def test_planner_accepts_read_only_resolved_connection():
    # Since profile creation blocks non-READ_ONLY access mode, we check that resolved connection's access mode matches READ_ONLY.
    endpoint = SQLConnectionEndpoint(host="dev-host", port=5432, database="devdb")
    p = SQLConnectionProfile(
        connection_ref="pg_conn",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        environment=SQLConnectionEnvironment.DEV,
        endpoint=endpoint,
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.NONE,
        secret_ref=None
    )
    registry = SQLConnectionRegistry(profiles=(p,))
    policy = SQLConnectionPolicy(
        allowed_environments=(SQLConnectionEnvironment.DEV,),
        allowed_dialects=(SQLDatabaseDialect.POSTGRESQL,)
    )
    resolver = SQLConnectionResolver(registry=registry, policy=policy)
    
    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.POSTGRESQL)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        fixture_ref=None,
        connection_ref="pg_conn",
        config=req_config
    )
    planner = SQLConnectionAwareExecutionPlanner(
        resolver=resolver,
        config=SQLConnectionAwareExecutionConfig(allow_live_connection_plans=True)
    )
    
    plan = planner.plan(req)
    assert plan.resolved_connection.access_mode == SQLConnectionAccessMode.READ_ONLY


def test_planner_uses_min_effective_max_rows():
    endpoint = SQLConnectionEndpoint(host="dev-host", port=5432, database="devdb")
    p = SQLConnectionProfile(
        connection_ref="pg_conn",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        environment=SQLConnectionEnvironment.DEV,
        endpoint=endpoint,
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.NONE,
        secret_ref=None,
        max_rows=100  # Resolver has max_rows = 100
    )
    registry = SQLConnectionRegistry(profiles=(p,))
    policy = SQLConnectionPolicy()
    resolver = SQLConnectionResolver(registry=registry, policy=policy)
    
    # Request config has max_rows = 500
    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.POSTGRESQL, max_rows=500)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01", sql="SELECT 1", dialect=SQLDatabaseDialect.POSTGRESQL,
        fixture_ref=None, connection_ref="pg_conn", config=req_config
    )
    planner = SQLConnectionAwareExecutionPlanner(
        resolver=resolver, config=SQLConnectionAwareExecutionConfig(allow_live_connection_plans=True)
    )
    plan = planner.plan(req)
    assert plan.effective_max_rows == 100  # min(500, 100)


def test_planner_uses_min_effective_timeout_seconds():
    endpoint = SQLConnectionEndpoint(host="dev-host", port=5432, database="devdb")
    p = SQLConnectionProfile(
        connection_ref="pg_conn",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        environment=SQLConnectionEnvironment.DEV,
        endpoint=endpoint,
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.NONE,
        secret_ref=None,
        timeout_seconds=5.0  # Resolver has timeout = 5.0
    )
    registry = SQLConnectionRegistry(profiles=(p,))
    policy = SQLConnectionPolicy()
    resolver = SQLConnectionResolver(registry=registry, policy=policy)
    
    # Request config has timeout = 2.0
    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.POSTGRESQL, timeout_seconds=2.0)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01", sql="SELECT 1", dialect=SQLDatabaseDialect.POSTGRESQL,
        fixture_ref=None, connection_ref="pg_conn", config=req_config
    )
    planner = SQLConnectionAwareExecutionPlanner(
        resolver=resolver, config=SQLConnectionAwareExecutionConfig(allow_live_connection_plans=True)
    )
    plan = planner.plan(req)
    assert plan.effective_timeout_seconds == 2.0  # min(2.0, 5.0)


def test_plan_does_not_expose_raw_secret():
    endpoint = SQLConnectionEndpoint(host="dev-host", port=5432, database="devdb")
    secret_ref = SQLConnectionSecretRef(provider="gcp-vault", key="my-pg-pass")
    p = SQLConnectionProfile(
        connection_ref="pg_conn",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        environment=SQLConnectionEnvironment.DEV,
        endpoint=endpoint,
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.SECRET_REF,
        secret_ref=secret_ref
    )
    registry = SQLConnectionRegistry(profiles=(p,))
    policy = SQLConnectionPolicy()
    resolver = SQLConnectionResolver(registry=registry, policy=policy)
    
    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.POSTGRESQL)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01", sql="SELECT 1", dialect=SQLDatabaseDialect.POSTGRESQL,
        fixture_ref=None, connection_ref="pg_conn", config=req_config
    )
    planner = SQLConnectionAwareExecutionPlanner(
        resolver=resolver, config=SQLConnectionAwareExecutionConfig(allow_live_connection_plans=True)
    )
    plan = planner.plan(req)
    
    # Verify no credentials fields exist in plan or resolved connection dictionaries
    assert plan.resolved_connection is not None
    for item in [plan.__dict__, plan.resolved_connection.__dict__]:
        for k in item:
            assert k not in ["password", "token", "secret_value", "raw_secret"]


def test_planner_does_not_import_network_or_db_drivers():
    from app.evaluation import connection_aware_execution
    source_file = connection_aware_execution.__file__
    with open(source_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    forbidden = ["psycopg", "oracledb", "cx_Oracle", "sqlalchemy", "requests", "urllib", "http.client", "socket"]
    for mod in forbidden:
        assert f"import {mod}" not in content, f"Forbidden import found: {mod}"
        assert f"from {mod}" not in content, f"Forbidden import found: {mod}"


def test_planner_rejects_non_read_only_execution_mode():
    from app.evaluation.multi_database_execution import SQLExecutionMode
    req_config = SQLDatabaseExecutionConfig(
        dialect=SQLDatabaseDialect.SQLITE,
        execution_mode=SQLExecutionMode.EXPLAIN_ONLY
    )
    req = SQLDatabaseExecutionRequest(
        case_id="case_01",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.SQLITE,
        fixture_ref="my_fixture",
        connection_ref=None,
        config=req_config
    )
    planner = SQLConnectionAwareExecutionPlanner()
    with pytest.raises(SQLConnectionAwareExecutionContractError) as exc_info:
        planner.plan(req)
    assert "supports only read_only execution mode" in str(exc_info.value)


def test_plan_rejects_both_fixture_and_connection_false():
    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.SQLITE,
        fixture_ref="my_fixture",
        connection_ref=None,
        config=req_config
    )
    with pytest.raises(SQLConnectionAwareExecutionContractError) as exc_info:
        SQLConnectionAwareExecutionPlan(
            version=SQL_CONNECTION_AWARE_EXECUTION_VERSION,
            request=req,
            resolved_connection=None,
            effective_dialect=SQLDatabaseDialect.SQLITE,
            effective_max_rows=1000,
            effective_timeout_seconds=2.0,
            uses_fixture=False,  # Both false
            uses_connection=False,
            can_execute_locally=True,
            requires_live_connection=False,
            warnings=()
        )
    assert "exactly one" in str(exc_info.value)


def test_plan_rejects_both_fixture_and_connection_true():
    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.SQLITE,
        fixture_ref="my_fixture",
        connection_ref=None,
        config=req_config
    )
    with pytest.raises(SQLConnectionAwareExecutionContractError) as exc_info:
        SQLConnectionAwareExecutionPlan(
            version=SQL_CONNECTION_AWARE_EXECUTION_VERSION,
            request=req,
            resolved_connection=None,
            effective_dialect=SQLDatabaseDialect.SQLITE,
            effective_max_rows=1000,
            effective_timeout_seconds=2.0,
            uses_fixture=True,  # Both true
            uses_connection=True,
            can_execute_locally=True,
            requires_live_connection=False,
            warnings=()
        )
    assert "exactly one" in str(exc_info.value)


def test_plan_rejects_fixture_plan_with_resolved_connection():
    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.SQLITE,
        fixture_ref="my_fixture",
        connection_ref=None,
        config=req_config
    )
    
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
    
    with pytest.raises(SQLConnectionAwareExecutionContractError) as exc_info:
        SQLConnectionAwareExecutionPlan(
            version=SQL_CONNECTION_AWARE_EXECUTION_VERSION,
            request=req,
            resolved_connection=resolved,  # Fixture backed but has resolved_connection
            effective_dialect=SQLDatabaseDialect.SQLITE,
            effective_max_rows=1000,
            effective_timeout_seconds=2.0,
            uses_fixture=True,
            uses_connection=False,
            can_execute_locally=True,
            requires_live_connection=False,
            warnings=()
        )
    assert "cannot include resolved_connection" in str(exc_info.value)


def test_plan_rejects_connection_plan_without_resolved_connection():
    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.POSTGRESQL)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        fixture_ref=None,
        connection_ref="pg_conn",
        config=req_config
    )
    with pytest.raises(SQLConnectionAwareExecutionContractError) as exc_info:
        SQLConnectionAwareExecutionPlan(
            version=SQL_CONNECTION_AWARE_EXECUTION_VERSION,
            request=req,
            resolved_connection=None,  # Connection backed but resolved_connection is None
            effective_dialect=SQLDatabaseDialect.POSTGRESQL,
            effective_max_rows=1000,
            effective_timeout_seconds=2.0,
            uses_fixture=False,
            uses_connection=True,
            can_execute_locally=False,
            requires_live_connection=True,
            warnings=()
        )
    assert "require resolved_connection" in str(exc_info.value)


def test_plan_rejects_connection_plan_marked_local():
    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.POSTGRESQL)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        fixture_ref=None,
        connection_ref="pg_conn",
        config=req_config
    )
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
    with pytest.raises(SQLConnectionAwareExecutionContractError) as exc_info:
        SQLConnectionAwareExecutionPlan(
            version=SQL_CONNECTION_AWARE_EXECUTION_VERSION,
            request=req,
            resolved_connection=resolved,
            effective_dialect=SQLDatabaseDialect.POSTGRESQL,
            effective_max_rows=1000,
            effective_timeout_seconds=2.0,
            uses_fixture=False,
            uses_connection=True,
            can_execute_locally=True,  # Connection backed but can execute locally
            requires_live_connection=True,
            warnings=()
        )
    assert "cannot execute locally" in str(exc_info.value)


def test_plan_rejects_effective_dialect_mismatch():
    req_config = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.SQLITE)
    req = SQLDatabaseExecutionRequest(
        case_id="case_01",
        sql="SELECT 1",
        dialect=SQLDatabaseDialect.SQLITE,
        fixture_ref="my_fixture",
        connection_ref=None,
        config=req_config
    )
    with pytest.raises(SQLConnectionAwareExecutionContractError) as exc_info:
        SQLConnectionAwareExecutionPlan(
            version=SQL_CONNECTION_AWARE_EXECUTION_VERSION,
            request=req,
            resolved_connection=None,
            effective_dialect=SQLDatabaseDialect.POSTGRESQL,  # Mismatch: request dialect is SQLITE
            effective_max_rows=1000,
            effective_timeout_seconds=2.0,
            uses_fixture=True,
            uses_connection=False,
            can_execute_locally=True,
            requires_live_connection=False,
            warnings=()
        )
    assert "effective_dialect must match" in str(exc_info.value)
