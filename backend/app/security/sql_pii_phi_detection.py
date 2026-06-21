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
