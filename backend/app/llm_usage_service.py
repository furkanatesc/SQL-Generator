"""LLM usage/cost adaptoru (Sprint 27.8).

KIRLI katman: RAW trace store + configs DB'ye dokunur. Saf birlestirme
app.llm_usage icindedir. Hesaplama YAN ETKISIZDIR: yazma yok, trace emit yok, LLM yok.
Kullanim/maliyet hassas DEGILDIR -> REDAKSIYON YOK. Trace'ler TEK fetch'te cekilir.
Fiyat tablosu configs DB'deki 'llm_pricing' JSON'undan okunur (gecersiz -> bos tablo).
Store/config hatasi YUTULMAZ.
"""
from typing import Mapping, Optional

from app.database import get_config
from app.llm_usage import UsageWindow, compute_llm_usage
from app.llm_usage.pricing import parse_price_table
from app.trace.query import TraceQuery

END_TO_END_TRACE_TYPE = "end_to_end"
SCAN_CAP = 10000
PRICING_CONFIG_KEY = "llm_pricing"


def build_llm_usage(*, trace_store,
                    created_after: Optional[str] = None,
                    created_before: Optional[str] = None,
                    bucket: str = "day",
                    scan_cap: int = SCAN_CAP) -> dict:
    query = TraceQuery(
        trace_type=END_TO_END_TRACE_TYPE, created_after=created_after,
        created_before=created_before, limit=scan_cap + 1)
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

    currency, price_table = parse_price_table(get_config(PRICING_CONFIG_KEY))

    window = UsageWindow(
        created_after=created_after, created_before=created_before, bucket=bucket,
        trace_count=len(trace_items), generation_count=0, truncated=truncated,
        scan_cap=scan_cap, timeseries_truncated=False)

    return compute_llm_usage(
        trace_items=trace_items, window=window, currency=currency,
        price_table=price_table, bucket=bucket).to_payload()
