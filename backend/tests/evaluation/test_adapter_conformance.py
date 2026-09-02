"""Sprint 29.7 — deterministic adapter-conformance core (Docker-free)."""
import pytest

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
