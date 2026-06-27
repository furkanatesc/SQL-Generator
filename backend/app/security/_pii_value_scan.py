"""Shared PII/PHI value-format scan (Sprint 26.9 refactor of Sprint 26.5).

Canonical home for the value-format heuristics (email / SSN / IBAN / phone +
Luhn-gated credit cards) and the PII/PHI category / confidence / data-class
enums. Sprint 26.5 (``sql_pii_phi_detection``) scans the raw SQL string with
these; Sprint 26.9 (``result_set_privacy_limits``) scans returned result-set
cell values with the same logic. Extracted here so both reuse one
implementation. 26.5 re-exports every symbol below, so its public API is
unchanged (behavior-preserving). This module is a dependency-free leaf (no
import of ``sql_pii_phi_detection``) to avoid an import cycle.

Value-free by design: ``scan_value_categories`` returns only
(category, confidence) pairs — never the matched substring. Performs no I/O.
"""

import re
from enum import Enum
from typing import Dict, List, Tuple


class SQLDataClass(str, Enum):
    PII = "pii"   # personal data
    PHI = "phi"   # protected health information (HIPAA-style)


class SQLPiiPhiCategory(str, Enum):
    EMAIL = "email"
    PHONE = "phone"
    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    IBAN = "iban"
    DATE_OF_BIRTH = "date_of_birth"
    PERSON_NAME = "person_name"
    POSTAL_ADDRESS = "postal_address"
    MEDICAL_RECORD_NUMBER = "medical_record_number"
    DIAGNOSIS = "diagnosis"
    HEALTH_GENERIC = "health_generic"


class SQLPiiPhiConfidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Each category's data class (PII vs PHI).
_CATEGORY_DATA_CLASS: Dict[SQLPiiPhiCategory, SQLDataClass] = {
    SQLPiiPhiCategory.EMAIL: SQLDataClass.PII,
    SQLPiiPhiCategory.PHONE: SQLDataClass.PII,
    SQLPiiPhiCategory.SSN: SQLDataClass.PII,
    SQLPiiPhiCategory.CREDIT_CARD: SQLDataClass.PII,
    SQLPiiPhiCategory.IBAN: SQLDataClass.PII,
    SQLPiiPhiCategory.DATE_OF_BIRTH: SQLDataClass.PII,
    SQLPiiPhiCategory.PERSON_NAME: SQLDataClass.PII,
    SQLPiiPhiCategory.POSTAL_ADDRESS: SQLDataClass.PII,
    SQLPiiPhiCategory.MEDICAL_RECORD_NUMBER: SQLDataClass.PHI,
    SQLPiiPhiCategory.DIAGNOSIS: SQLDataClass.PHI,
    SQLPiiPhiCategory.HEALTH_GENERIC: SQLDataClass.PHI,
}

# Confidence ordering (low -> high).
_CONFIDENCE_ORDER: Dict[SQLPiiPhiConfidence, int] = {
    SQLPiiPhiConfidence.LOW: 0,
    SQLPiiPhiConfidence.MEDIUM: 1,
    SQLPiiPhiConfidence.HIGH: 2,
}

# --- value-format detection (best-effort, value-free output) ---

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
# Loose phone: an optional + then a run of digits/space/()-.- at least 9 long.
_PHONE_RE = re.compile(r"(?<![\w.])\+?\d(?:[\d\s().-]{7,})\d(?![\w.])")
# A 13-19 "digit" run allowing single space/dash separators; Luhn-checked after.
_CARD_CANDIDATE_RE = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")


def _luhn_ok(digits: str) -> bool:
    """Standard Luhn checksum. Only 13-19 all-digit strings can pass."""
    if not digits.isdigit() or not (13 <= len(digits) <= 19):
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def scan_value_categories(text: str) -> List[Tuple[SQLPiiPhiCategory, SQLPiiPhiConfidence]]:
    """Value-format PII/PHI detections over an arbitrary string. Deterministic,
    value-free output: (category, confidence) pairs only. This is the logic 26.5
    runs over the raw SQL string, factored out for reuse over result-set cells.

    Over-detection is intentional (a signal, never a gate): e.g. an SSN literal
    also looks like a phone number, so both may be emitted. No matched value is
    ever returned or stored.
    """
    out: List[Tuple[SQLPiiPhiCategory, SQLPiiPhiConfidence]] = []
    if _EMAIL_RE.search(text):
        out.append((SQLPiiPhiCategory.EMAIL, SQLPiiPhiConfidence.MEDIUM))
    if _SSN_RE.search(text):
        out.append((SQLPiiPhiCategory.SSN, SQLPiiPhiConfidence.MEDIUM))
    if _IBAN_RE.search(text):
        out.append((SQLPiiPhiCategory.IBAN, SQLPiiPhiConfidence.MEDIUM))
    for m in _CARD_CANDIDATE_RE.finditer(text):
        if _luhn_ok(re.sub(r"[ -]", "", m.group(0))):
            out.append((SQLPiiPhiCategory.CREDIT_CARD, SQLPiiPhiConfidence.HIGH))
            break
    if _PHONE_RE.search(text):
        out.append((SQLPiiPhiCategory.PHONE, SQLPiiPhiConfidence.LOW))
    return out
