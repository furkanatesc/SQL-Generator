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

from enum import Enum
from typing import Dict

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
