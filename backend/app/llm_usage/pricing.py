"""LLM fiyat tablosu ayristirma + maliyet — SAF (Sprint 27.8).

parse_price_table configs DB'deki 'llm_pricing' JSON string'ini toleransli ayristirir:
gecersiz/eksik girdi -> bos tablo (cost null, kullanim yine gercek). I/O yok.
"""
import json
from typing import Optional, Tuple

DEFAULT_CURRENCY = "USD"


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def parse_price_table(raw: Optional[str]) -> Tuple[str, dict]:
    if not raw:
        return DEFAULT_CURRENCY, {}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return DEFAULT_CURRENCY, {}
    if not isinstance(data, dict):
        return DEFAULT_CURRENCY, {}
    currency = data.get("currency")
    if not isinstance(currency, str) or not currency:
        currency = DEFAULT_CURRENCY
    table: dict = {}
    models = data.get("models")
    if isinstance(models, dict):
        for model_id, price in models.items():
            if not isinstance(model_id, str) or not isinstance(price, dict):
                continue
            inp = price.get("input_per_1m")
            out = price.get("output_per_1m")
            if _is_number(inp) and _is_number(out):
                table[model_id] = {"input_per_1m": float(inp), "output_per_1m": float(out)}
    return currency, table


def cost_for(prompt_tokens, completion_tokens, price: Optional[dict]) -> Optional[float]:
    """Model basi tahmini maliyet. price None -> None (fiyatsiz). None token -> 0 sayilir."""
    if price is None:
        return None
    p = prompt_tokens if _is_number(prompt_tokens) else 0
    c = completion_tokens if _is_number(completion_tokens) else 0
    return round(p / 1e6 * price["input_per_1m"] + c / 1e6 * price["output_per_1m"], 6)
