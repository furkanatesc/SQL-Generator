"""Sprint 26.6 — Audit Event Contract (Phase 7: Security & Governance).

Maturity: contract MVP. Defines ONE immutable, secret-free audit record that any
26.0-26.5 governance result normalizes into, plus a SHA-256 hash chain that makes
the record sequence tamper-evident. Where 26.0 asks "may this run?", 26.1 "right
tenant?", 26.2 "read-only?", 26.3 "how risky?", 26.4 "declared-sensitive?", 26.5
"PII/PHI?", 26.6 records: **what happened, who, when, where, why, and with what
outcome** -- in a form whose later alteration is detectable.

It is a record + normalizer + hash chain. It is NOT a logger, sink, or transport:
it performs NO I/O, calls NO clock, uses NO randomness. ``occurred_at`` and
``event_id`` are caller-supplied so the record (and its hash) are deterministic and
reproducible. Persistence, shipping, retention and querying are Phase 13.

Integrity model: the chain is **integrity-evident, NOT non-repudiation**. Each
entry_hash commits to the full prior chain via prev_hash, so any edit/reorder/
insert/delete to an earlier record breaks every later hash and is detected by
``verify_chain``. An attacker who can rewrite the entire suffix could still forge a
consistent chain; true non-repudiation needs asymmetric signing / an external
anchor -- Phase 13, out of scope.

Secret-free: no raw SQL anywhere. ``sql_sha256`` and ``details`` are copied from
source results already proven secret-free in 26.0-26.5; this module adds no new
raw-SQL surface.

Out of scope (deliberate): persistence/transport (Phase 13), approval (26.7),
asymmetric signing / Merkle trees / external timestamping, clocks, id generation,
querying/SIEM mapping, API/UI. This module performs no I/O.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Sequence

AUDIT_EVENT_CONTRACT_VERSION = "audit_event_contract_v1"

_HEX64 = re.compile(r"[a-f0-9]{64}")


class AuditEventContractError(ValueError):
    """Raised when audit event contract rules are violated."""
    pass


class AuditCategory(str, Enum):
    AUTHZ_PERMISSION = "authz_permission"   # 26.0
    TENANT_BOUNDARY = "tenant_boundary"     # 26.1
    READ_ONLY = "read_only"                 # 26.2
    QUERY_RISK = "query_risk"               # 26.3
    SENSITIVE_DATA = "sensitive_data"       # 26.4
    PII_PHI = "pii_phi"                     # 26.5


class AuditOutcome(str, Enum):
    ALLOWED = "allowed"
    DENIED = "denied"
    REQUIRES_APPROVAL = "requires_approval"
    FLAGGED = "flagged"          # a signal was raised; no gate decision
    ERROR = "error"             # contract / evaluation error path


class AuditSeverity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Deterministic low->high ordering for comparisons / mapping.
_SEVERITY_ORDER: Dict[AuditSeverity, int] = {
    AuditSeverity.INFO: 0,
    AuditSeverity.LOW: 1,
    AuditSeverity.MEDIUM: 2,
    AuditSeverity.HIGH: 3,
    AuditSeverity.CRITICAL: 4,
}
