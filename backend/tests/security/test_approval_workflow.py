"""Sprint 26.7 — Approval Workflow Contract tests."""
import dataclasses

import pytest

from app.security.approval_workflow import (
    APPROVAL_WORKFLOW_CONTRACT_VERSION,
    ApprovalWorkflowContractError,
    ApprovalState,
    ApprovalDecisionType,
    ApprovalCategory,
    ApprovalReasonCode,
    TERMINAL_STATES,
    ApprovalDecision,
)


def test_version_and_error_type():
    assert APPROVAL_WORKFLOW_CONTRACT_VERSION == "approval_workflow_contract_v1"
    assert issubclass(ApprovalWorkflowContractError, ValueError)


def test_enum_values():
    assert ApprovalState.PENDING.value == "pending"
    assert {s.value for s in ApprovalState} == {
        "pending", "approved", "rejected", "expired", "cancelled"
    }
    assert {d.value for d in ApprovalDecisionType} == {"approve", "reject"}
    assert {c.value for c in ApprovalCategory} == {"permission", "sensitive_data"}
    assert ApprovalReasonCode.QUORUM_MET.value == "quorum_met"


def test_terminal_states():
    assert TERMINAL_STATES == frozenset({
        ApprovalState.APPROVED, ApprovalState.REJECTED,
        ApprovalState.EXPIRED, ApprovalState.CANCELLED,
    })
    assert ApprovalState.PENDING not in TERMINAL_STATES


def _decision(approver="alice", dtype=ApprovalDecisionType.APPROVE, at="2026-06-23T10:00:00Z"):
    return ApprovalDecision(approver=approver, decision=dtype, occurred_at=at)


def test_decision_valid_and_to_dict():
    d = _decision()
    assert d.to_dict() == {
        "approver": "alice",
        "decision": "approve",
        "occurred_at": "2026-06-23T10:00:00Z",
    }


def test_decision_is_frozen():
    d = _decision()
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.approver = "mallory"  # type: ignore[misc]


@pytest.mark.parametrize("kwargs", [
    {"approver": ""},
    {"approver": "   "},
    {"at": ""},
    {"dtype": "approve"},  # bare string, not the enum
])
def test_decision_invalid_raises(kwargs):
    with pytest.raises(ApprovalWorkflowContractError):
        _decision(**kwargs)
