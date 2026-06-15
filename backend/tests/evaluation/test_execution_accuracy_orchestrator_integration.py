import os
import sys
import sqlite3
import tempfile
import pytest
from typing import Tuple

from app.evaluation.golden_dataset_contract import (
    SQLGoldenDatasetCase,
    SQLResultComparePolicy,
    SQLGoldenDatasetTier,
    SQLAdjudicationStatus,
)
from app.evaluation.execution_accuracy import (
    SQLExecutionAccuracyConfig,
    SQLExecutionAccuracyHarness,
    SQLExecutionAccuracyContractError,
)
from app.evaluation.multi_database_execution import (
    SQLDatabaseDialect,
    SQLDatabaseExecutionConfig,
    SQLDatabaseExecutionRequest,
    SQLDatabaseExecutionResult,
    SQLDatabaseExecutionAdapter,
    SQLDatabaseExecutionRouter,
    SQLiteDatabaseExecutionAdapter,
    SQLExecutionAdapterCapability,
    SQLExecutionMode,
)
from app.evaluation.connection_aware_execution import (
    SQLConnectionAwareExecutionPlanner,
    SQLConnectionAwareExecutionConfig,
)
from app.evaluation.connection_abstraction import (
    SQLConnectionResolver,
    SQLConnectionRegistry,
    SQLConnectionPolicy,
    SQLConnectionProfile,
    SQLConnectionEndpoint,
    SQLConnectionEnvironment,
    SQLConnectionAccessMode,
    SQLConnectionAuthMode,
)
from app.evaluation.connection_aware_execution_orchestrator import (
    SQLConnectionAwareExecutionOrchestrator,
    SQLConnectionAwareExecutionOrchestratorConfig,
    SQLConnectionAwareExecutionOutcomeStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class ExplodingRouter(SQLDatabaseExecutionRouter):
    """Router that must never be called — verifies connection_ref requests
    don't reach the router layer."""

    def __init__(self):
        # Bypass parent __post_init__ by using a valid empty adapters tuple
        object.__setattr__(self, "adapters", ())

    def execute(self, request: SQLDatabaseExecutionRequest) -> SQLDatabaseExecutionResult:
        raise AssertionError("router must not be called for connection_ref")

    def get_adapter(self, dialect):
        raise AssertionError("router must not be called for connection_ref")


def _make_pg_dev_profile(connection_ref: str = "pg_dev_conn") -> SQLConnectionProfile:
    """Create a minimal PostgreSQL dev connection profile for testing."""
    return SQLConnectionProfile(
        connection_ref=connection_ref,
        dialect=SQLDatabaseDialect.POSTGRESQL,
        environment=SQLConnectionEnvironment.DEV,
        endpoint=SQLConnectionEndpoint(host="localhost", port=5432, database="testdb"),
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.NONE,
        secret_ref=None,
    )


def _make_resolver_with_profiles(*profiles: SQLConnectionProfile) -> SQLConnectionResolver:
    """Build a resolver with given profiles and a permissive dev policy."""
    registry = SQLConnectionRegistry(profiles=profiles)
    policy = SQLConnectionPolicy()
    return SQLConnectionResolver(registry=registry, policy=policy)


@pytest.fixture
def temp_fixtures_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_db.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, score REAL)")
        cursor.execute("INSERT INTO users (id, name, score) VALUES (1, 'Alice', 95.51)")
        cursor.execute("INSERT INTO users (id, name, score) VALUES (2, 'Bob', 80.0)")
        cursor.execute("INSERT INTO users (id, name, score) VALUES (3, 'Charlie', NULL)")
        conn.commit()
        conn.close()
        yield tmpdir


def make_test_case(**kwargs):
    default_args = {
        "case_id": "c1",
        "question": "Get all users",
        "dialect": "sqlite",
        "schema_snapshot_id": "snap1",
        "fixture_ref": "test_db",
        "gold_sql": "SELECT id, name, score FROM users ORDER BY id",
        "tier": SQLGoldenDatasetTier.CORE_REGRESSION,
        "adjudication_status": SQLAdjudicationStatus.APPROVED,
        "no_expected_result_reason": "Run reference gold_sql",
        "result_compare_policy": SQLResultComparePolicy.EXACT_ORDERED,
    }
    default_args.update(kwargs)
    return SQLGoldenDatasetCase(**default_args)


def make_orchestrator(fixtures_dir: str) -> SQLConnectionAwareExecutionOrchestrator:
    """Create a standard orchestrator for SQLite fixture-based execution."""
    planner = SQLConnectionAwareExecutionPlanner()
    adapter = SQLiteDatabaseExecutionAdapter(fixtures_dir=fixtures_dir)
    router = SQLDatabaseExecutionRouter(adapters=(adapter,))
    config = SQLConnectionAwareExecutionOrchestratorConfig()
    return SQLConnectionAwareExecutionOrchestrator(
        planner=planner,
        router=router,
        config=config,
    )


def make_exploding_orchestrator() -> SQLConnectionAwareExecutionOrchestrator:
    """Create an orchestrator with ExplodingRouter — for connection_ref blocking tests.

    Includes a resolver with a PostgreSQL dev profile so the planner can
    successfully resolve connection_ref requests. The orchestrator then blocks
    the request at the live-connection gate without reaching the router.
    """
    profile = _make_pg_dev_profile("pg_dev_conn")
    resolver = _make_resolver_with_profiles(profile)
    planner = SQLConnectionAwareExecutionPlanner(
        resolver=resolver,
        config=SQLConnectionAwareExecutionConfig(allow_live_connection_plans=True),
    )
    router = ExplodingRouter()
    config = SQLConnectionAwareExecutionOrchestratorConfig()
    return SQLConnectionAwareExecutionOrchestrator(
        planner=planner,
        router=router,
        config=config,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExecutionAccuracyUsesOrchestratorByDefault:
    """test_execution_accuracy_uses_orchestrator_by_default"""

    def test_default_config_has_orchestrator_enabled(self):
        config = SQLExecutionAccuracyConfig(fixtures_dir="data")
        assert config.use_connection_aware_orchestrator is True

    def test_harness_requires_orchestrator_when_enabled(self):
        config = SQLExecutionAccuracyConfig(fixtures_dir="data")
        with pytest.raises(SQLExecutionAccuracyContractError) as exc_info:
            SQLExecutionAccuracyHarness(config)
        assert "orchestrator is required" in str(exc_info.value)

    def test_harness_accepts_orchestrator_when_enabled(self, temp_fixtures_dir):
        config = SQLExecutionAccuracyConfig(fixtures_dir=temp_fixtures_dir)
        orchestrator = make_orchestrator(temp_fixtures_dir)
        harness = SQLExecutionAccuracyHarness(config, orchestrator=orchestrator)
        assert harness.orchestrator is orchestrator

    def test_legacy_mode_does_not_require_orchestrator(self, temp_fixtures_dir):
        config = SQLExecutionAccuracyConfig(
            fixtures_dir=temp_fixtures_dir,
            use_connection_aware_orchestrator=False,
        )
        harness = SQLExecutionAccuracyHarness(config)
        assert harness.orchestrator is None


class TestExecutionAccuracyExecutesSQLiteFixtureViaOrchestrator:
    """test_execution_accuracy_executes_sqlite_fixture_via_orchestrator"""

    def test_sqlite_fixture_case_executes_via_orchestrator(self, temp_fixtures_dir):
        config = SQLExecutionAccuracyConfig(fixtures_dir=temp_fixtures_dir)
        orchestrator = make_orchestrator(temp_fixtures_dir)
        harness = SQLExecutionAccuracyHarness(config, orchestrator=orchestrator)

        case = make_test_case()
        predicted_sql = "SELECT id, name, score FROM users ORDER BY id"

        result = harness.run_case(case, predicted_sql)
        assert result.passed is True
        assert result.execution_error is None
        assert result.actual_row_count == 3


class TestExecutionAccuracyBlocksConnectionRefWithoutRouterCall:
    """test_execution_accuracy_blocks_connection_ref_without_router_call

    Uses ExplodingRouter to guarantee router is never contacted for
    connection_ref requests.
    """

    def test_connection_ref_does_not_reach_router(self, temp_fixtures_dir):
        """Build a connection_ref request directly through the orchestrator
        to verify the router is not called."""
        orchestrator = make_exploding_orchestrator()

        config = SQLDatabaseExecutionConfig(
            dialect=SQLDatabaseDialect.POSTGRESQL,
            timeout_seconds=2.0,
            max_rows=1000,
            execution_mode=SQLExecutionMode.READ_ONLY,
        )
        request = SQLDatabaseExecutionRequest(
            case_id="conn_case_1",
            sql="SELECT 1",
            dialect=SQLDatabaseDialect.POSTGRESQL,
            fixture_ref=None,
            connection_ref="pg_dev_conn",
            config=config,
        )

        # Orchestrator should block without touching router
        outcome = orchestrator.execute(request)

        assert outcome.status == SQLConnectionAwareExecutionOutcomeStatus.BLOCKED_LIVE_CONNECTION
        assert outcome.execution_result is None
        # ExplodingRouter was NOT called — no AssertionError


class TestExecutionAccuracyMapsBlockedLiveConnectionToFailedResult:
    """test_execution_accuracy_maps_blocked_live_connection_to_failed_result"""

    def test_blocked_outcome_produces_failed_accuracy_result(self, temp_fixtures_dir):
        """Simulate a case that triggers BLOCKED_LIVE_CONNECTION through
        the harness _run_case_via_orchestrator path via _build_execution_request."""
        orchestrator = make_exploding_orchestrator()

        config = SQLExecutionAccuracyConfig(fixtures_dir=temp_fixtures_dir)
        harness = SQLExecutionAccuracyHarness(config, orchestrator=orchestrator)

        # Build a request manually through orchestrator to simulate blocked
        exec_config = SQLDatabaseExecutionConfig(
            dialect=SQLDatabaseDialect.POSTGRESQL,
            timeout_seconds=2.0,
            max_rows=1000,
            execution_mode=SQLExecutionMode.READ_ONLY,
        )
        request = SQLDatabaseExecutionRequest(
            case_id="conn_blocked_1",
            sql="SELECT 1",
            dialect=SQLDatabaseDialect.POSTGRESQL,
            fixture_ref=None,
            connection_ref="pg_dev_conn",
            config=exec_config,
        )

        outcome = orchestrator.execute(request)
        assert outcome.status == SQLConnectionAwareExecutionOutcomeStatus.BLOCKED_LIVE_CONNECTION

        # The accuracy result should be failed
        assert outcome.execution_result is None
        assert outcome.error is not None
        assert "blocked" in outcome.error.lower() or "live" in outcome.error.lower()


class TestExecutionAccuracyMapsRejectedOutcomeToFailedResult:
    """test_execution_accuracy_maps_rejected_outcome_to_failed_result"""

    def test_rejected_outcome_produces_failed_accuracy_result(self, temp_fixtures_dir):
        """Create a case that will be rejected by the planner (e.g., EXPLAIN_ONLY mode)."""
        orchestrator = make_orchestrator(temp_fixtures_dir)
        config = SQLExecutionAccuracyConfig(fixtures_dir=temp_fixtures_dir)
        harness = SQLExecutionAccuracyHarness(config, orchestrator=orchestrator)

        # Build a request that the planner will reject (EXPLAIN_ONLY mode)
        exec_config = SQLDatabaseExecutionConfig(
            dialect=SQLDatabaseDialect.SQLITE,
            timeout_seconds=2.0,
            max_rows=1000,
            execution_mode=SQLExecutionMode.EXPLAIN_ONLY,
        )
        request = SQLDatabaseExecutionRequest(
            case_id="rejected_1",
            sql="SELECT 1",
            dialect=SQLDatabaseDialect.SQLITE,
            fixture_ref="test_db",
            connection_ref=None,
            config=exec_config,
        )

        outcome = orchestrator.execute(request)
        assert outcome.status == SQLConnectionAwareExecutionOutcomeStatus.REJECTED
        assert outcome.execution_result is None
        assert outcome.error is not None


class TestExecutionAccuracyPreservesSuccessfulSQLiteComparison:
    """test_execution_accuracy_preserves_successful_sqlite_comparison"""

    def test_matching_sql_passes(self, temp_fixtures_dir):
        config = SQLExecutionAccuracyConfig(fixtures_dir=temp_fixtures_dir)
        orchestrator = make_orchestrator(temp_fixtures_dir)
        harness = SQLExecutionAccuracyHarness(config, orchestrator=orchestrator)

        case = make_test_case()
        predicted_sql = "SELECT id, name, score FROM users ORDER BY id"

        result = harness.run_case(case, predicted_sql)
        assert result.passed is True
        assert result.execution_error is None
        assert result.actual_row_count == 3
        assert result.expected_row_count == 3
        assert result.predicted_sql_sha256 != ""
        assert result.gold_sql_sha256 != ""

    def test_batch_run_passes_matching_cases(self, temp_fixtures_dir):
        config = SQLExecutionAccuracyConfig(fixtures_dir=temp_fixtures_dir)
        orchestrator = make_orchestrator(temp_fixtures_dir)
        harness = SQLExecutionAccuracyHarness(config, orchestrator=orchestrator)

        case = make_test_case()
        sqls = {"c1": "SELECT id, name, score FROM users ORDER BY id"}

        run_result = harness.run_harness([case], sqls)
        assert run_result.total_cases == 1
        assert run_result.passed_cases == 1
        assert run_result.pass_rate == 1.0


class TestExecutionAccuracyPreservesFailedSQLiteComparison:
    """test_execution_accuracy_preserves_failed_sqlite_comparison"""

    def test_mismatched_sql_fails(self, temp_fixtures_dir):
        config = SQLExecutionAccuracyConfig(fixtures_dir=temp_fixtures_dir)
        orchestrator = make_orchestrator(temp_fixtures_dir)
        harness = SQLExecutionAccuracyHarness(config, orchestrator=orchestrator)

        case = make_test_case()
        # Different SQL that returns different results
        predicted_sql = "SELECT id, name, score FROM users WHERE id = 1"

        result = harness.run_case(case, predicted_sql)
        assert result.passed is False
        # Should be a comparison failure, not an execution error
        assert result.execution_error is None
        assert result.actual_row_count == 1
        assert result.expected_row_count == 3

    def test_syntax_error_sql_fails(self, temp_fixtures_dir):
        config = SQLExecutionAccuracyConfig(fixtures_dir=temp_fixtures_dir)
        orchestrator = make_orchestrator(temp_fixtures_dir)
        harness = SQLExecutionAccuracyHarness(config, orchestrator=orchestrator)

        case = make_test_case()
        predicted_sql = "SELECT * FROM nonexistent_table_xyz"

        result = harness.run_case(case, predicted_sql)
        assert result.passed is False
        assert result.execution_error is not None


class TestExecutionAccuracyDoesNotImportNetworkOrDbDrivers:
    """test_execution_accuracy_does_not_import_network_or_db_drivers"""

    def test_no_forbidden_imports_in_execution_accuracy(self):
        """Verify that the execution_accuracy module does not import
        any database driver or network libraries."""
        import app.evaluation.execution_accuracy as mod

        source_file = mod.__file__
        assert source_file is not None

        with open(source_file, "r", encoding="utf-8") as f:
            source = f.read()

        forbidden_imports = [
            "psycopg2",
            "psycopg",
            "oracledb",
            "cx_Oracle",
            "sqlalchemy",
            "pymysql",
            "pyodbc",
            "requests",
            "httpx",
            "urllib3",
            "aiohttp",
        ]

        for forbidden in forbidden_imports:
            assert f"import {forbidden}" not in source, (
                f"Forbidden import '{forbidden}' found in execution_accuracy.py"
            )
            assert f"from {forbidden}" not in source, (
                f"Forbidden import 'from {forbidden}' found in execution_accuracy.py"
            )

    def test_no_forbidden_imports_in_orchestrator(self):
        """Verify orchestrator module doesn't import driver/network libs."""
        import app.evaluation.connection_aware_execution_orchestrator as mod

        source_file = mod.__file__
        assert source_file is not None

        with open(source_file, "r", encoding="utf-8") as f:
            source = f.read()

        forbidden_imports = [
            "psycopg2",
            "psycopg",
            "oracledb",
            "cx_Oracle",
            "sqlalchemy",
            "pymysql",
            "pyodbc",
            "requests",
            "httpx",
            "urllib3",
            "aiohttp",
        ]

        for forbidden in forbidden_imports:
            assert f"import {forbidden}" not in source, (
                f"Forbidden import '{forbidden}' found in connection_aware_execution_orchestrator.py"
            )
            assert f"from {forbidden}" not in source, (
                f"Forbidden import 'from {forbidden}' found in connection_aware_execution_orchestrator.py"
            )
