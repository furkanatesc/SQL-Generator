"""Debug bundle saf birlestirici (Sprint 27.5).

I/O yok. Girdiler ZATEN-REDAKTE gelir (kirli adaptor redakte eder, §3.1a).
Ayni girdi -> ayni DebugBundle.to_payload() (determinizm).
"""
from typing import Any, Mapping, Optional

from app.debug_bundle.contract import BUNDLE_CONTRACT_VERSION, DebugBundle
from app.debug_bundle.projectors import (
    project_job, project_meta, project_schema, project_sql,
)


def compose_bundle(*, job: Mapping[str, Any],
                   redacted_trace_payload: Optional[Mapping[str, Any]],
                   redacted_debug_trace_payload: Optional[Mapping[str, Any]],
                   replay_payload: Optional[Mapping[str, Any]],
                   dialect: Optional[str]) -> DebugBundle:
    return DebugBundle(
        version=BUNDLE_CONTRACT_VERSION,
        job_id=str(job.get("id")),
        job=project_job(job),
        trace=redacted_trace_payload,
        sql=project_sql(redacted_debug_trace_payload),
        replay=replay_payload,
        schema=project_schema(redacted_trace_payload, replay_payload),
        meta=project_meta(redacted_trace_payload, replay_payload, dialect),
    )
