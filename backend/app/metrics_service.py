"""Metrics adaptoru (Sprint 27.6).

KIRLI katman: RAW trace store'a dokunur. Saf aggregation app.metrics icindedir.
Hesaplama YAN ETKISIZDIR: hicbir sey yazilmaz, trace emit edilmez, LLM'e gidilmez.
Metrikler hassas DEGILDIR (sayim + kapali registry kodu + sure) -> REDAKSIYON YOK.
"""
from typing import Any, Mapping, Optional

from app.metrics import MetricsWindow, compute_metrics
from app.trace.query import TraceQuery

END_TO_END_TRACE_TYPE = "end_to_end"
SCAN_CAP = 10000


def compute_metrics_for_window(*, trace_store,
                               created_after: Optional[str] = None,
                               created_before: Optional[str] = None,
                               dialect: Optional[str] = None,
                               scan_cap: int = SCAN_CAP) -> dict:
    # limit=scan_cap+1: pencere cap'i asiyorsa truncation'i tespit etmek icin.
    query = TraceQuery(
        trace_type=END_TO_END_TRACE_TYPE,
        created_after=created_after, created_before=created_before,
        dialect=dialect, limit=scan_cap + 1)
    rows = list(trace_store.list_traces(query) or [])  # store hatasi YUTULMAZ

    truncated = len(rows) > scan_cap
    rows = rows[:scan_cap]

    payloads = []
    for r in rows:
        payload = r["payload"] if isinstance(r, Mapping) else getattr(r, "payload", None)
        if isinstance(payload, Mapping):
            payloads.append(payload)

    window = MetricsWindow(
        created_after=created_after, created_before=created_before, dialect=dialect,
        trace_count=len(payloads), truncated=truncated, scan_cap=scan_cap)
    return compute_metrics(payloads, window).to_payload()
