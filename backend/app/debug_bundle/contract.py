"""Debug bundle sozlesmesi — frozen record'lar (Sprint 27.5).

to_payload() JSON-safe'tir: tuple'lar listeye doner, enum tasinmaz. Ayni girdi
her zaman ayni payload'i uretir (determinizm). Duvar-saati YOKTUR.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Tuple

BUNDLE_CONTRACT_VERSION = "debug_bundle_v1"


@dataclass(frozen=True)
class BundleJobInfo:
    status: Optional[str] = None
    dialect: Optional[str] = None
    error_code: Optional[str] = None
    has_natural_query: bool = False
    has_excel_input: bool = False
    result_sql_present: bool = False

    def to_payload(self) -> dict:
        return {
            "status": self.status,
            "dialect": self.dialect,
            "error_code": self.error_code,
            "has_natural_query": self.has_natural_query,
            "has_excel_input": self.has_excel_input,
            "result_sql_present": self.result_sql_present,
        }


@dataclass(frozen=True)
class BundleSqlInfo:
    generated_sql: Optional[str] = None
    last_generated_sql: Optional[str] = None
    sql_valid: Optional[bool] = None
    attempts: Tuple[Any, ...] = ()
    sql_validation_errors: Tuple[Any, ...] = ()

    def to_payload(self) -> dict:
        return {
            "generated_sql": self.generated_sql,
            "last_generated_sql": self.last_generated_sql,
            "sql_valid": self.sql_valid,
            "attempts": list(self.attempts),
            "sql_validation_errors": list(self.sql_validation_errors),
        }


@dataclass(frozen=True)
class BundleSchemaInfo:
    selected_tables: Tuple[str, ...] = ()
    schema_hash: Optional[str] = None
    table_count: int = 0

    def to_payload(self) -> dict:
        return {
            "selected_tables": list(self.selected_tables),
            "schema_hash": self.schema_hash,
            "table_count": self.table_count,
        }


@dataclass(frozen=True)
class BundleMeta:
    bundle_contract_version: str
    replay_contract_version: Optional[str] = None
    trace_contract_version: Optional[str] = None
    dialect: Optional[str] = None

    def to_payload(self) -> dict:
        return {
            "bundle_contract_version": self.bundle_contract_version,
            "replay_contract_version": self.replay_contract_version,
            "trace_contract_version": self.trace_contract_version,
            "dialect": self.dialect,
        }


@dataclass(frozen=True)
class DebugBundle:
    version: str
    job_id: str
    job: BundleJobInfo
    trace: Optional[Mapping[str, Any]] = None      # zaten-redakte end_to_end payload
    sql: Optional[BundleSqlInfo] = None
    replay: Optional[Mapping[str, Any]] = None      # ReplayResult.to_payload()
    schema: Optional[BundleSchemaInfo] = None
    meta: Optional[BundleMeta] = None

    def to_payload(self) -> dict:
        return {
            "version": self.version,
            "job_id": self.job_id,
            "job": self.job.to_payload(),
            "trace": None if self.trace is None else dict(self.trace),
            "sql": None if self.sql is None else self.sql.to_payload(),
            "replay": None if self.replay is None else dict(self.replay),
            "schema": None if self.schema is None else self.schema.to_payload(),
            "meta": None if self.meta is None else self.meta.to_payload(),
        }
