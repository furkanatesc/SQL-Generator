"""Sprint 29.7 — Adapter Conformance Eval Suite.

A single, declarative source of truth for what it means for a database execution
adapter to conform to the shared ``SQLDatabaseExecutionAdapter`` contract. This
module is IMPORT-SAFE: importing it loads NO database driver. Driver names are
recorded only as strings; the deterministic conformance core uses inert adapters
(a resolver that returns ``None``) so nothing ever connects.
"""
from __future__ import annotations

import argparse
import json
import sys as _sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, FrozenSet, Optional, Tuple

from app.evaluation.multi_database_execution import (
    SQLDatabaseDialect,
    SQLDatabaseExecutionAdapter,
    SQLDatabaseExecutionConfig,
    SQLDatabaseExecutionRequest,
    SQLDatabaseExecutionRouter,
    SQLExecutionAdapterCapability,
    SQLExecutionMode,
    SQLiteDatabaseExecutionAdapter,
    SQLMultiDatabaseExecutionContractError,
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


def _benign_request(dialect, *, explain: bool = False) -> "SQLDatabaseExecutionRequest":
    cfg = SQLDatabaseExecutionConfig(
        dialect=dialect,
        execution_mode=SQLExecutionMode.EXPLAIN_ONLY if explain else SQLExecutionMode.READ_ONLY,
    )
    return SQLDatabaseExecutionRequest(
        case_id="conformance", sql="SELECT 1", dialect=dialect,
        fixture_ref=None, connection_ref="local_docker", config=cfg,
    )


def assert_contract_conformance(profile: AdapterConformanceProfile) -> list:
    """Return a list of contract-conformance violations (empty == conformant).

    Docker-free: connection-based adapters are exercised through an inert
    resolver (returns ``None``) so nothing ever connects.
    """
    violations = []
    adapter = profile.adapter_factory()

    if adapter.dialect != profile.dialect:
        violations.append(f"dialect property {adapter.dialect} != profile {profile.dialect}")

    caps = adapter.capabilities()
    if set(caps) != profile.expected_capabilities:
        violations.append(
            f"capabilities {sorted(c.value for c in caps)} != expected "
            f"{sorted(c.value for c in profile.expected_capabilities)}"
        )
    if len(caps) != len(set(caps)):
        violations.append("capabilities contains duplicates")

    try:
        SQLDatabaseExecutionRouter(adapters=(adapter,))
    except SQLMultiDatabaseExecutionContractError as exc:  # pragma: no cover - defensive
        violations.append(f"adapter rejected by router: {exc}")

    if profile.is_connection_based:
        inert = profile.inert_adapter_factory()

        res = inert.execute(_benign_request(profile.dialect))
        if res.rows != () or res.row_count != 0:
            violations.append("inert adapter returned rows for a no-connection request")
        if not res.execution_error:
            violations.append("inert adapter did not set execution_error on no-connection")

        explain_req = _benign_request(profile.dialect, explain=True)
        if profile.accepts_explain_only:
            try:
                inert.execute(explain_req)
            except SQLMultiDatabaseExecutionContractError:
                violations.append("adapter advertises EXPLAIN_ONLY but rejected an explain request")
        else:
            try:
                inert.execute(explain_req)
                violations.append("adapter does not advertise EXPLAIN_ONLY but accepted an explain request")
            except SQLMultiDatabaseExecutionContractError:
                pass

    return violations


def contract_conformance_report(profile: AdapterConformanceProfile) -> dict:
    violations = assert_contract_conformance(profile)
    return {
        "dialect": profile.dialect.value,
        "capabilities": sorted(c.value for c in profile.expected_capabilities),
        "accepts_explain_only": profile.accepts_explain_only,
        "case_fold": profile.case_fold.value,
        "is_connection_based": profile.is_connection_based,
        "driver": profile.driver_module_name,
        "contract_conformance": {"ok": not violations, "violations": violations},
    }


def build_conformance_report() -> dict:
    return {
        "version": SQL_ADAPTER_CONFORMANCE_VERSION,
        "dialects": [contract_conformance_report(p) for p in CONFORMANCE_PROFILES],
    }


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="adapter_conformance")
    sub = parser.add_subparsers(dest="command", required=True)
    rep = sub.add_parser("report", help="Emit the Docker-free conformance/capability snapshot")
    rep.add_argument("--json", action="store_true", help="Emit JSON (default: short human summary)")
    rep.add_argument("--output", default=None, help="Write to PATH instead of stdout")
    args = parser.parse_args(argv)

    if args.command == "report":
        report = build_conformance_report()
        if args.json:
            text = json.dumps(report, indent=2, sort_keys=True)
        else:
            lines = [f"adapter conformance ({report['version']}):"]
            for d in report["dialects"]:
                ok = "OK" if d["contract_conformance"]["ok"] else "FAIL"
                lines.append(
                    f"  {d['dialect']:<11} caps={','.join(d['capabilities'])} "
                    f"explain_only={d['accepts_explain_only']} {ok}"
                )
            text = "\n".join(lines)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(text)
        else:
            print(text)
        return 0
    return 1  # pragma: no cover - argparse requires a subcommand


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(_sys.argv[1:]))
