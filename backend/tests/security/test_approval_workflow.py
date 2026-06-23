"""Sprint 26.7 — Approval Workflow Contract tests."""
import dataclasses
import json

import pytest

from app.security.approval_workflow import (
    APPROVAL_WORKFLOW_CONTRACT_VERSION,
    ApprovalWorkflowContractError,
    ApprovalState,
    ApprovalDecisionType,
    ApprovalCategory,
    ApprovalReasonCode,
    TERMINAL_STATES,
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
