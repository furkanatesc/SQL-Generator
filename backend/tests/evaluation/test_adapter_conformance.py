"""Sprint 29.7 — deterministic adapter-conformance core (Docker-free)."""
import os

import pytest


def _backend_dir():
    # this file: backend/tests/evaluation/test_adapter_conformance.py -> backend/
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

from app.evaluation.adapter_conformance import (
    SQL_ADAPTER_CONFORMANCE_VERSION,
    CaseFold,
    fold,
    AdapterConformanceProfile,
    CONFORMANCE_PROFILES,
    profiles_for,
)
from app.evaluation.multi_database_execution import (
    SQLDatabaseDialect,
    SQLExecutionAdapterCapability,
)


def test_version_constant():
    assert SQL_ADAPTER_CONFORMANCE_VERSION == "sql_adapter_conformance_v1"


def test_fold_helper():
    assert fold("Customer", CaseFold.UPPER) == "CUSTOMER"
    assert fold("Customer", CaseFold.LOWER) == "customer"
    assert fold("Customer", CaseFold.AS_WRITTEN) == "Customer"


def test_registry_has_five_unique_dialects():
    dialects = [p.dialect for p in CONFORMANCE_PROFILES]
    assert set(dialects) == {
        SQLDatabaseDialect.SQLITE,
        SQLDatabaseDialect.POSTGRESQL,
        SQLDatabaseDialect.ORACLE,
        SQLDatabaseDialect.MYSQL,
        SQLDatabaseDialect.SQLSERVER,
    }
    assert len(dialects) == len(set(dialects))


def test_profiles_for_partitions_connection_based():
    conn = profiles_for(connection_based=True)
    fixture = profiles_for(connection_based=False)
    assert len(conn) == 4
    assert len(fixture) == 1
    assert fixture[0].dialect == SQLDatabaseDialect.SQLITE
    assert all(p.is_connection_based for p in conn)
    assert profiles_for() == CONFORMANCE_PROFILES


def test_every_profile_is_well_formed():
    for p in CONFORMANCE_PROFILES:
        assert isinstance(p, AdapterConformanceProfile)
        assert isinstance(p.expected_capabilities, frozenset)
        assert p.expected_capabilities  # non-empty
        assert all(isinstance(c, SQLExecutionAdapterCapability) for c in p.expected_capabilities)
        assert isinstance(p.case_fold, CaseFold)
        assert callable(p.adapter_factory)
        if p.is_connection_based:
            assert p.pytest_marker in {"postgres", "oracle", "mysql", "sqlserver"}
            assert p.driver_module_name
            assert callable(p.inert_adapter_factory)
            assert callable(p.resolver)
        else:
            assert p.inert_adapter_factory is None


def test_importing_module_loads_no_db_driver():
    import sys
    for driver in ("pymssql", "pymysql", "oracledb", "psycopg2"):
        assert driver not in sys.modules, f"{driver} must not be imported by adapter_conformance"


from app.evaluation.adapter_conformance import (
    assert_contract_conformance,
    contract_conformance_report,
    profiles_for as _profiles_for,
)
from app.evaluation.multi_database_execution import (
    SQLDatabaseExecutionRouter,
    SQLDatabaseExecutionConfig,
    SQLDatabaseExecutionRequest,
    SQLExecutionMode,
    SQLMultiDatabaseExecutionContractError,
)


@pytest.mark.parametrize("profile", CONFORMANCE_PROFILES, ids=lambda p: p.dialect.value)
def test_adapter_is_contract_conformant(profile):
    violations = assert_contract_conformance(profile)
    assert violations == [], f"{profile.dialect.value}: {violations}"


@pytest.mark.parametrize("profile", CONFORMANCE_PROFILES, ids=lambda p: p.dialect.value)
def test_adapter_dialect_matches_profile(profile):
    assert profile.adapter_factory().dialect == profile.dialect


@pytest.mark.parametrize("profile", CONFORMANCE_PROFILES, ids=lambda p: p.dialect.value)
def test_adapter_capabilities_match_profile(profile):
    caps = profile.adapter_factory().capabilities()
    assert set(caps) == profile.expected_capabilities
    assert len(caps) == len(set(caps))  # no duplicates


def test_all_adapters_register_in_one_router():
    adapters = tuple(p.adapter_factory() for p in CONFORMANCE_PROFILES)
    router = SQLDatabaseExecutionRouter(adapters=adapters)
    for p in CONFORMANCE_PROFILES:
        assert router.get_adapter(p.dialect).dialect == p.dialect


@pytest.mark.parametrize("profile", _profiles_for(connection_based=True), ids=lambda p: p.dialect.value)
def test_inert_adapter_returns_graceful_empty_result(profile):
    adapter = profile.inert_adapter_factory()
    cfg = SQLDatabaseExecutionConfig(dialect=profile.dialect)
    req = SQLDatabaseExecutionRequest(
        case_id="conf", sql="SELECT 1", dialect=profile.dialect,
        fixture_ref=None, connection_ref="local_docker", config=cfg,
    )
    res = adapter.execute(req)  # must NOT raise
    assert res.rows == ()
    assert res.row_count == 0
    assert res.execution_error  # non-empty
    assert res.dialect == profile.dialect


@pytest.mark.parametrize("profile", _profiles_for(connection_based=True), ids=lambda p: p.dialect.value)
def test_explain_only_consistency(profile):
    adapter = profile.inert_adapter_factory()
    cfg = SQLDatabaseExecutionConfig(dialect=profile.dialect, execution_mode=SQLExecutionMode.EXPLAIN_ONLY)
    req = SQLDatabaseExecutionRequest(
        case_id="conf", sql="SELECT 1", dialect=profile.dialect,
        fixture_ref=None, connection_ref="local_docker", config=cfg,
    )
    if profile.accepts_explain_only:
        res = adapter.execute(req)  # postgres: accepted; inert -> graceful empty
        assert res.execution_error
    else:
        with pytest.raises(SQLMultiDatabaseExecutionContractError):
            adapter.execute(req)


@pytest.mark.parametrize("profile", CONFORMANCE_PROFILES, ids=lambda p: p.dialect.value)
def test_contract_conformance_report_shape(profile):
    rep = contract_conformance_report(profile)
    assert rep["dialect"] == profile.dialect.value
    assert set(rep["capabilities"]) == {c.value for c in profile.expected_capabilities}
    assert rep["accepts_explain_only"] == profile.accepts_explain_only
    assert rep["contract_conformance"]["ok"] is True
    assert rep["contract_conformance"]["violations"] == []


import subprocess
import sys


@pytest.mark.parametrize("profile", _profiles_for(connection_based=True), ids=lambda p: p.dialect.value)
def test_adapter_module_import_is_driver_isolated(profile):
    code = (
        "import importlib, sys; "
        f"importlib.import_module({profile.adapter_module_name!r}); "
        f"assert {profile.driver_module_name!r} not in sys.modules, "
        f"'{profile.driver_module_name} imported at module import time'; "
        "print('ok')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, cwd=_backend_dir(),
    )
    assert proc.returncode == 0, f"{profile.dialect.value} isolation failed: {proc.stderr}"
    assert "ok" in proc.stdout
