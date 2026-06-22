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

import dataclasses
import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Sequence

from app.security.sql_permission_policy import (
    SQL_PERMISSION_POLICY_CONTRACT_VERSION, SQLPermissionPolicyResult,
    SQLPermissionDecision,
)
from app.security.tenant_workspace_boundary import (
    TENANT_WORKSPACE_BOUNDARY_CONTRACT_VERSION, TenantWorkspaceBoundaryResult,
    TenantWorkspaceBoundaryDecision,
)
from app.security.sql_read_only_enforcement import (
    SQL_READ_ONLY_ENFORCEMENT_CONTRACT_VERSION, SQLReadOnlyEnforcementResult,
    SQLReadOnlyDecision,
)
from app.security.sql_query_risk_classifier import (
    SQL_QUERY_RISK_CLASSIFIER_CONTRACT_VERSION, SQLQueryRiskResult, SQLQueryRiskLevel,
)
from app.security.sql_sensitive_data_policy import (
    SQL_SENSITIVE_DATA_POLICY_CONTRACT_VERSION, SQLSensitiveDataPolicyResult,
    SQLSensitiveDataDecision, SQLSensitivityLevel,
)
from app.security.sql_pii_phi_detection import (
    SQL_PII_PHI_DETECTION_CONTRACT_VERSION, SQLPiiPhiDetectionResult,
    SQLPiiPhiConfidence,
)

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


def _check_opt_str(value: Any, field: str) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise AuditEventContractError(
            f"{field} must be a non-empty string or None, got {value!r}"
        )


@dataclass(frozen=True)
class AuditActor:
    """WHO performed the action. Only ``subject`` is required."""
    subject: str
    tenant: Optional[str] = None
    workspace: Optional[str] = None
    source_ip: Optional[str] = None
    request_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.subject, str) or not self.subject.strip():
            raise AuditEventContractError("actor.subject must be a non-empty string")
        _check_opt_str(self.tenant, "actor.tenant")
        _check_opt_str(self.workspace, "actor.workspace")
        _check_opt_str(self.source_ip, "actor.source_ip")
        _check_opt_str(self.request_id, "actor.request_id")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject": self.subject,
            "tenant": self.tenant,
            "workspace": self.workspace,
            "source_ip": self.source_ip,
            "request_id": self.request_id,
        }


@dataclass(frozen=True)
class AuditResource:
    """WHAT was acted on. id is e.g. a table or query id -- never raw SQL."""
    type: Optional[str] = None
    id: Optional[str] = None
    dialect: Optional[str] = None

    def __post_init__(self) -> None:
        _check_opt_str(self.type, "resource.type")
        _check_opt_str(self.id, "resource.id")
        _check_opt_str(self.dialect, "resource.dialect")

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, "id": self.id, "dialect": self.dialect}


def _check_req_str(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise AuditEventContractError(f"{field} must be a non-empty string")


def _check_hex64(value: Any, field: str) -> None:
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        raise AuditEventContractError(f"{field} must be a 64-char lowercase hex string")


@dataclass(frozen=True)
class AuditEvent:
    """Immutable, secret-free audit record. Build via ``link`` / the ``from_*``
    normalizers (Task 4/5) so ``entry_hash`` is computed; direct construction
    requires a precomputed ``entry_hash``."""
    schema_version: str
    event_id: str
    occurred_at: str
    category: AuditCategory
    action: str
    outcome: AuditOutcome
    severity: AuditSeverity
    actor: AuditActor
    resource: AuditResource
    reason_code: str
    reason: str
    contract_source: str
    sql_sha256: Optional[str]
    details: Dict[str, Any]
    prev_hash: Optional[str]
    entry_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != AUDIT_EVENT_CONTRACT_VERSION:
            raise AuditEventContractError(
                f"schema_version must be {AUDIT_EVENT_CONTRACT_VERSION!r}, "
                f"got {self.schema_version!r}"
            )
        _check_req_str(self.event_id, "event_id")
        _check_req_str(self.occurred_at, "occurred_at")
        _check_req_str(self.action, "action")
        _check_req_str(self.reason_code, "reason_code")
        _check_req_str(self.reason, "reason")
        _check_req_str(self.contract_source, "contract_source")
        if not isinstance(self.category, AuditCategory):
            raise AuditEventContractError("category must be an AuditCategory")
        if not isinstance(self.outcome, AuditOutcome):
            raise AuditEventContractError("outcome must be an AuditOutcome")
        if not isinstance(self.severity, AuditSeverity):
            raise AuditEventContractError("severity must be an AuditSeverity")
        if not isinstance(self.actor, AuditActor):
            raise AuditEventContractError("actor must be an AuditActor")
        if not isinstance(self.resource, AuditResource):
            raise AuditEventContractError("resource must be an AuditResource")
        if self.sql_sha256 is not None:
            _check_hex64(self.sql_sha256, "sql_sha256")
        if not isinstance(self.details, dict):
            raise AuditEventContractError("details must be a dict")
        if self.prev_hash is not None:
            _check_hex64(self.prev_hash, "prev_hash")
        _check_hex64(self.entry_hash, "entry_hash")

    def _payload(self) -> Dict[str, Any]:
        """JSON-safe dict of every field EXCEPT entry_hash (includes prev_hash).
        This is exactly what entry_hash is computed over (Task 4)."""
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "occurred_at": self.occurred_at,
            "category": self.category.value,
            "action": self.action,
            "outcome": self.outcome.value,
            "severity": self.severity.value,
            "actor": self.actor.to_dict(),
            "resource": self.resource.to_dict(),
            "reason_code": self.reason_code,
            "reason": self.reason,
            "contract_source": self.contract_source,
            "sql_sha256": self.sql_sha256,
            "details": self.details,
            "prev_hash": self.prev_hash,
        }

    def to_dict(self) -> Dict[str, Any]:
        payload = self._payload()
        payload["entry_hash"] = self.entry_hash
        return payload


def _canonical(payload: Dict[str, Any]) -> str:
    """Deterministic JSON: sorted keys, no whitespace, stable across runs."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_entry_hash(event: AuditEvent) -> str:
    """SHA-256 over the canonical payload (every field except entry_hash, incl.
    prev_hash). Recomputing this and comparing to the stored entry_hash is how
    verify_chain detects mutation."""
    return hashlib.sha256(_canonical(event._payload()).encode("utf-8")).hexdigest()


def link(
    prev: Optional[AuditEvent],
    *,
    event_id: str,
    occurred_at: str,
    category: AuditCategory,
    action: str,
    outcome: AuditOutcome,
    severity: AuditSeverity,
    actor: AuditActor,
    resource: AuditResource,
    reason_code: str,
    reason: str,
    contract_source: str,
    sql_sha256: Optional[str],
    details: Dict[str, Any],
) -> AuditEvent:
    """Build the next AuditEvent, chained to ``prev`` (None = genesis).
    Computes prev_hash and entry_hash; returns a validated, frozen record."""
    prev_hash = prev.entry_hash if prev is not None else None
    # Build a draft to derive the payload, then stamp the real entry_hash.
    # entry_hash is excluded from the payload, so a placeholder is hashed-out.
    draft = AuditEvent(
        schema_version=AUDIT_EVENT_CONTRACT_VERSION,
        event_id=event_id,
        occurred_at=occurred_at,
        category=category,
        action=action,
        outcome=outcome,
        severity=severity,
        actor=actor,
        resource=resource,
        reason_code=reason_code,
        reason=reason,
        contract_source=contract_source,
        sql_sha256=sql_sha256,
        details=details,
        prev_hash=prev_hash,
        entry_hash="0" * 64,    # placeholder; excluded from _payload(), replaced below
    )
    entry_hash = compute_entry_hash(draft)
    return dataclasses.replace(draft, entry_hash=entry_hash)


def verify_chain(events: Sequence[AuditEvent]) -> Optional[int]:
    """Return the index of the first broken link, or None if the chain is intact.

    Broken means either (a) the stored entry_hash != recomputed hash (the record
    was mutated after hashing), or (b) continuity breaks: events[0].prev_hash must
    be None, and events[i].prev_hash must equal events[i-1].entry_hash. Detects
    mutation, reorder, insertion and deletion. Empty sequence is vacuously valid."""
    prev: Optional[AuditEvent] = None
    for i, event in enumerate(events):
        expected_prev = prev.entry_hash if prev is not None else None
        if event.prev_hash != expected_prev:
            return i
        if compute_entry_hash(event) != event.entry_hash:
            return i
        prev = event
    return None


# ---------------------------------------------------------------------------
# Mapping tables (keyed by lowercase enum .value strings)
# ---------------------------------------------------------------------------

# decision .value (shared across the gate result types) -> audit outcome
_DECISION_OUTCOME: Dict[str, AuditOutcome] = {
    "allow": AuditOutcome.ALLOWED,
    "deny": AuditOutcome.DENIED,
    "requires_approval": AuditOutcome.REQUIRES_APPROVAL,
}

# decision .value -> severity for the permission/tenant/read-only gates
_DECISION_SEVERITY: Dict[str, AuditSeverity] = {
    "allow": AuditSeverity.INFO,
    "deny": AuditSeverity.HIGH,
    "requires_approval": AuditSeverity.MEDIUM,
}

# risk level .value -> severity (and reused for QUERY_RISK reason_code)
_RISK_SEVERITY: Dict[str, AuditSeverity] = {
    "low": AuditSeverity.LOW,
    "medium": AuditSeverity.MEDIUM,
    "high": AuditSeverity.HIGH,
    "critical": AuditSeverity.CRITICAL,
}

# sensitivity level .value -> severity
_SENSITIVITY_SEVERITY: Dict[str, AuditSeverity] = {
    "public": AuditSeverity.INFO,
    "internal": AuditSeverity.LOW,
    "confidential": AuditSeverity.MEDIUM,
    "restricted": AuditSeverity.HIGH,
}


# ---------------------------------------------------------------------------
# Normalizer builders (six sources)
# ---------------------------------------------------------------------------

def from_permission(result: SQLPermissionPolicyResult, *, event_id: str, occurred_at: str, actor: AuditActor, resource: AuditResource, prev: Optional[AuditEvent] = None) -> AuditEvent:
    """Normalize a 26.0 permission result into an AuditEvent (AUTHZ_PERMISSION)."""
    dv = result.decision.value
    return link(
        prev, event_id=event_id, occurred_at=occurred_at,
        category=AuditCategory.AUTHZ_PERMISSION, action="evaluate_permission",
        outcome=_DECISION_OUTCOME[dv], severity=_DECISION_SEVERITY[dv],
        actor=actor, resource=resource,
        reason_code=result.reason_code.value, reason=result.reason,
        contract_source=SQL_PERMISSION_POLICY_CONTRACT_VERSION,
        sql_sha256=None,                      # permission result carries no sql hash
        details=result.to_dict(),
    )


def from_tenant(result: TenantWorkspaceBoundaryResult, *, event_id: str, occurred_at: str, actor: AuditActor, resource: AuditResource, prev: Optional[AuditEvent] = None) -> AuditEvent:
    """Normalize a 26.1 tenant/workspace boundary result (TENANT_BOUNDARY)."""
    dv = result.decision.value
    return link(
        prev, event_id=event_id, occurred_at=occurred_at,
        category=AuditCategory.TENANT_BOUNDARY, action="check_tenant_boundary",
        outcome=_DECISION_OUTCOME[dv], severity=_DECISION_SEVERITY[dv],
        actor=actor, resource=resource,
        reason_code=result.reason_code.value, reason=result.reason,
        contract_source=TENANT_WORKSPACE_BOUNDARY_CONTRACT_VERSION,
        sql_sha256=None,                      # tenant result carries no sql hash
        details=result.to_dict(),
    )


def from_read_only(result: SQLReadOnlyEnforcementResult, *, event_id: str, occurred_at: str, actor: AuditActor, resource: AuditResource, prev: Optional[AuditEvent] = None) -> AuditEvent:
    """Normalize a 26.2 read-only enforcement result (READ_ONLY)."""
    dv = result.decision.value
    return link(
        prev, event_id=event_id, occurred_at=occurred_at,
        category=AuditCategory.READ_ONLY, action="enforce_read_only",
        outcome=_DECISION_OUTCOME[dv], severity=_DECISION_SEVERITY[dv],
        actor=actor, resource=resource,
        reason_code=result.reason_code.value, reason=result.reason,
        contract_source=SQL_READ_ONLY_ENFORCEMENT_CONTRACT_VERSION,
        sql_sha256=result.sql_sha256,
        details=result.to_dict(),
    )


def from_risk(result: SQLQueryRiskResult, *, event_id: str, occurred_at: str, actor: AuditActor, resource: AuditResource, prev: Optional[AuditEvent] = None) -> AuditEvent:
    """Normalize a 26.3 risk classifier result (QUERY_RISK). A signal, not a gate:
    outcome is always FLAGGED; risk has no reason_code, so the level value is used."""
    lv = result.risk_level.value
    return link(
        prev, event_id=event_id, occurred_at=occurred_at,
        category=AuditCategory.QUERY_RISK, action="classify_query_risk",
        outcome=AuditOutcome.FLAGGED, severity=_RISK_SEVERITY[lv],
        actor=actor, resource=resource,
        reason_code=lv, reason=result.reason,
        contract_source=SQL_QUERY_RISK_CLASSIFIER_CONTRACT_VERSION,
        sql_sha256=result.sql_sha256,
        details=result.to_dict(),
    )


def from_sensitive(result: SQLSensitiveDataPolicyResult, *, event_id: str, occurred_at: str, actor: AuditActor, resource: AuditResource, prev: Optional[AuditEvent] = None) -> AuditEvent:
    """Normalize a 26.4 sensitive-data policy result (SENSITIVE_DATA)."""
    return link(
        prev, event_id=event_id, occurred_at=occurred_at,
        category=AuditCategory.SENSITIVE_DATA, action="evaluate_sensitive_data",
        outcome=_DECISION_OUTCOME[result.decision.value],
        severity=_SENSITIVITY_SEVERITY[result.sensitivity_level.value],
        actor=actor, resource=resource,
        reason_code=result.reason_code.value, reason=result.reason,
        contract_source=SQL_SENSITIVE_DATA_POLICY_CONTRACT_VERSION,
        sql_sha256=result.sql_sha256,
        details=result.to_dict(),
    )


def from_pii_phi(result: SQLPiiPhiDetectionResult, *, event_id: str, occurred_at: str, actor: AuditActor, resource: AuditResource, prev: Optional[AuditEvent] = None) -> AuditEvent:
    """Normalize a 26.5 PII/PHI detection result (PII_PHI). A detector, not a gate:
    outcome is always FLAGGED; severity escalates with PHI and confidence."""
    if result.has_phi:
        severity = (AuditSeverity.CRITICAL
                    if result.highest_confidence == SQLPiiPhiConfidence.HIGH
                    else AuditSeverity.HIGH)
    elif result.highest_confidence is not None:      # PII only
        severity = (AuditSeverity.MEDIUM
                    if result.highest_confidence == SQLPiiPhiConfidence.HIGH
                    else AuditSeverity.LOW)
    else:
        severity = AuditSeverity.INFO
    return link(
        prev, event_id=event_id, occurred_at=occurred_at,
        category=AuditCategory.PII_PHI, action="detect_pii_phi",
        outcome=AuditOutcome.FLAGGED, severity=severity,
        actor=actor, resource=resource,
        reason_code=result.reason_code.value, reason=result.reason,
        contract_source=SQL_PII_PHI_DETECTION_CONTRACT_VERSION,
        sql_sha256=result.sql_sha256,
        details=result.to_dict(),
    )
