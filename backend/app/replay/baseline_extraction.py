"""end_to_end trace payload'indan baseline cikarimi (Sprint 27.4).

SAF: girdi bir dict'tir, I/O yoktur, EndToEndTrace nesnesi KURULMAZ.
Stage ve status literal'leri (asagida tanimli _STAGE_* ve _SKIPPED sabitler)
BILINÇLI OLARAK yereldir: app.trace.end_to_end_trace import etmek sqlite3 +
19 app modülü çekebilir (import esleme yan etki), bu safligi bozer.
Tek dogru basarili sabit kaynagi app/trace/end_to_end_trace.py'deki TraceStageKind
ve TraceSpanStatus'tur; burada degisiklik varsa bu literal'ler de güncellenmelidir.

app.errors ISTISNA OLARAK izinlidir (bkz. test_replay_package_purity.py):
olculdu — app.errors yaprak katmandir, yalniz kendi alt modullerini
(categories/codes/registry) ceker, hicbir driver/framework (sqlite3, psycopg,
sqlglot, fastapi, pydantic...) yuklemez. app.trace ise hala YASAKTIR: paketin
__init__'i canli pipeline'in tum bagimliliklarini eager import eder (sqlite3 +
19 app modulu), bu da bu katmanin safligini bozar.

Sprint 27.4 merge-kapisi bulgusu: SECURITY ekseni eskiden STAGE adina
("sql_guardrail"/"sql_sandbox_safety" icinde miydi) bakiyordu. Ama bir stage
guvenlik-disi bir kod da uretebilir — ör. guardrail asamasi bozuk SQL'i
`sql_parse_error` ile reddeder, bu VALIDATION kategorisidir, guvenlik reddi
DEGILDIR. LLM ilk denemede bozuk SQL uretip ikinci denemede duzeltirse, baseline
SECURITY span'inde bu gecici `sql_parse_error` kalir (tum attempt'lerin
birlesimi — bkz. live_trace_assembly.py:90-92) ve replay hicbir sey
degismemisken "security_recovery" verdict'i uretir. Duzeltme: guvenlik ekseni
artik 27.2 registry'sinin KATEGORISINE bakar (kod DOGASI, sabit), stage'e degil
(calisma zamani verisi). Registry'de olmayan/bos reason_code'lar (fallback
`category` dahil) MUHAFAZAKAR sekilde guvenlik ekseninde TUTULUR — gercek bir
reddi asla dusurmemek icin.
"""
from typing import Any, Mapping, Optional

from app.errors import DESCRIPTORS, ErrorCategory, codes_for_category
from app.replay.contract import ReplayBaseline

_STAGE_RETRIEVAL = "retrieval"
_STAGE_VALIDATION = "validation"
_STAGE_SECURITY = "security"
_SKIPPED = "skipped"

_SECURITY_CODES = frozenset(str(code) for code in codes_for_category(ErrorCategory.SECURITY))
_KNOWN_CODES = frozenset(str(code) for code in DESCRIPTORS)


def _belongs_to_security_axis(reason_code: str) -> bool:
    """Bir denied check'in reason_code'u guvenlik eksenine mi ait?

    Kural MUHAFAZAKAR: bilinen ve guvenlik-disi bir registry kodu ise DUSUR
    (ör. sql_parse_error -> validation); guvenlik kategorisindeyse ya da
    registry'de hic yoksa/bos ise (fallback category adina dusulen hal dahil)
    TUT — gercek bir reddi asla sessizce kaybetmemek icin.
    """
    if reason_code in _SECURITY_CODES:
        return True
    if reason_code in _KNOWN_CODES:
        return False
    return True


def _spans_by_stage(payload: Mapping[str, Any]) -> dict:
    by_stage = {}
    for span in payload.get("spans") or ():
        if isinstance(span, Mapping) and span.get("stage"):
            by_stage[span["stage"]] = span
    return by_stage


def _measured(span: Optional[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    """Span yoksa ya da SKIPPED ise None — o boyut o gun olculmemistir."""
    if span is None or span.get("status") == _SKIPPED:
        return None
    return span


def _detail(span: Mapping[str, Any]) -> Mapping[str, Any]:
    detail = span.get("detail")
    return detail if isinstance(detail, Mapping) else {}


def extract_baseline(
    trace_payload: Optional[Mapping[str, Any]],
) -> Optional[ReplayBaseline]:
    """end_to_end payload'indan ReplayBaseline uretir; payload bossa None."""
    if not trace_payload:
        return None

    by_stage = _spans_by_stage(trace_payload)

    retrieval_tables = None
    retrieval = _measured(by_stage.get(_STAGE_RETRIEVAL))
    if retrieval is not None:
        candidates = _detail(retrieval).get("candidates") or ()
        retrieval_tables = tuple(sorted({
            str(c["object_id"])
            for c in candidates
            if isinstance(c, Mapping)
            and c.get("object_type") == "table"
            and c.get("object_id")
        }))

    validation_valid = None
    validation_issue_types = None
    validation = _measured(by_stage.get(_STAGE_VALIDATION))
    if validation is not None:
        detail = _detail(validation)
        validation_valid = bool(detail.get("valid"))
        # DIKKAT: trace tarafinda alan adi "category" (ValidationIssue.category);
        # uretim pipeline'inin hata sozlugunde ayni eksen "type" olarak gecer.
        validation_issue_types = tuple(sorted({
            str(i["category"])
            for i in (detail.get("issues") or ())
            if isinstance(i, Mapping) and i.get("category")
        }))

    security_denied = None
    security = _measured(by_stage.get(_STAGE_SECURITY))
    if security is not None:
        denied_codes = {
            str(c.get("reason_code") or c.get("category") or "denied")
            for c in (_detail(security).get("checks") or ())
            if isinstance(c, Mapping) and c.get("outcome") == "denied"
        }
        security_denied = tuple(sorted(
            code for code in denied_codes if _belongs_to_security_axis(code)))

    return ReplayBaseline(
        trace_id=trace_payload.get("trace_id"),
        terminal_status=trace_payload.get("terminal_status"),
        retrieval_tables=retrieval_tables,
        validation_valid=validation_valid,
        validation_issue_types=validation_issue_types,
        security_denied=security_denied,
    )
