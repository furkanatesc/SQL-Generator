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


from app.security.approval_workflow import ApprovalRequest  # noqa: E402


def _request(**over):
    base = dict(
        schema_version=APPROVAL_WORKFLOW_CONTRACT_VERSION,
        request_id="req-1",
        requester="bob",
        category=ApprovalCategory.SENSITIVE_DATA,
        required_approvals=2,
        state=ApprovalState.PENDING,
        decisions=(),
        reason_code=ApprovalReasonCode.OPENED,
        sql_sha256="a" * 64,
        resource_id="users",
        opened_at="2026-06-23T09:00:00Z",
        expires_at=None,
    )
    base.update(over)
    return ApprovalRequest(**base)


def test_request_valid_and_to_dict_json_safe():
    r = _request(decisions=(_decision(),))
    d = r.to_dict()
    assert d["schema_version"] == APPROVAL_WORKFLOW_CONTRACT_VERSION
    assert d["category"] == "sensitive_data"
    assert d["state"] == "pending"
    assert d["reason_code"] == "opened"
    assert d["decisions"] == [_decision().to_dict()]
    json.dumps(d)  # must not raise


def test_request_helpers():
    r = _request(decisions=(
        _decision(approver="a"), _decision(approver="b"),
        _decision(approver="c", dtype=ApprovalDecisionType.REJECT),
    ))
    assert r.count_approvals() == 2          # distinct APPROVE votes only
    assert r.is_terminal is False
    assert _request(state=ApprovalState.APPROVED).is_terminal is True


def test_request_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        _request().state = ApprovalState.APPROVED  # type: ignore[misc]


@pytest.mark.parametrize("over", [
    {"schema_version": "nope"},
    {"request_id": ""},
    {"requester": "  "},
    {"required_approvals": 0},
    {"required_approvals": -1},
    {"required_approvals": 1.0},   # non-int
    {"category": "sensitive_data"},  # bare string
    {"state": "pending"},            # bare string
    {"reason_code": "opened"},       # bare string
    {"decisions": [_decision()]},    # list, not tuple
    {"decisions": ("x",)},           # not ApprovalDecision
    {"sql_sha256": "xyz"},           # bad hex
    {"opened_at": ""},
    {"resource_id": ""},
])
def test_request_invalid_raises(over):
    with pytest.raises(ApprovalWorkflowContractError):
        _request(**over)


def test_request_to_dict_secret_free():
    secret_sql = "SELECT ssn FROM patients WHERE ssn = '123-45-6789'"
    r = _request(resource_id="patients", sql_sha256="b" * 64)
    blob = json.dumps(r.to_dict())
    assert secret_sql not in blob
    assert "123-45-6789" not in blob
