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

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict

APPROVAL_WORKFLOW_CONTRACT_VERSION = "approval_workflow_contract_v1"


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
