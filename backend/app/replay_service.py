"""Query replay adaptoru (Sprint 27.4).

KIRLI katman: DB, trace store ve pipeline'a dokunur. Saf karar mantigi
app.replay icindedir. Replay YAN ETKISIZDIR: hicbir sey yazilmaz, hicbir
trace emit edilmez, LLM'e gidilmez.
"""
import os
from typing import Any, Mapping, Optional, Tuple

from app.database import get_job
from app.replay import (
    ReplayObserved,
    ReplayResult,
    compare_replay,
    extract_baseline,
)
from app.trace.query import TraceQuery

END_TO_END_TRACE_TYPE = "end_to_end"

# Guvenlik reddi bu stage'lerden gelir (live_trace_assembly ile ayni set).
_SECURITY_STAGES = frozenset({"sql_guardrail", "sql_sandbox_safety"})


class ReplayJobNotFound(Exception):
    """Istenen job kaydi yok. Bu bir replay sonucu DEGIL, kaynak hatasidir."""


def _latest_baseline_payload(trace_store, job_id: str) -> Optional[Mapping[str, Any]]:
    """job_id'nin en yeni end_to_end trace payload'ini dondurur.

    Store hatasi BILINCLI OLARAK yutulmaz: bir debug aracinin hatayi yutup
    "baseline yok" demesi yanlis sinyal verir; exception yukari cikar ve
    500 envelope'a doner (spec §5).
    """
    records = trace_store.list_traces(
        TraceQuery(limit=1, job_id=job_id, trace_type=END_TO_END_TRACE_TYPE))
    for record in records or ():
        payload = getattr(record, "payload", None)
        if isinstance(payload, Mapping) and payload:
            return payload
    return None


def _input_available(job: Mapping[str, Any]) -> bool:
    """Uretimde `_stage_intent` excel_file_path'i natural_query'ye onceler
    (bkz. sql_pipeline.py `if excel_file_path: ... elif natural_query: ...`).
    Bu yuzden file_path doluysa uretimin kostugu yol excel dalidir; dosya
    diskte yoksa o yol natural_query dolu olsa bile yeniden uretilemez.
    """
    file_path = job.get("file_path")
    if file_path:
        return os.path.exists(file_path)
    return bool(job.get("natural_query"))


def _split_issue_types(errors) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """Uretim hata sozluklerini (anahtar: "type") dogrulama/guvenlik eksenlerine ayirir."""
    validation, security = set(), set()
    for err in errors or ():
        if not isinstance(err, Mapping):
            continue
        code = err.get("type")
        if code is None:
            continue
        if err.get("stage") in _SECURITY_STAGES:
            security.add(str(code))
        else:
            validation.add(str(code))
    return tuple(sorted(validation)), tuple(sorted(security))


def replay_job(job_id: str, *, pipeline, trace_store) -> ReplayResult:
    """Gecmis bir job'i bugunun koduyla deterministik olarak yeniden kosar."""
    job = get_job(job_id)
    if job is None:
        raise ReplayJobNotFound(job_id)

    baseline_payload = _latest_baseline_payload(trace_store, job_id)
    baseline = extract_baseline(baseline_payload)

    notes = []

    if not _input_available(job):
        return compare_replay(
            job_id=job_id, baseline=baseline,
            observed=ReplayObserved(
                input_available=False,
                notes=("job girdisi artik erisilebilir degil (natural_query bos, "
                       "file_path yok ya da silinmis)",)))

    dialect = job.get("dialect") or "postgres"
    natural_query = job.get("natural_query")
    excel_file_path = job.get("file_path")

    # Uretim gibi ikisini de gecir; onceligi _stage_intent'e birak
    # (bkz. sql_pipeline.py: `if excel_file_path: ... elif natural_query: ...`).
    aqr, intent_error, _ = pipeline._stage_intent(
        excel_file_path=excel_file_path, natural_query=natural_query,
        log_callback=None)
    if intent_error:
        return compare_replay(
            job_id=job_id, baseline=baseline,
            observed=ReplayObserved(
                retrieval_error_code=str(intent_error.get("error_type")),
                notes=("girdi yorumlama bugun hata verdi",)))

    pruned_schema, _ctx, selection_trace, retrieval_error, _ = pipeline._stage_retrieval(
        aqr=aqr, natural_query=natural_query, dialect=dialect, log_callback=None)
    if retrieval_error:
        return compare_replay(
            job_id=job_id, baseline=baseline,
            observed=ReplayObserved(
                retrieval_error_code=str(retrieval_error.get("error_type")),
                notes=("retrieval bugun hata verdi",)))

    observed_tables = tuple(sorted(
        (selection_trace or {}).get("selected_tables")
        or list((pruned_schema or {}).get("tables", {}).keys())))

    result_sql = job.get("result_sql")
    if not result_sql:
        notes.append("job'un result_sql'i bos — dogrulama boyutu karsilastirilamaz")
        observed = ReplayObserved(
            retrieval_tables=observed_tables, notes=tuple(notes))
        return compare_replay(job_id=job_id, baseline=baseline, observed=observed)

    outcome = pipeline.validate_sql(result_sql, pruned_schema, dialect,
                                    log_callback=None)
    validation_types, security_types = _split_issue_types(outcome.validation_errors)

    # Baseline ile AYNI eksen tanimi (live_trace_assembly.py:152-160):
    # yalniz guvenlik nedeniyle reddedilen SQL, dogrulama ekseninde basarisiz SAYILMAZ.
    observed_validation_valid = bool(outcome.valid or security_types)

    observed = ReplayObserved(
        retrieval_tables=observed_tables,
        validation_valid=observed_validation_valid,
        validation_issue_types=validation_types,
        security_denied=security_types,
        notes=tuple(notes))
    return compare_replay(job_id=job_id, baseline=baseline, observed=observed)
