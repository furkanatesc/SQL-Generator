"""Admin dashboard adaptoru (Sprint 27.7).

KIRLI katman: RAW trace store + feedback DB'ye dokunur. Saf birlestirme
app.dashboard icindedir. Hesaplama YAN ETKISIZDIR: yazma yok, trace emit yok, LLM yok.
Dashboard verisi hassas DEGILDIR (sayim + registry kodu + sure + verdict/category)
-> REDAKSIYON YOK. Trace'ler TEK fetch'te cekilir; metrics + timeseries + recent ayni
veriyi paylasir.
"""
from typing import Mapping, Optional

from app.dashboard import DashboardWindow, compose_dashboard
from app.database import list_feedback
from app.trace.query import TraceQuery

END_TO_END_TRACE_TYPE = "end_to_end"
SCAN_CAP = 10000


def build_dashboard(*, trace_store,
                    created_after: Optional[str] = None,
                    created_before: Optional[str] = None,
                    dialect: Optional[str] = None,
                    bucket: str = "day",
                    top_n: int = 10,
                    recent_limit: int = 20,
                    scan_cap: int = SCAN_CAP) -> dict:
    query = TraceQuery(
        trace_type=END_TO_END_TRACE_TYPE, created_after=created_after,
        created_before=created_before, dialect=dialect, limit=scan_cap + 1)
    rows = list(trace_store.list_traces(query) or [])   # store hatasi YUTULMAZ

    truncated = len(rows) > scan_cap
    rows = rows[:scan_cap]

    trace_items = []
    for r in rows:
        if isinstance(r, Mapping):
            payload = r.get("payload")
            created_at = r.get("created_at")
        else:
            payload = getattr(r, "payload", None)
            created_at = getattr(r, "created_at", None)
        if isinstance(payload, Mapping):
            trace_items.append((created_at, payload))

    # feedback DB hatasi da YUTULMAZ.
    feedback_rows = list_feedback(created_after=created_after,
                                  created_before=created_before, limit=scan_cap + 1)
    feedback_truncated = len(feedback_rows) > scan_cap
    feedback_rows = feedback_rows[:scan_cap]

    window_base = DashboardWindow(
        created_after=created_after, created_before=created_before, dialect=dialect,
        trace_count=len(trace_items), truncated=truncated, scan_cap=scan_cap,
        bucket=bucket, timeseries_truncated=False, feedback_truncated=feedback_truncated)

    return compose_dashboard(
        trace_items=trace_items, feedback_rows=feedback_rows, window_base=window_base,
        bucket=bucket, top_n=top_n, recent_limit=recent_limit).to_payload()
