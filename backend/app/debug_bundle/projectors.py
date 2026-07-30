"""Debug bundle allow-list projektorleri (Sprint 27.5).

TAMAMEN SAF: I/O yok, redaksiyon yok (girdi zaten-redakte gelir, §3.1a).
Her projektor YALNIZ beyaz-listeli alanlari emit eder; yeni bir alan varsayilan
olarak disarida kalir (sizinti riski minimum).
"""
from typing import Any, Mapping, Optional

from app.debug_bundle.contract import (
    BUNDLE_CONTRACT_VERSION, BundleJobInfo, BundleMeta, BundleSchemaInfo,
    BundleSqlInfo,
)

_SQL_FIELDS = ("generated_sql", "last_generated_sql", "sql_valid",
               "attempts", "sql_validation_errors")


def project_job(job: Mapping[str, Any]) -> BundleJobInfo:
    return BundleJobInfo(
        status=job.get("status"),
        dialect=job.get("dialect"),
        error_code=job.get("error_code"),
        has_natural_query=bool(job.get("natural_query")),
        has_excel_input=bool(job.get("file_path")),
        result_sql_present=bool(job.get("result_sql")),
    )


def _dig(payload: Mapping[str, Any], key: str) -> Any:
    # serialize_trace_for_debug hem root'a yansitir hem "payload" altinda tutar.
    if key in payload:
        return payload[key]
    inner = payload.get("payload")
    if isinstance(inner, Mapping):
        return inner.get(key)
    return None


def project_sql(redacted_debug_trace_payload: Optional[Mapping[str, Any]]
                ) -> Optional[BundleSqlInfo]:
    if not redacted_debug_trace_payload:
        return None
    p = redacted_debug_trace_payload
    if not any(_dig(p, k) is not None for k in _SQL_FIELDS):
        return None
    attempts = _dig(p, "attempts") or ()
    errors = _dig(p, "sql_validation_errors") or ()
    return BundleSqlInfo(
        generated_sql=_dig(p, "generated_sql"),
        last_generated_sql=_dig(p, "last_generated_sql"),
        sql_valid=_dig(p, "sql_valid"),
        attempts=tuple(attempts),
        sql_validation_errors=tuple(errors),
    )


def project_schema(trace_payload: Optional[Mapping[str, Any]],
                   replay_payload: Optional[Mapping[str, Any]]
                   ) -> Optional[BundleSchemaInfo]:
    selected = ()
    schema_hash = None
    if trace_payload:
        spans = trace_payload.get("spans") or []
        for s in spans:
            if s.get("stage") != "retrieval":
                continue
            detail = s.get("detail") or {}
            cands = detail.get("candidates") or []
            tables = {c.get("object_id") for c in cands
                      if c.get("object_type") == "table" and c.get("object_id")}
            selected = tuple(sorted(tables))
            for c in cands:
                if c.get("schema_hash"):
                    schema_hash = c["schema_hash"]
                    break
    if not selected and replay_payload:
        retr = replay_payload.get("retrieval") or {}
        selected = tuple(retr.get("observed_tables") or ())
    if not selected and schema_hash is None:
        return None
    return BundleSchemaInfo(selected_tables=selected, schema_hash=schema_hash,
                            table_count=len(selected))


def project_meta(trace_payload: Optional[Mapping[str, Any]],
                 replay_payload: Optional[Mapping[str, Any]],
                 dialect: Optional[str]) -> BundleMeta:
    # trace_contract_version IMPORT edilmez; payload'in "version" alanindan okunur
    # (END_TO_END_TRACE_CONTRACT_VERSION'i import etmek app/trace/__init__'i tetikler).
    trace_ver = (trace_payload or {}).get("version")
    replay_ver = (replay_payload or {}).get("version")
    return BundleMeta(
        bundle_contract_version=BUNDLE_CONTRACT_VERSION,
        replay_contract_version=replay_ver,
        trace_contract_version=trace_ver,
        dialect=dialect,
    )
