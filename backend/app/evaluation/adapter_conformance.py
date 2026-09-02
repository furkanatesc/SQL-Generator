"""Sprint 29.7 — Adapter Conformance Eval Suite.

A single, declarative source of truth for what it means for a database execution
adapter to conform to the shared ``SQLDatabaseExecutionAdapter`` contract. This
module is IMPORT-SAFE: importing it loads NO database driver. Driver names are
recorded only as strings; the deterministic conformance core uses inert adapters
(a resolver that returns ``None``) so nothing ever connects.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, FrozenSet, Optional, Tuple

from app.evaluation.multi_database_execution import (
    SQLDatabaseDialect,
    SQLDatabaseExecutionAdapter,
    SQLExecutionAdapterCapability,
    SQLiteDatabaseExecutionAdapter,
)
from app.evaluation.postgres_execution_adapter import PostgresDatabaseExecutionAdapter
from app.evaluation.oracle_execution_adapter import OracleDatabaseExecutionAdapter
from app.evaluation.mysql_execution_adapter import MySQLDatabaseExecutionAdapter
from app.evaluation.mssql_execution_adapter import MSSQLDatabaseExecutionAdapter
from app.evaluation.postgres_connection_resolver import (
    resolve_local_docker_connection as _resolve_pg,
)
from app.evaluation.oracle_connection_resolver import (
    resolve_local_docker_connection as _resolve_oracle,
)
from app.evaluation.mysql_connection_resolver import (
    resolve_local_docker_connection as _resolve_mysql,
)
from app.evaluation.mssql_connection_resolver import (
    resolve_local_docker_connection as _resolve_mssql,
)

SQL_ADAPTER_CONFORMANCE_VERSION = "sql_adapter_conformance_v1"

_CAP = SQLExecutionAdapterCapability


class CaseFold(str, Enum):
    UPPER = "upper"
    LOWER = "lower"
    AS_WRITTEN = "as_written"


def fold(name: str, case_fold: CaseFold) -> str:
    if case_fold == CaseFold.UPPER:
        return name.upper()
    if case_fold == CaseFold.LOWER:
        return name.lower()
    return name


@dataclass(frozen=True)
class AdapterConformanceProfile:
    dialect: SQLDatabaseDialect
    adapter_module_name: str
    adapter_factory: Callable[[], SQLDatabaseExecutionAdapter]
    inert_adapter_factory: Optional[Callable[[], SQLDatabaseExecutionAdapter]]
    resolver: Optional[Callable[..., Any]]
    driver_module_name: Optional[str]
    pytest_marker: Optional[str]
    expected_capabilities: FrozenSet[SQLExecutionAdapterCapability]
    accepts_explain_only: bool
    case_fold: CaseFold
    seed_fixture_path: Optional[str]
    is_connection_based: bool


def _inert(adapter_cls) -> Callable[[], SQLDatabaseExecutionAdapter]:
    return lambda: adapter_cls(connection_resolver=lambda: None)


CONFORMANCE_PROFILES: Tuple[AdapterConformanceProfile, ...] = (
    AdapterConformanceProfile(
        dialect=SQLDatabaseDialect.SQLITE,
        adapter_module_name="app.evaluation.multi_database_execution",
        adapter_factory=lambda: SQLiteDatabaseExecutionAdapter(
            fixtures_dir=tempfile.gettempdir()
        ),
        inert_adapter_factory=None,
        resolver=None,
        driver_module_name=None,
        pytest_marker=None,
        expected_capabilities=frozenset({_CAP.LOCAL_FIXTURE, _CAP.READ_ONLY}),
        accepts_explain_only=False,
        case_fold=CaseFold.AS_WRITTEN,
        seed_fixture_path=None,
        is_connection_based=False,
    ),
    AdapterConformanceProfile(
        dialect=SQLDatabaseDialect.POSTGRESQL,
        adapter_module_name="app.evaluation.postgres_execution_adapter",
        adapter_factory=PostgresDatabaseExecutionAdapter,
        inert_adapter_factory=_inert(PostgresDatabaseExecutionAdapter),
        resolver=_resolve_pg,
        driver_module_name="psycopg2",
        pytest_marker="postgres",
        expected_capabilities=frozenset({_CAP.CONNECTION_REF, _CAP.READ_ONLY, _CAP.EXPLAIN_ONLY}),
        accepts_explain_only=True,
        case_fold=CaseFold.LOWER,
        seed_fixture_path="tests/fixtures/postgres/seed.sql",
        is_connection_based=True,
    ),
    AdapterConformanceProfile(
        dialect=SQLDatabaseDialect.ORACLE,
        adapter_module_name="app.evaluation.oracle_execution_adapter",
        adapter_factory=OracleDatabaseExecutionAdapter,
        inert_adapter_factory=_inert(OracleDatabaseExecutionAdapter),
        resolver=_resolve_oracle,
        driver_module_name="oracledb",
        pytest_marker="oracle",
        expected_capabilities=frozenset({_CAP.CONNECTION_REF, _CAP.READ_ONLY}),
        accepts_explain_only=False,
        case_fold=CaseFold.UPPER,
        seed_fixture_path="tests/fixtures/oracle/seed.sql",
        is_connection_based=True,
    ),
    AdapterConformanceProfile(
        dialect=SQLDatabaseDialect.MYSQL,
        adapter_module_name="app.evaluation.mysql_execution_adapter",
        adapter_factory=MySQLDatabaseExecutionAdapter,
        inert_adapter_factory=_inert(MySQLDatabaseExecutionAdapter),
        resolver=_resolve_mysql,
        driver_module_name="pymysql",
        pytest_marker="mysql",
        expected_capabilities=frozenset({_CAP.CONNECTION_REF, _CAP.READ_ONLY}),
        accepts_explain_only=False,
        case_fold=CaseFold.LOWER,
        seed_fixture_path="tests/fixtures/mysql/seed.sql",
        is_connection_based=True,
    ),
    AdapterConformanceProfile(
        dialect=SQLDatabaseDialect.SQLSERVER,
        adapter_module_name="app.evaluation.mssql_execution_adapter",
        adapter_factory=MSSQLDatabaseExecutionAdapter,
        inert_adapter_factory=_inert(MSSQLDatabaseExecutionAdapter),
        resolver=_resolve_mssql,
        driver_module_name="pymssql",
        pytest_marker="sqlserver",
        expected_capabilities=frozenset({_CAP.CONNECTION_REF, _CAP.READ_ONLY}),
        accepts_explain_only=False,
        case_fold=CaseFold.LOWER,
        seed_fixture_path="tests/fixtures/mssql/seed.sql",
        is_connection_based=True,
    ),
)


def profiles_for(*, connection_based: Optional[bool] = None) -> Tuple[AdapterConformanceProfile, ...]:
    if connection_based is None:
        return CONFORMANCE_PROFILES
    return tuple(p for p in CONFORMANCE_PROFILES if p.is_connection_based == connection_based)
