"""Sprint 26.5 — PII / PHI Detection Contract (Phase 7: Security & Governance).

Maturity: MVP / early beta. NOT production-ready. This sprint defines a *static*
(no execution) contract that **detects** whether a query plausibly involves personal
data (PII) or protected health information (PHI), reporting *what kind* and *with what
confidence*. Where 26.0 asks "may this run?", 26.1 "right tenant?", 26.2 "is it
read-only?", 26.3 "how risky?", and 26.4 "does it touch a declared-sensitive
resource (and what to do)?", 26.5 asks:

* Does this query plausibly involve PII/PHI, by category, and how confident is that?

It is a **pure signal / detector — NOT a gate.** It returns NO ALLOW/DENY decision
(that is 26.4 / approval 26.7). Like 26.3 (risk classifier), it emits a typed signal
that downstream gates and governance consume (26.4 sensitive-data gate, 26.6 audit,
26.7 approval). Where 26.4 is declaration-based, 26.5 is **heuristic**: it infers
categories from identifier names and literal value formats *without* requiring any
operator declaration. A declared category map is supported as an optional, sound
override; its value is catching PII/PHI the operator never declared.

Three detection layers, each tagged by its source on every match:

* Layer A — declared map (source DECLARED, confidence HIGH): an operator assertion
  that a referenced column holds a given category. Sound.
* Layer B — identifier-name heuristics (source IDENTIFIER_NAME, confidence MEDIUM):
  table/column/identifier *names* matched against per-category name patterns over the
  literal-free executable core (shared ``_sql_text``).
* Layer C — SQL literal-value heuristics (source LITERAL_VALUE, confidence LOW->HIGH):
  value formats (email/SSN/IBAN/phone and Luhn-gated credit cards) scanned over the
  **raw** SQL string — because leaked PII lives inside string literals, which the
  ``_sql_text`` sanitizer masks by design.

Core principle — **secret-free**: the result carries NO raw SQL and NO matched value,
only ``sql_sha256``, categories, and matched identifier *names* (schema metadata the
operator exposed). Literal matches carry no identifier and no value.

Fail behaviour: unusable input (no references and no usable SQL string) yields a
deterministic result with reason ``UNUSABLE_INPUT`` and no detections — the detector
asserts neither presence nor absence (it could not evaluate), rather than a false
"clean".

Out of scope (later sprints / deliberate): any ALLOW/DENY decision (26.4/26.7), audit
persistence (26.6), approval orchestration (26.7), prompt-injection defense (26.8),
result-set/row privacy over *returned data* (26.9 — this sees only SQL, never rows), a
real SQL parser, alias/schema resolution, catalog metadata, locale-specific national
IDs beyond the chosen formats, any I/O, DB/adapter execution, API/UI, tenant/RBAC.
This module performs no I/O.

KNOWN LIMITATIONS (heuristics, no parser; a sound fix needs a parser + catalog/
data-classification metadata and/or value sampling under execution — a later sprint):

* Heuristic in BOTH directions: name/value patterns under-detect (a ``notes`` column
  full of PHI; an unlisted national-ID format) AND over-detect (an ``ip_address``
  column, a non-PII number that passes Luhn by chance, PII-looking text inside a SQL
  comment). It is a **signal, never proof**, and never a gate.
* Identifier extraction is alias-blind, nesting-blind, schema-qualification-blind
  (shares 26.4's limits). **Sound identifier usage = explicit references.**
* Layer C scans the raw SQL, so its regexes may also match inside comments — an
  intentional over-detection bias for a signal; no value is ever stored, so no secret
  leaks regardless.
* Layer C is locale-limited (US SSN; generic email/IBAN/phone; Luhn cards).
"""

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from app.security._sql_text import to_executable_core as _to_executable_core

SQL_PII_PHI_DETECTION_CONTRACT_VERSION = "sql_pii_phi_detection_contract_v1"


class SQLPiiPhiDetectionContractError(ValueError):
    """Raised when PII/PHI detection contract rules are violated."""
    pass


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


class SQLPiiPhiDetectionSource(str, Enum):
    DECLARED = "declared"                 # operator-declared map (sound)
    IDENTIFIER_NAME = "identifier_name"   # name heuristic (best-effort)
    LITERAL_VALUE = "literal_value"       # value-format heuristic (best-effort)


class SQLPiiPhiConfidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SQLPiiPhiReasonCode(str, Enum):
    NO_PII_PHI_DETECTED = "no_pii_phi_detected"
    PII_DETECTED = "pii_detected"
    PHI_DETECTED = "phi_detected"
    UNUSABLE_INPUT = "unusable_input"


class SQLPiiPhiEvaluatedVia(str, Enum):
    EXPLICIT_REFERENCES = "explicit_references"  # caller-supplied identifier lists (sound view)
    SQL_TEXT = "sql_text"                        # heuristics over the SQL string
    NONE = "none"                                # no usable input


# Each category's data class (PII vs PHI). The result's has_phi flag is True iff any
# matched category maps to PHI; PHI dominates the reason code.
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

# Confidence ordering (low -> high). The result's highest_confidence is the MAX.
_CONFIDENCE_ORDER: Dict[SQLPiiPhiConfidence, int] = {
    SQLPiiPhiConfidence.LOW: 0,
    SQLPiiPhiConfidence.MEDIUM: 1,
    SQLPiiPhiConfidence.HIGH: 2,
}


def _normalize_id(value: str) -> str:
    """Canonical form for a table/column identifier: stripped and lower-cased."""
    return value.strip().lower()


@dataclass(frozen=True)
class SQLPiiPhiDeclaration:
    """An optional, trusted, immutable operator assertion that a column holds a given
    PII/PHI category. Trusted config (same stance as 26.4 rules): the category MUST be
    a real enum member; ``resource_id`` must be a non-empty, table-qualified
    (``table.column``) string, normalized to lowercase. A declared match is reported
    at confidence HIGH (an assertion, not a guess). Declarations are optional — an
    empty set still detects heuristically.
    """
    resource_id: str
    category: SQLPiiPhiCategory

    def __post_init__(self):
        if not isinstance(self.category, SQLPiiPhiCategory):
            raise SQLPiiPhiDetectionContractError("category must be a SQLPiiPhiCategory")
        if not isinstance(self.resource_id, str) or not self.resource_id.strip():
            raise SQLPiiPhiDetectionContractError("resource_id must be a non-empty string")
        normalized = _normalize_id(self.resource_id)
        if "." not in normalized:
            raise SQLPiiPhiDetectionContractError(
                "resource_id must be table-qualified (e.g. 'users.ssn')")
        object.__setattr__(self, "resource_id", normalized)


@dataclass(frozen=True)
class SQLPiiPhiMatch:
    """One PII/PHI detection, in a stable, typed, JSON-safe, secret-free audit shape.

    ``identifier`` is the schema name the operator exposed (a table/column name) for
    DECLARED / IDENTIFIER_NAME matches, and ``None`` for LITERAL_VALUE matches (which
    carry no value). Never a query value.
    """
    category: SQLPiiPhiCategory
    data_class: SQLDataClass
    source: SQLPiiPhiDetectionSource
    confidence: SQLPiiPhiConfidence
    identifier: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "data_class": self.data_class.value,
            "source": self.source.value,
            "confidence": self.confidence.value,
            "identifier": self.identifier,
        }


@dataclass(frozen=True)
class SQLPiiPhiDetectionResult:
    """An immutable, audit-grade, secret-free PII/PHI detection signal.

    Carries NO raw SQL and NO matched value — only ``sql_sha256`` (when sql given),
    the detected categories, a ``has_phi`` flag, the max confidence, a reason code +
    human reason, how identifiers were obtained, and the per-match detail (each a
    secret-free ``SQLPiiPhiMatch``). NOT a gate: there is no decision field.
    """
    version: str
    detected: Tuple[SQLPiiPhiMatch, ...]
    categories: Tuple[SQLPiiPhiCategory, ...]
    has_phi: bool
    highest_confidence: Optional[SQLPiiPhiConfidence]
    reason_code: SQLPiiPhiReasonCode
    reason: str
    sql_sha256: Optional[str]
    evaluated_via: SQLPiiPhiEvaluatedVia
    dialect: str

    def __post_init__(self):
        if self.version != SQL_PII_PHI_DETECTION_CONTRACT_VERSION:
            raise SQLPiiPhiDetectionContractError(f"Invalid result version: {self.version}")
        if not isinstance(self.detected, tuple):
            raise SQLPiiPhiDetectionContractError("detected must be a tuple")
        for m in self.detected:
            if not isinstance(m, SQLPiiPhiMatch):
                raise SQLPiiPhiDetectionContractError("each detected entry must be a SQLPiiPhiMatch")
        if not isinstance(self.categories, tuple):
            raise SQLPiiPhiDetectionContractError("categories must be a tuple")
        for c in self.categories:
            if not isinstance(c, SQLPiiPhiCategory):
                raise SQLPiiPhiDetectionContractError("each category must be a SQLPiiPhiCategory")
        if not isinstance(self.has_phi, bool):
            raise SQLPiiPhiDetectionContractError("has_phi must be a bool")
        if self.highest_confidence is not None and not isinstance(self.highest_confidence, SQLPiiPhiConfidence):
            raise SQLPiiPhiDetectionContractError("highest_confidence must be a SQLPiiPhiConfidence or None")
        if not isinstance(self.reason_code, SQLPiiPhiReasonCode):
            raise SQLPiiPhiDetectionContractError("reason_code must be a SQLPiiPhiReasonCode")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise SQLPiiPhiDetectionContractError("reason must be a non-empty string")
        if self.sql_sha256 is not None and (
            not isinstance(self.sql_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", self.sql_sha256)
        ):
            raise SQLPiiPhiDetectionContractError("sql_sha256 must be a lowercase SHA-256 hex digest or None")
        if not isinstance(self.evaluated_via, SQLPiiPhiEvaluatedVia):
            raise SQLPiiPhiDetectionContractError("evaluated_via must be a SQLPiiPhiEvaluatedVia")
        if not isinstance(self.dialect, str) or not self.dialect.strip():
            raise SQLPiiPhiDetectionContractError("dialect must be a non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "detected": [m.to_dict() for m in self.detected],
            "categories": [c.value for c in self.categories],
            "has_phi": self.has_phi,
            "highest_confidence": self.highest_confidence.value if self.highest_confidence is not None else None,
            "reason_code": self.reason_code.value,
            "reason": self.reason,
            "sql_sha256": self.sql_sha256,
            "evaluated_via": self.evaluated_via.value,
            "dialect": self.dialect,
        }


@dataclass(frozen=True)
class SQLPiiPhiDetectionRequest:
    """An immutable PII/PHI detection request.

    Identifier source is hybrid (mirrors 26.4): if ``referenced_tables``/
    ``referenced_columns`` are provided they are used as-is (sound) for the name +
    declared layers; otherwise identifiers are extracted from ``sql`` (best-effort).
    The literal-value layer runs over ``sql`` whenever ``sql`` is a usable string,
    independently of the identifier source. ``sql`` is typed ``str`` but intentionally
    NOT type-checked here, so a non-string yields a deterministic fail-closed result
    from ``detect()`` rather than raising at construction.
    """
    version: str
    sql: Optional[str] = None
    referenced_tables: Optional[Sequence[str]] = None
    referenced_columns: Optional[Sequence[str]] = None
    dialect: str = "generic"

    def __post_init__(self):
        if self.version != SQL_PII_PHI_DETECTION_CONTRACT_VERSION:
            raise SQLPiiPhiDetectionContractError(f"Invalid request version: {self.version}")
        if not isinstance(self.dialect, str) or not self.dialect.strip():
            raise SQLPiiPhiDetectionContractError("dialect must be a non-empty string")


# --- Layer B: identifier extraction + name-pattern detection (best-effort) ---

_IDENT = r"[A-Za-z_][A-Za-z0-9_$]*"
# Any identifier or dotted token (e.g. `users`, `ssn`, `users.ssn`, `public.users`).
_ANY_IDENT_RE = re.compile(_IDENT + r"(?:\." + _IDENT + r")*")

# (pattern, category). Patterns match against a normalized (lowercased) identifier;
# `.` is a non-word char so `\bssn\b` matches the `ssn` segment of `users.ssn`. These
# are intentionally broad (best-effort, over-detection-biased).
_NAME_PATTERNS: List[Tuple["re.Pattern[str]", SQLPiiPhiCategory]] = [
    (re.compile(r"\b(?:ssn|social_security)\b"), SQLPiiPhiCategory.SSN),
    (re.compile(r"\b(?:e[_-]?mail)\b"), SQLPiiPhiCategory.EMAIL),
    (re.compile(r"\b(?:phone|mobile|msisdn)\b"), SQLPiiPhiCategory.PHONE),
    (re.compile(r"\b(?:dob|date_of_birth|birth_date|birthday)\b"), SQLPiiPhiCategory.DATE_OF_BIRTH),
    (re.compile(r"\biban\b"), SQLPiiPhiCategory.IBAN),
    (re.compile(r"\b(?:credit_card|card_number|cc_number)\b"), SQLPiiPhiCategory.CREDIT_CARD),
    (re.compile(r"\b(?:first_name|last_name|full_name|surname)\b"), SQLPiiPhiCategory.PERSON_NAME),
    (re.compile(r"\b(?:address|street|postcode|zip_code|zipcode)\b"), SQLPiiPhiCategory.POSTAL_ADDRESS),
    (re.compile(r"\b(?:mrn|medical_record(?:_number)?)\b"), SQLPiiPhiCategory.MEDICAL_RECORD_NUMBER),
    (re.compile(r"\b(?:diagnosis|icd(?:10|9)?)\b"), SQLPiiPhiCategory.DIAGNOSIS),
    (re.compile(r"\b(?:patient|disease|treatment|prescription)\b"), SQLPiiPhiCategory.HEALTH_GENERIC),
]


def _extract_identifiers(core: str) -> Set[str]:
    """Every normalized identifier / dotted token in the executable core.

    Captures unqualified column names (``ssn``) as well as qualified tokens
    (``users.ssn``). Over-captures SQL keywords (``select``, ``from``); harmless since
    keywords never match a PII/PHI name pattern.
    """
    return {_normalize_id(m.group(0)) for m in _ANY_IDENT_RE.finditer(core)}


def _detect_name_matches(identifiers: Set[str]) -> List[Tuple[SQLPiiPhiCategory, str]]:
    """``(category, identifier)`` pairs where an identifier matches a category name
    pattern. Deterministically ordered (identifier asc, then pattern order)."""
    out: List[Tuple[SQLPiiPhiCategory, str]] = []
    for ident in sorted(identifiers):
        for pattern, category in _NAME_PATTERNS:
            if pattern.search(ident):
                out.append((category, ident))
    return out


# --- Layer C: literal-value detection over the RAW sql (best-effort) ---

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


def _detect_literal_matches(sql: str) -> List[Tuple[SQLPiiPhiCategory, SQLPiiPhiConfidence]]:
    """Value-format detections over the raw SQL. Deterministic, value-free output.

    Over-detection is intentional (a signal, never a gate): e.g. an SSN literal also
    looks like a phone number, so both may be emitted; a long Luhn-valid order number
    may read as a card. No matched value is ever returned or stored.
    """
    out: List[Tuple[SQLPiiPhiCategory, SQLPiiPhiConfidence]] = []
    if _EMAIL_RE.search(sql):
        out.append((SQLPiiPhiCategory.EMAIL, SQLPiiPhiConfidence.MEDIUM))
    if _SSN_RE.search(sql):
        out.append((SQLPiiPhiCategory.SSN, SQLPiiPhiConfidence.MEDIUM))
    if _IBAN_RE.search(sql):
        out.append((SQLPiiPhiCategory.IBAN, SQLPiiPhiConfidence.MEDIUM))
    for m in _CARD_CANDIDATE_RE.finditer(sql):
        if _luhn_ok(re.sub(r"[ -]", "", m.group(0))):
            out.append((SQLPiiPhiCategory.CREDIT_CARD, SQLPiiPhiConfidence.HIGH))
            break
    if _PHONE_RE.search(sql):
        out.append((SQLPiiPhiCategory.PHONE, SQLPiiPhiConfidence.LOW))
    return out


class SQLPiiPhiDetector:
    """Deterministic, static PII/PHI detector. Stateless w.r.t. requests: the result
    is a pure function of (request, declarations). NOT a gate — it emits a signal only.

    Identifiers feed Layer A (declared) + Layer B (name heuristics); the raw sql feeds
    Layer C (literal heuristics) whenever it is a usable string. ``evaluated_via``
    describes the identifier view (EXPLICIT_REFERENCES / SQL_TEXT / NONE); literal
    matches are reported per-match via the LITERAL_VALUE source regardless.
    """

    def __init__(self, declarations: Sequence[SQLPiiPhiDeclaration] = ()):
        for d in declarations:
            if not isinstance(d, SQLPiiPhiDeclaration):
                raise SQLPiiPhiDetectionContractError("each declaration must be a SQLPiiPhiDeclaration")
        self._declared: Dict[str, List[SQLPiiPhiCategory]] = {}
        for d in declarations:
            self._declared.setdefault(d.resource_id, []).append(d.category)

    def detect(self, request: SQLPiiPhiDetectionRequest) -> SQLPiiPhiDetectionResult:
        if not isinstance(request, SQLPiiPhiDetectionRequest):
            raise SQLPiiPhiDetectionContractError("request must be a SQLPiiPhiDetectionRequest")

        sql = request.sql
        dialect = request.dialect
        sql_hash = (
            hashlib.sha256(sql.encode("utf-8")).hexdigest()
            if isinstance(sql, str) and sql else None
        )

        identifiers, via = self._resolve_identifiers(request)
        if via == SQLPiiPhiEvaluatedVia.NONE:
            return self._result(
                (), (), False, None, SQLPiiPhiReasonCode.UNUSABLE_INPUT, via, sql_hash, dialect,
                reason="No usable references and no usable SQL; cannot evaluate "
                       "PII/PHI presence.")

        matches: List[SQLPiiPhiMatch] = []
        # Layer A — declared map (sound, HIGH).
        for ident in identifiers:
            for category in self._declared.get(ident, ()):
                matches.append(SQLPiiPhiMatch(
                    category=category, data_class=_CATEGORY_DATA_CLASS[category],
                    source=SQLPiiPhiDetectionSource.DECLARED,
                    confidence=SQLPiiPhiConfidence.HIGH, identifier=ident))
        # Layer B — identifier-name heuristics (MEDIUM).
        for category, ident in _detect_name_matches(identifiers):
            matches.append(SQLPiiPhiMatch(
                category=category, data_class=_CATEGORY_DATA_CLASS[category],
                source=SQLPiiPhiDetectionSource.IDENTIFIER_NAME,
                confidence=SQLPiiPhiConfidence.MEDIUM, identifier=ident))
        # Layer C — literal-value heuristics over the raw sql (LOW->HIGH).
        if isinstance(sql, str) and sql.strip():
            for category, confidence in _detect_literal_matches(sql):
                matches.append(SQLPiiPhiMatch(
                    category=category, data_class=_CATEGORY_DATA_CLASS[category],
                    source=SQLPiiPhiDetectionSource.LITERAL_VALUE,
                    confidence=confidence, identifier=None))

        return self._aggregate(matches, via, sql_hash, dialect)

    def _resolve_identifiers(self, request: SQLPiiPhiDetectionRequest):
        """Return (identifiers, evaluated_via). Explicit references win (sound); else
        extract from sql (best-effort); else NONE. Usability hinges on explicit refs
        or a non-empty sql string."""
        if request.referenced_tables is not None or request.referenced_columns is not None:
            idents = self._normalize_set(request.referenced_tables) | \
                self._normalize_set(request.referenced_columns)
            return idents, SQLPiiPhiEvaluatedVia.EXPLICIT_REFERENCES
        sql = request.sql
        if isinstance(sql, str) and sql.strip():
            return _extract_identifiers(_to_executable_core(sql)), SQLPiiPhiEvaluatedVia.SQL_TEXT
        return set(), SQLPiiPhiEvaluatedVia.NONE

    @staticmethod
    def _normalize_set(values: Optional[Sequence[str]]) -> Set[str]:
        if not values:
            return set()
        return {_normalize_id(v) for v in values if isinstance(v, str) and v.strip()}

    def _aggregate(self, matches: List[SQLPiiPhiMatch], via: SQLPiiPhiEvaluatedVia,
                   sql_hash: Optional[str], dialect: str) -> SQLPiiPhiDetectionResult:
        if not matches:
            return self._result(
                (), (), False, None, SQLPiiPhiReasonCode.NO_PII_PHI_DETECTED, via, sql_hash, dialect,
                reason="No PII/PHI detected in the query's identifiers or literals.")

        # De-duplicate on (category, source, identifier).
        seen: Set[Tuple[Any, ...]] = set()
        unique: List[SQLPiiPhiMatch] = []
        for m in matches:
            key = (m.category, m.source, m.identifier)
            if key in seen:
                continue
            seen.add(key)
            unique.append(m)
        # Order: PHI before PII, then category, then source, then confidence desc, then
        # identifier (None last via a high sentinel).
        unique.sort(key=lambda m: (
            0 if m.data_class == SQLDataClass.PHI else 1,
            m.category.value,
            m.source.value,
            -_CONFIDENCE_ORDER[m.confidence],
            m.identifier if m.identifier is not None else "~",
        ))

        categories = tuple(sorted({m.category for m in unique}, key=lambda c: c.value))
        has_phi = any(m.data_class == SQLDataClass.PHI for m in unique)
        highest = max((m.confidence for m in unique), key=lambda c: _CONFIDENCE_ORDER[c])
        reason_code = (SQLPiiPhiReasonCode.PHI_DETECTED if has_phi
                       else SQLPiiPhiReasonCode.PII_DETECTED)
        reason = (f"Detected {len(categories)} PII/PHI category(ies) "
                  f"(has_phi={has_phi}, max confidence {highest.value}).")
        return self._result(
            tuple(unique), categories, has_phi, highest, reason_code, via, sql_hash, dialect,
            reason=reason)

    def _result(self, detected: Tuple[SQLPiiPhiMatch, ...],
                categories: Tuple[SQLPiiPhiCategory, ...], has_phi: bool,
                highest_confidence: Optional[SQLPiiPhiConfidence],
                reason_code: SQLPiiPhiReasonCode, via: SQLPiiPhiEvaluatedVia,
                sql_sha256: Optional[str], dialect: str,
                reason: str) -> SQLPiiPhiDetectionResult:
        return SQLPiiPhiDetectionResult(
            version=SQL_PII_PHI_DETECTION_CONTRACT_VERSION,
            detected=detected, categories=categories, has_phi=has_phi,
            highest_confidence=highest_confidence, reason_code=reason_code, reason=reason,
            sql_sha256=sql_sha256, evaluated_via=via, dialect=dialect)
