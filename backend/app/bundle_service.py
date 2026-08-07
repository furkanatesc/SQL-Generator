"""Debug bundle adaptoru (Sprint 27.5).

KIRLI katman: DB, trace store, pipeline ve debug-trace adaptorune dokunur. Saf
birlestirme app.debug_bundle icindedir. Export YAN ETKISIZDIR: hicbir sey
yazilmaz, trace emit edilmez, LLM'e gidilmez.

Iki trace turu (§3.1a):
- end_to_end trace  -> `trace` + `schema` (secret-free; yine de redaksiyondan gecer)
- debug trace       -> `sql` (serialize_trace_for_debug ile REDAKTE gelir)
"""
from typing import Any, Mapping, Optional

from app.database import get_job
from app.debug_bundle import compose_bundle
from app.replay_service import replay_job
from app.trace.debug_api import DebugTraceAdapter
from app.trace.query import TraceQuery
from app.trace.redaction import redact_sensitive, redact_sensitive_dict

END_TO_END_TRACE_TYPE = "end_to_end"
DEBUG_TRACE_TYPE = "nl2sql"


class BundleJobNotFound(Exception):
    """Istenen job kaydi yok. Kaynak hatasidir."""


def _latest_end_to_end_payload(trace_store, job_id: str) -> Optional[Mapping[str, Any]]:
    """job_id'nin en yeni end_to_end trace payload'i. Store hatasi YUTULMAZ."""
    records = trace_store.list_traces(
        TraceQuery(limit=1, job_id=job_id, trace_type=END_TO_END_TRACE_TYPE))
    for record in records or ():
        payload = record["payload"] if isinstance(record, Mapping) else getattr(record, "payload", None)
        if isinstance(payload, Mapping) and payload:
            return payload
    return None


def _latest_debug_trace(trace_store, job_id: str) -> Optional[Mapping[str, Any]]:
    """SQL tasiyan debug trace (trace_type=nl2sql), serialize_trace_for_debug ile
    REDAKTE gelir. Yoksa None."""
    adapter = DebugTraceAdapter(trace_store)
    rows = adapter.list_traces(TraceQuery(trace_type=DEBUG_TRACE_TYPE, job_id=job_id, limit=1))
    for row in rows or ():
        return row
    return None


def build_bundle(job_id: str, *, trace_store, pipeline) -> dict:
    job = get_job(job_id)
    if job is None:
        raise BundleJobNotFound(job_id)

    e2e_payload = _latest_end_to_end_payload(trace_store, job_id)
    redacted_trace = None
    if e2e_payload is not None:
        # end_to_end secret-free'dir; iki-gecis redaksiyon EK guvence (§3.5).
        redacted_trace = redact_sensitive(redact_sensitive_dict(dict(e2e_payload)))

    redacted_debug_trace = _latest_debug_trace(trace_store, job_id)

    replay_payload = replay_job(job_id, pipeline=pipeline, trace_store=trace_store).to_payload()

    bundle = compose_bundle(
        job=job,
        redacted_trace_payload=redacted_trace,
        redacted_debug_trace_payload=redacted_debug_trace,
        replay_payload=replay_payload,
        dialect=job.get("dialect") or "postgres",
    )
    return bundle.to_payload()
