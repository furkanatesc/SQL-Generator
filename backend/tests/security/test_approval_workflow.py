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
    ApprovalRequest,
    open as open_request,
    from_permission,
    from_sensitive,
    approve,
    reject,
    cancel,
    expire,
)
from app.security.sql_permission_policy import (
    SQL_PERMISSION_POLICY_CONTRACT_VERSION,
    SQLPermissionPolicyResult, SQLPermissionDecision, SQLPermissionReasonCode,
    SQLPermissionAction, SQLPermissionResourceType,
)
from app.security.sql_sensitive_data_policy import (
    SQL_SENSITIVE_DATA_POLICY_CONTRACT_VERSION,
    SQLSensitiveDataPolicyResult, SQLSensitiveDataDecision,
    SQLSensitiveDataReasonCode, SQLSensitivityLevel, SQLSensitiveDataEvaluatedVia,
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
    {"required_approvals": True},  # bool is an int subclass — must be rejected
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


# ---------------------------------------------------------------------------
# Task 4: open factory + fail-closed builders
# ---------------------------------------------------------------------------
def test_open_yields_pending():
    r = open_request(
        request_id="req-1", requester="bob", category=ApprovalCategory.PERMISSION,
        required_approvals=2, opened_at="2026-06-23T09:00:00Z",
    )
    assert r.state == ApprovalState.PENDING
    assert r.reason_code == ApprovalReasonCode.OPENED
    assert r.decisions == ()
    assert r.required_approvals == 2
    assert r.sql_sha256 is None


def _perm_result(decision):
    # NOTE: SQLPermissionPolicyResult requires version + echoed subject/action/
    # resource identifiers; reason_code below pairs with the REQUIRES_APPROVAL path
    # but the builder only inspects .decision, so any valid reason_code is fine.
    return SQLPermissionPolicyResult(
        version=SQL_PERMISSION_POLICY_CONTRACT_VERSION,
        decision=decision,
        reason_code=SQLPermissionReasonCode.REQUIRES_APPROVAL,
        reason="needs approval",
        subject_id="bob",
        action=SQLPermissionAction.EXECUTE_SQL,
        resource_type=SQLPermissionResourceType.TABLE,
        resource_id="patients",
    )


def test_from_permission_requires_approval():
    r = from_permission(
        _perm_result(SQLPermissionDecision.REQUIRES_APPROVAL),
        request_id="req-2", requester="bob", opened_at="2026-06-23T09:00:00Z",
    )
    assert r.category == ApprovalCategory.PERMISSION
    assert r.required_approvals == 1
    assert r.sql_sha256 is None
    assert r.state == ApprovalState.PENDING


def test_from_permission_non_approval_fails_closed():
    with pytest.raises(ApprovalWorkflowContractError):
        from_permission(
            _perm_result(SQLPermissionDecision.ALLOW),
            request_id="req-3", requester="bob", opened_at="2026-06-23T09:00:00Z",
        )


def _sens_result(decision, level, sql_sha256="c" * 64):
    return SQLSensitiveDataPolicyResult(
        version=SQL_SENSITIVE_DATA_POLICY_CONTRACT_VERSION,
        decision=decision,
        sensitivity_level=level,
        matched=(),
        reason_code=SQLSensitiveDataReasonCode.SENSITIVE_MATCH_REQUIRES_APPROVAL,
        reason="sensitive",
        sql_sha256=sql_sha256,
        evaluated_via=SQLSensitiveDataEvaluatedVia.EXPLICIT_REFERENCES,
        dialect="postgres",
    )


@pytest.mark.parametrize("level,expected_n", [
    (SQLSensitivityLevel.CONFIDENTIAL, 1),
    (SQLSensitivityLevel.RESTRICTED, 2),
])
def test_from_sensitive_quorum_mapping(level, expected_n):
    r = from_sensitive(
        _sens_result(SQLSensitiveDataDecision.REQUIRES_APPROVAL, level),
        request_id="req-4", requester="bob", opened_at="2026-06-23T09:00:00Z",
        resource_id="patients",
    )
    assert r.category == ApprovalCategory.SENSITIVE_DATA
    assert r.required_approvals == expected_n
    assert r.sql_sha256 == "c" * 64
    assert r.resource_id == "patients"


def test_from_sensitive_non_approval_fails_closed():
    with pytest.raises(ApprovalWorkflowContractError):
        from_sensitive(
            _sens_result(SQLSensitiveDataDecision.DENY, SQLSensitivityLevel.RESTRICTED),
            request_id="req-5", requester="bob", opened_at="2026-06-23T09:00:00Z",
        )


# ---------------------------------------------------------------------------
# Task 5: approve / reject transitions
# ---------------------------------------------------------------------------
def _pending(required_approvals=2, requester="bob"):
    return open_request(
        request_id="req-1", requester=requester,
        category=ApprovalCategory.SENSITIVE_DATA,
        required_approvals=required_approvals, opened_at="2026-06-23T09:00:00Z",
    )


def test_approve_below_quorum_stays_pending():
    r = approve(_pending(required_approvals=2), approver="alice", occurred_at="2026-06-23T10:00:00Z")
    assert r.state == ApprovalState.PENDING
    assert r.reason_code == ApprovalReasonCode.APPROVAL_RECORDED
    assert r.count_approvals() == 1


def test_approve_reaching_quorum_approves():
    r1 = approve(_pending(required_approvals=2), approver="alice", occurred_at="2026-06-23T10:00:00Z")
    r2 = approve(r1, approver="carol", occurred_at="2026-06-23T10:05:00Z")
    assert r2.state == ApprovalState.APPROVED
    assert r2.reason_code == ApprovalReasonCode.QUORUM_MET
    assert r2.count_approvals() == 2


def test_approve_single_quorum():
    r = approve(_pending(required_approvals=1), approver="alice", occurred_at="2026-06-23T10:00:00Z")
    assert r.state == ApprovalState.APPROVED


def test_reject_vetoes():
    # a reject vetoes even when approvals have already accumulated
    r0 = approve(_pending(required_approvals=3), approver="alice", occurred_at="2026-06-23T10:00:00Z")
    assert r0.state == ApprovalState.PENDING
    r = reject(r0, approver="carol", occurred_at="2026-06-23T10:05:00Z")
    assert r.state == ApprovalState.REJECTED
    assert r.reason_code == ApprovalReasonCode.REJECTED_VETO


def test_sod_requester_cannot_vote():
    with pytest.raises(ApprovalWorkflowContractError):
        approve(_pending(requester="bob"), approver="bob", occurred_at="2026-06-23T10:00:00Z")
    with pytest.raises(ApprovalWorkflowContractError):
        reject(_pending(requester="bob"), approver="bob", occurred_at="2026-06-23T10:00:00Z")


def test_duplicate_vote_raises():
    r1 = approve(_pending(required_approvals=2), approver="alice", occurred_at="2026-06-23T10:00:00Z")
    with pytest.raises(ApprovalWorkflowContractError):
        approve(r1, approver="alice", occurred_at="2026-06-23T10:10:00Z")


def test_vote_on_terminal_raises():
    approved = approve(_pending(required_approvals=1), approver="alice", occurred_at="2026-06-23T10:00:00Z")
    assert approved.is_terminal
    with pytest.raises(ApprovalWorkflowContractError):
        approve(approved, approver="carol", occurred_at="2026-06-23T11:00:00Z")
    with pytest.raises(ApprovalWorkflowContractError):
        reject(approved, approver="carol", occurred_at="2026-06-23T11:00:00Z")


def test_approve_does_not_mutate_input():
    base = _pending(required_approvals=2)
    approve(base, approver="alice", occurred_at="2026-06-23T10:00:00Z")
    assert base.decisions == ()  # input untouched


# ---------------------------------------------------------------------------
# Task 6: cancel + expire transitions
# ---------------------------------------------------------------------------
def test_cancel_pending():
    r = cancel(_pending())
    assert r.state == ApprovalState.CANCELLED
    assert r.reason_code == ApprovalReasonCode.CANCELLED


def test_cancel_terminal_raises():
    approved = approve(_pending(required_approvals=1), approver="alice", occurred_at="2026-06-23T10:00:00Z")
    with pytest.raises(ApprovalWorkflowContractError):
        cancel(approved)


def _expiring(expires_at="2026-06-23T12:00:00Z"):
    return open_request(
        request_id="req-1", requester="bob", category=ApprovalCategory.PERMISSION,
        required_approvals=1, opened_at="2026-06-23T09:00:00Z", expires_at=expires_at,
    )


def test_expire_when_due():
    r = expire(_expiring(), now="2026-06-23T12:00:00Z")
    assert r.state == ApprovalState.EXPIRED
    assert r.reason_code == ApprovalReasonCode.EXPIRED
    # also expires strictly after
    assert expire(_expiring(), now="2026-06-23T13:00:00Z").state == ApprovalState.EXPIRED


def test_expire_before_due_raises():
    with pytest.raises(ApprovalWorkflowContractError):
        expire(_expiring(), now="2026-06-23T11:59:59Z")


def test_expire_without_expires_at_raises():
    no_expiry = open_request(
        request_id="req-1", requester="bob", category=ApprovalCategory.PERMISSION,
        required_approvals=1, opened_at="2026-06-23T09:00:00Z",
    )
    with pytest.raises(ApprovalWorkflowContractError):
        expire(no_expiry, now="2026-06-23T13:00:00Z")


def test_expire_terminal_raises():
    approved = approve(_pending(required_approvals=1), approver="alice", occurred_at="2026-06-23T10:00:00Z")
    with pytest.raises(ApprovalWorkflowContractError):
        expire(approved, now="2026-06-23T13:00:00Z")


# ---------------------------------------------------------------------------
# Task 7: package-level re-exports
# ---------------------------------------------------------------------------
def test_exported_from_package():
    import app.security as pkg
    for name in [
        "APPROVAL_WORKFLOW_CONTRACT_VERSION", "ApprovalWorkflowContractError",
        "ApprovalState", "ApprovalDecisionType", "ApprovalCategory",
        "ApprovalReasonCode", "ApprovalDecision", "ApprovalRequest",
        "TERMINAL_STATES",
    ]:
        assert hasattr(pkg, name), name
    assert "ApprovalRequest" in pkg.__all__
