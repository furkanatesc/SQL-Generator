"""Sprint 26.7 — Approval Workflow Contract (Phase 7: Security & Governance).

Maturity: contract MVP. A pure, deterministic approval state machine. Where 26.0
asks "may this run?" and 26.4 "touches declared-sensitive data?", either can return
REQUIRES_APPROVAL -- a verdict that a human must sign off. 26.7 orchestrates that
sign-off: a REQUIRES_APPROVAL signal opens an immutable ApprovalRequest which
collects approver decisions and settles into a terminal state under two rules:

* Quorum (N-of-M): ``required_approvals`` distinct approvers must approve.
* Separation of duties (SoD): the requester can never approve their own request.

It is a state machine + normalizer, NOT a sink: NO I/O, NO clock, NO randomness.
``occurred_at``/``opened_at``/``expires_at``/``now`` and ``request_id`` are
caller-supplied so every transition is deterministic and reproducible. Each
transition returns a NEW frozen request; the input is never mutated.

Secret-free: no raw SQL, and deliberately NO free-text approver comment (free text
is an uncontrolled leak channel). Only ids, enum values, and ``sql_sha256`` /
``resource_id`` copied verbatim from source results already proven secret-free.

Quorum + SoD, NOT RBAC: it enforces HOW MANY distinct non-requester approvers are
needed, not WHO is eligible. Role-based approver eligibility is a later sprint.

Integrity is inherited: tamper-evidence comes from the 26.6 audit chain via
``audit_event.from_approval``; this module adds no integrity machinery and never
imports ``audit_event`` (one-way graph: audit -> approval -> {permission, sensitive}).

Out of scope (deliberate): persistence/transport (Phase 13), scheduling/real timers,
RBAC approver eligibility, asymmetric signing, clocks, id generation, API/UI,
concurrency/locking. This module performs no I/O.
"""

import dataclasses
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from app.security.sql_permission_policy import (
    SQLPermissionPolicyResult, SQLPermissionDecision,
)
from app.security.sql_sensitive_data_policy import (
    SQLSensitiveDataPolicyResult, SQLSensitiveDataDecision, SQLSensitivityLevel,
)

APPROVAL_WORKFLOW_CONTRACT_VERSION = "approval_workflow_contract_v1"

_HEX64 = re.compile(r"[a-f0-9]{64}")


class ApprovalWorkflowContractError(ValueError):
    """Raised when approval workflow contract rules are violated."""
    pass


class ApprovalState(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ApprovalDecisionType(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


class ApprovalCategory(str, Enum):
    PERMISSION = "permission"           # 26.0
    SENSITIVE_DATA = "sensitive_data"   # 26.4


class ApprovalReasonCode(str, Enum):
    OPENED = "opened"                       # PENDING, freshly opened
    APPROVAL_RECORDED = "approval_recorded" # PENDING, approve recorded, quorum not yet met
    QUORUM_MET = "quorum_met"               # APPROVED
    REJECTED_VETO = "rejected_veto"         # REJECTED (single reject vetoes)
    CANCELLED = "cancelled"                 # CANCELLED
    EXPIRED = "expired"                     # EXPIRED


TERMINAL_STATES = frozenset({
    ApprovalState.APPROVED,
    ApprovalState.REJECTED,
    ApprovalState.EXPIRED,
    ApprovalState.CANCELLED,
})


def _check_req_str(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ApprovalWorkflowContractError(f"{field} must be a non-empty string")


def _check_opt_str(value: Any, field: str) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ApprovalWorkflowContractError(
            f"{field} must be a non-empty string or None, got {value!r}"
        )


@dataclass(frozen=True)
class ApprovalDecision:
    """One approver's vote. Secret-free: approver id + enum + caller-supplied time."""
    approver: str
    decision: ApprovalDecisionType
    occurred_at: str

    def __post_init__(self) -> None:
        _check_req_str(self.approver, "approver")
        if not isinstance(self.decision, ApprovalDecisionType):
            raise ApprovalWorkflowContractError("decision must be an ApprovalDecisionType")
        _check_req_str(self.occurred_at, "occurred_at")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approver": self.approver,
            "decision": self.decision.value,
            "occurred_at": self.occurred_at,
        }


@dataclass(frozen=True)
class ApprovalRequest:
    """Immutable approval request. Build/transition via the module functions so
    state and reason_code stay consistent. Secret-free (no raw SQL, no free text)."""
    schema_version: str
    request_id: str
    requester: str
    category: ApprovalCategory
    required_approvals: int
    state: ApprovalState
    decisions: Tuple[ApprovalDecision, ...]
    reason_code: ApprovalReasonCode
    sql_sha256: Optional[str]
    resource_id: Optional[str]
    opened_at: str
    expires_at: Optional[str]

    def __post_init__(self) -> None:
        if self.schema_version != APPROVAL_WORKFLOW_CONTRACT_VERSION:
            raise ApprovalWorkflowContractError(
                f"schema_version must be {APPROVAL_WORKFLOW_CONTRACT_VERSION!r}, "
                f"got {self.schema_version!r}"
            )
        _check_req_str(self.request_id, "request_id")
        _check_req_str(self.requester, "requester")
        _check_req_str(self.opened_at, "opened_at")
        _check_opt_str(self.resource_id, "resource_id")
        _check_opt_str(self.expires_at, "expires_at")
        # bool is an int subclass; reject it explicitly.
        if not isinstance(self.required_approvals, int) or isinstance(self.required_approvals, bool) \
                or self.required_approvals < 1:
            raise ApprovalWorkflowContractError(
                f"required_approvals must be an int >= 1, got {self.required_approvals!r}"
            )
        if not isinstance(self.category, ApprovalCategory):
            raise ApprovalWorkflowContractError("category must be an ApprovalCategory")
        if not isinstance(self.state, ApprovalState):
            raise ApprovalWorkflowContractError("state must be an ApprovalState")
        if not isinstance(self.reason_code, ApprovalReasonCode):
            raise ApprovalWorkflowContractError("reason_code must be an ApprovalReasonCode")
        if not isinstance(self.decisions, tuple):
            raise ApprovalWorkflowContractError("decisions must be a tuple")
        for d in self.decisions:
            if not isinstance(d, ApprovalDecision):
                raise ApprovalWorkflowContractError("decisions must contain ApprovalDecision only")
        if self.sql_sha256 is not None and not _HEX64.fullmatch(str(self.sql_sha256)):
            raise ApprovalWorkflowContractError("sql_sha256 must be a 64-char lowercase hex string")

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def count_approvals(self) -> int:
        """Distinct approver ids whose vote is APPROVE."""
        return len({
            d.approver for d in self.decisions
            if d.decision == ApprovalDecisionType.APPROVE
        })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "requester": self.requester,
            "category": self.category.value,
            "required_approvals": self.required_approvals,
            "state": self.state.value,
            "decisions": [d.to_dict() for d in self.decisions],
            "reason_code": self.reason_code.value,
            "sql_sha256": self.sql_sha256,
            "resource_id": self.resource_id,
            "opened_at": self.opened_at,
            "expires_at": self.expires_at,
        }


# sensitivity level -> default quorum. PUBLIC/INTERNAL never reach REQUIRES_APPROVAL,
# so they are intentionally absent; a missing key is a fail-closed KeyError guarded below.
_SENSITIVITY_QUORUM: Dict[SQLSensitivityLevel, int] = {
    SQLSensitivityLevel.CONFIDENTIAL: 1,
    SQLSensitivityLevel.RESTRICTED: 2,
}


def open(*, request_id: str, requester: str, category: ApprovalCategory,
         required_approvals: int, sql_sha256: Optional[str] = None,
         resource_id: Optional[str] = None, opened_at: str,
         expires_at: Optional[str] = None) -> ApprovalRequest:
    """Open a fresh PENDING approval request. Validates required_approvals >= 1."""
    return ApprovalRequest(
        schema_version=APPROVAL_WORKFLOW_CONTRACT_VERSION,
        request_id=request_id, requester=requester, category=category,
        required_approvals=required_approvals, state=ApprovalState.PENDING,
        decisions=(), reason_code=ApprovalReasonCode.OPENED,
        sql_sha256=sql_sha256, resource_id=resource_id,
        opened_at=opened_at, expires_at=expires_at,
    )


def from_permission(result: SQLPermissionPolicyResult, *, request_id: str,
                    requester: str, opened_at: str, expires_at: Optional[str] = None,
                    resource_id: Optional[str] = None) -> ApprovalRequest:
    """Open a request from a 26.0 permission result. Fail-closed: the result's
    decision must be REQUIRES_APPROVAL. Permission carries no sql hash (N=1)."""
    if result.decision != SQLPermissionDecision.REQUIRES_APPROVAL:
        raise ApprovalWorkflowContractError(
            "from_permission requires a REQUIRES_APPROVAL result, "
            f"got {result.decision.value!r}"
        )
    return open(
        request_id=request_id, requester=requester,
        category=ApprovalCategory.PERMISSION, required_approvals=1,
        sql_sha256=None, resource_id=resource_id,
        opened_at=opened_at, expires_at=expires_at,
    )


def from_sensitive(result: SQLSensitiveDataPolicyResult, *, request_id: str,
                   requester: str, opened_at: str, expires_at: Optional[str] = None,
                   resource_id: Optional[str] = None) -> ApprovalRequest:
    """Open a request from a 26.4 sensitive-data result. Fail-closed: decision must
    be REQUIRES_APPROVAL. Quorum derives from sensitivity_level; sql hash copied."""
    if result.decision != SQLSensitiveDataDecision.REQUIRES_APPROVAL:
        raise ApprovalWorkflowContractError(
            "from_sensitive requires a REQUIRES_APPROVAL result, "
            f"got {result.decision.value!r}"
        )
    n = _SENSITIVITY_QUORUM.get(result.sensitivity_level)
    if n is None:
        raise ApprovalWorkflowContractError(
            f"no quorum defined for sensitivity level {result.sensitivity_level.value!r}"
        )
    return open(
        request_id=request_id, requester=requester,
        category=ApprovalCategory.SENSITIVE_DATA, required_approvals=n,
        sql_sha256=result.sql_sha256, resource_id=resource_id,
        opened_at=opened_at, expires_at=expires_at,
    )


def _replace_state(request: ApprovalRequest, *, decisions: Tuple[ApprovalDecision, ...],
                   state: ApprovalState, reason_code: ApprovalReasonCode) -> ApprovalRequest:
    """Return a NEW validated request with state/decisions/reason_code replaced; all
    identity/origin fields preserved. (dataclasses.replace re-runs __post_init__.)"""
    return dataclasses.replace(
        request, decisions=decisions, state=state, reason_code=reason_code,
    )


def _guard_vote(request: ApprovalRequest, approver: str) -> None:
    """Fail-closed preconditions shared by approve/reject."""
    _check_req_str(approver, "approver")
    if request.is_terminal:
        raise ApprovalWorkflowContractError(
            f"cannot vote on a {request.state.value} (terminal) request"
        )
    if approver == request.requester:
        raise ApprovalWorkflowContractError(
            "separation of duties: requester cannot vote on their own request"
        )
    if any(d.approver == approver for d in request.decisions):
        raise ApprovalWorkflowContractError(
            f"approver {approver!r} has already voted on this request"
        )


def approve(request: ApprovalRequest, *, approver: str, occurred_at: str) -> ApprovalRequest:
    """Record an APPROVE vote. Reaches APPROVED when distinct approvals meet quorum."""
    _guard_vote(request, approver)
    decisions = request.decisions + (
        ApprovalDecision(approver=approver, decision=ApprovalDecisionType.APPROVE,
                         occurred_at=occurred_at),
    )
    approvals = len({
        d.approver for d in decisions if d.decision == ApprovalDecisionType.APPROVE
    })
    if approvals >= request.required_approvals:
        state, reason = ApprovalState.APPROVED, ApprovalReasonCode.QUORUM_MET
    else:
        state, reason = ApprovalState.PENDING, ApprovalReasonCode.APPROVAL_RECORDED
    return _replace_state(request, decisions=decisions, state=state, reason_code=reason)


def reject(request: ApprovalRequest, *, approver: str, occurred_at: str) -> ApprovalRequest:
    """Record a REJECT vote. A single reject vetoes the request (terminal)."""
    _guard_vote(request, approver)
    decisions = request.decisions + (
        ApprovalDecision(approver=approver, decision=ApprovalDecisionType.REJECT,
                         occurred_at=occurred_at),
    )
    return _replace_state(request, decisions=decisions,
                          state=ApprovalState.REJECTED,
                          reason_code=ApprovalReasonCode.REJECTED_VETO)
