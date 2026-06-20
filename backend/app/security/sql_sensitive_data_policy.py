"""Sprint 26.4 — Sensitive Table/Column Policy (Phase 7: Security & Governance).

Maturity: MVP / early beta. NOT production-ready. This sprint defines a *static*
(no execution) contract that decides whether a query touches a table/column the
operator has **declared sensitive**, and what to do about it. Where 26.0 asks "may
this run?", 26.1 "right tenant?", 26.2 "is it read-only?", 26.3 "how risky?", 26.4
asks:

* Does this query reference a declared-sensitive table/column, and is touching it
  allowed, denied, or does it need approval?

It is a **gate that also emits a signal**: it returns a decision
(ALLOW/DENY/REQUIRES_APPROVAL) plus, for audit, the matched sensitive resources and
the maximum sensitivity level. The signal explains the decision (consumed by audit
26.6 / approval 26.7); it does not compete with it.

This is a **declaration-based** gate: it enforces only what the policy author
declared sensitive — a table not in the policy is never treated as sensitive.
Heuristic content/name detection of PII/PHI is 26.5, deliberately out of scope.

Reference source is **hybrid**: caller-supplied table/column lists are used as-is
(sound); absent those, references are extracted from the raw SQL by best-effort
regex over the shared ``_sql_text`` sanitizer (comments/literals masked). The
extraction path is flagged via ``evaluated_via`` so a strict caller can require
explicit references.

Core security principle — **fail closed**: unusable input (no references and no
usable SQL) resolves to ``DENY`` (we cannot confirm the absence of sensitive
access). On the lossy extraction path, ``SELECT *`` over a table that has any
column-level rule is treated as touching all of that table's sensitive columns.

Out of scope (later sprints): PII/PHI content detection (26.5), audit persistence
(26.6), approval workflow orchestration (26.7), a real SQL parser, alias/schema
resolution, catalog metadata, any I/O, DB/adapter execution, API/UI, tenant/RBAC.
This module performs no I/O.

KNOWN LIMITATIONS (regex heuristics, no parser — a sound fix needs a real parser or
catalog metadata, a later sprint):

* The ``SQL_EXTRACTION`` path is alias-blind, nesting-blind, and
  schema-qualification-blind: a column reached through an alias (``u.ssn`` is not
  resolved to ``users.ssn``), inside a subquery/CTE, or via ``*`` on a table with
  no column rule may be missed. **Sound usage = explicit references.**
* Table extraction captures the identifier directly after ``FROM``/``JOIN`` only;
  additional comma-joined tables in a ``FROM`` list may be under-captured.
* The ``SELECT *`` fail-closed rule can over-match (flag a sensitive column a real
  projection would have excluded) — an intentional bias to higher protection.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Sequence, Tuple

SQL_SENSITIVE_DATA_POLICY_CONTRACT_VERSION = "sql_sensitive_data_policy_contract_v1"


class SQLSensitiveDataPolicyContractError(ValueError):
    """Raised when sensitive-data policy contract rules are violated."""
    pass


class SQLSensitivityLevel(str, Enum):
    # Declared low -> high; severity ordering is in _LEVEL_ORDER.
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class SQLSensitiveDataDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRES_APPROVAL = "requires_approval"


class SQLSensitiveResourceType(str, Enum):
    TABLE = "table"
    COLUMN = "column"


class SQLSensitiveDataReasonCode(str, Enum):
    NO_SENSITIVE_MATCH = "no_sensitive_match"
    SENSITIVE_MATCH_ALLOW = "sensitive_match_allow"
    SENSITIVE_MATCH_REQUIRES_APPROVAL = "sensitive_match_requires_approval"
    SENSITIVE_MATCH_DENY = "sensitive_match_deny"
    UNUSABLE_INPUT = "unusable_input"


class SQLSensitiveDataEvaluatedVia(str, Enum):
    EXPLICIT_REFERENCES = "explicit_references"   # caller-supplied lists (sound)
    SQL_EXTRACTION = "sql_extraction"             # best-effort regex over SQL
    NONE = "none"                                 # no usable input


# Sensitivity severity ordering (low -> high). The result level is the MAX of the
# matched rules' levels; no match -> PUBLIC.
_LEVEL_ORDER: Dict[SQLSensitivityLevel, int] = {
    SQLSensitivityLevel.PUBLIC: 0,
    SQLSensitivityLevel.INTERNAL: 1,
    SQLSensitivityLevel.CONFIDENTIAL: 2,
    SQLSensitivityLevel.RESTRICTED: 3,
}

# Decision restrictiveness (low -> high). The result decision is the MOST
# restrictive of the matched rules' actions; no match -> ALLOW.
_DECISION_RESTRICTIVENESS: Dict[SQLSensitiveDataDecision, int] = {
    SQLSensitiveDataDecision.ALLOW: 0,
    SQLSensitiveDataDecision.REQUIRES_APPROVAL: 1,
    SQLSensitiveDataDecision.DENY: 2,
}

_DECISION_TO_REASON: Dict[SQLSensitiveDataDecision, SQLSensitiveDataReasonCode] = {
    SQLSensitiveDataDecision.ALLOW: SQLSensitiveDataReasonCode.SENSITIVE_MATCH_ALLOW,
    SQLSensitiveDataDecision.REQUIRES_APPROVAL: SQLSensitiveDataReasonCode.SENSITIVE_MATCH_REQUIRES_APPROVAL,
    SQLSensitiveDataDecision.DENY: SQLSensitiveDataReasonCode.SENSITIVE_MATCH_DENY,
}


def _normalize_id(value: str) -> str:
    """Canonical form for a table/column identifier: stripped and lower-cased."""
    return value.strip().lower()


@dataclass(frozen=True)
class SQLSensitiveDataRule:
    """A single, trusted, immutable sensitivity rule.

    Rules are internal policy configuration (not untrusted input): the enum fields
    MUST be proper enum members. ``resource_id`` is normalized to lowercase; a
    COLUMN id must be table-qualified (``table.column``). ``sensitivity_level`` and
    ``action`` are independent — the level is the audit signal, the action is the
    gate.
    """
    resource_type: SQLSensitiveResourceType
    resource_id: str
    sensitivity_level: SQLSensitivityLevel
    action: SQLSensitiveDataDecision
    policy_id: Optional[str] = None

    def __post_init__(self):
        if not isinstance(self.resource_type, SQLSensitiveResourceType):
            raise SQLSensitiveDataPolicyContractError("resource_type must be a SQLSensitiveResourceType")
        if not isinstance(self.sensitivity_level, SQLSensitivityLevel):
            raise SQLSensitiveDataPolicyContractError("sensitivity_level must be a SQLSensitivityLevel")
        if not isinstance(self.action, SQLSensitiveDataDecision):
            raise SQLSensitiveDataPolicyContractError("action must be a SQLSensitiveDataDecision")
        if not isinstance(self.resource_id, str) or not self.resource_id.strip():
            raise SQLSensitiveDataPolicyContractError("resource_id must be a non-empty string")
        if self.policy_id is not None and (not isinstance(self.policy_id, str) or not self.policy_id.strip()):
            raise SQLSensitiveDataPolicyContractError("policy_id must be a non-empty string or None")
        normalized = _normalize_id(self.resource_id)
        if self.resource_type == SQLSensitiveResourceType.COLUMN and "." not in normalized:
            raise SQLSensitiveDataPolicyContractError(
                "COLUMN resource_id must be table-qualified (e.g. 'users.ssn')")
        object.__setattr__(self, "resource_id", normalized)

    @property
    def table(self) -> str:
        """Table portion: everything before the last '.' for a COLUMN id, else the
        id itself for a TABLE rule."""
        if self.resource_type == SQLSensitiveResourceType.COLUMN:
            return self.resource_id.rsplit(".", 1)[0]
        return self.resource_id


@dataclass(frozen=True)
class SQLSensitiveDataMatch:
    """One matched sensitivity rule, in a stable, typed, JSON-safe audit shape.

    Carries policy-declared resource names (schema metadata the operator declared),
    never query values — safe to persist in an audit record.
    """
    resource_type: SQLSensitiveResourceType
    resource_id: str
    sensitivity_level: SQLSensitivityLevel
    action: SQLSensitiveDataDecision
    policy_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resource_type": self.resource_type.value,
            "resource_id": self.resource_id,
            "sensitivity_level": self.sensitivity_level.value,
            "action": self.action.value,
            "policy_id": self.policy_id,
        }


@dataclass(frozen=True)
class SQLSensitiveDataPolicyResult:
    """An immutable, audit-grade, secret-free sensitivity decision.

    Carries NO raw SQL: only the decision, the max sensitivity level, the matched
    rules (deterministic order, de-duplicated), a reason code + human reason, a
    SHA-256 of the SQL (when given), and how references were obtained.
    """
    version: str
    decision: SQLSensitiveDataDecision
    sensitivity_level: SQLSensitivityLevel
    matched: Tuple[SQLSensitiveDataMatch, ...]
    reason_code: SQLSensitiveDataReasonCode
    reason: str
    sql_sha256: Optional[str]
    evaluated_via: SQLSensitiveDataEvaluatedVia
    dialect: str

    def __post_init__(self):
        if self.version != SQL_SENSITIVE_DATA_POLICY_CONTRACT_VERSION:
            raise SQLSensitiveDataPolicyContractError(f"Invalid result version: {self.version}")
        if not isinstance(self.decision, SQLSensitiveDataDecision):
            raise SQLSensitiveDataPolicyContractError("decision must be a SQLSensitiveDataDecision")
        if not isinstance(self.sensitivity_level, SQLSensitivityLevel):
            raise SQLSensitiveDataPolicyContractError("sensitivity_level must be a SQLSensitivityLevel")
        if not isinstance(self.matched, tuple):
            raise SQLSensitiveDataPolicyContractError("matched must be a tuple")
        for m in self.matched:
            if not isinstance(m, SQLSensitiveDataMatch):
                raise SQLSensitiveDataPolicyContractError("each matched entry must be a SQLSensitiveDataMatch")
        if not isinstance(self.reason_code, SQLSensitiveDataReasonCode):
            raise SQLSensitiveDataPolicyContractError("reason_code must be a SQLSensitiveDataReasonCode")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise SQLSensitiveDataPolicyContractError("reason must be a non-empty string")
        if self.sql_sha256 is not None and (
            not isinstance(self.sql_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", self.sql_sha256)
        ):
            raise SQLSensitiveDataPolicyContractError("sql_sha256 must be a lowercase SHA-256 hex digest or None")
        if not isinstance(self.evaluated_via, SQLSensitiveDataEvaluatedVia):
            raise SQLSensitiveDataPolicyContractError("evaluated_via must be a SQLSensitiveDataEvaluatedVia")
        if not isinstance(self.dialect, str) or not self.dialect.strip():
            raise SQLSensitiveDataPolicyContractError("dialect must be a non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "decision": self.decision.value,
            "sensitivity_level": self.sensitivity_level.value,
            "matched": [m.to_dict() for m in self.matched],
            "reason_code": self.reason_code.value,
            "reason": self.reason,
            "sql_sha256": self.sql_sha256,
            "evaluated_via": self.evaluated_via.value,
            "dialect": self.dialect,
        }


@dataclass(frozen=True)
class SQLSensitiveDataPolicyRequest:
    """An immutable sensitivity-policy request.

    Reference source is hybrid: if ``referenced_tables``/``referenced_columns`` are
    provided they are used as-is (sound); otherwise references are extracted from
    ``sql`` (best-effort). ``sql`` is typed ``str`` but intentionally NOT
    type-checked here, so a non-string yields a deterministic fail-closed result
    from ``evaluate()`` (bias to DENY) rather than raising at construction.
    """
    version: str
    sql: Optional[str] = None
    referenced_tables: Optional[Sequence[str]] = None
    referenced_columns: Optional[Sequence[str]] = None
    dialect: str = "generic"

    def __post_init__(self):
        if self.version != SQL_SENSITIVE_DATA_POLICY_CONTRACT_VERSION:
            raise SQLSensitiveDataPolicyContractError(f"Invalid request version: {self.version}")
        if not isinstance(self.dialect, str) or not self.dialect.strip():
            raise SQLSensitiveDataPolicyContractError("dialect must be a non-empty string")
