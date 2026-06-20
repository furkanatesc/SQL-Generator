import pytest
from dataclasses import FrozenInstanceError

from app.security.sql_sensitive_data_policy import (
    SQL_SENSITIVE_DATA_POLICY_CONTRACT_VERSION,
    SQLSensitiveDataPolicyContractError,
    SQLSensitivityLevel,
    SQLSensitiveDataDecision,
    SQLSensitiveResourceType,
    SQLSensitiveDataReasonCode,
    SQLSensitiveDataEvaluatedVia,
    SQLSensitiveDataRule,
    _LEVEL_ORDER,
    _DECISION_RESTRICTIVENESS,
    _normalize_id,
)


def test_contract_version_is_v1():
    assert SQL_SENSITIVE_DATA_POLICY_CONTRACT_VERSION == "sql_sensitive_data_policy_contract_v1"


def test_error_is_value_error():
    assert issubclass(SQLSensitiveDataPolicyContractError, ValueError)


def test_sensitivity_level_order_is_strictly_increasing():
    assert (
        _LEVEL_ORDER[SQLSensitivityLevel.PUBLIC]
        < _LEVEL_ORDER[SQLSensitivityLevel.INTERNAL]
        < _LEVEL_ORDER[SQLSensitivityLevel.CONFIDENTIAL]
        < _LEVEL_ORDER[SQLSensitivityLevel.RESTRICTED]
    )


def test_decision_restrictiveness_deny_is_highest():
    assert (
        _DECISION_RESTRICTIVENESS[SQLSensitiveDataDecision.ALLOW]
        < _DECISION_RESTRICTIVENESS[SQLSensitiveDataDecision.REQUIRES_APPROVAL]
        < _DECISION_RESTRICTIVENESS[SQLSensitiveDataDecision.DENY]
    )


def test_normalize_id_lowercases_and_strips():
    assert _normalize_id("  Users.SSN ") == "users.ssn"


def _table_rule(name="users", level=SQLSensitivityLevel.RESTRICTED,
                action=SQLSensitiveDataDecision.DENY, policy_id=None):
    return SQLSensitiveDataRule(
        resource_type=SQLSensitiveResourceType.TABLE,
        resource_id=name, sensitivity_level=level, action=action, policy_id=policy_id)


def _column_rule(name="users.ssn", level=SQLSensitivityLevel.RESTRICTED,
                 action=SQLSensitiveDataDecision.DENY, policy_id=None):
    return SQLSensitiveDataRule(
        resource_type=SQLSensitiveResourceType.COLUMN,
        resource_id=name, sensitivity_level=level, action=action, policy_id=policy_id)


def test_rule_normalizes_resource_id():
    assert _table_rule(name="  Users ").resource_id == "users"
    assert _column_rule(name="Orders.Total").resource_id == "orders.total"


def test_rule_is_frozen():
    rule = _table_rule()
    with pytest.raises(FrozenInstanceError):
        rule.resource_id = "x"


def test_rule_table_property():
    assert _table_rule(name="users").table == "users"
    assert _column_rule(name="users.ssn").table == "users"
    assert _column_rule(name="public.users.ssn").table == "public.users"


def test_rule_rejects_non_enum_members():
    with pytest.raises(SQLSensitiveDataPolicyContractError):
        SQLSensitiveDataRule(resource_type="table", resource_id="users",
                             sensitivity_level=SQLSensitivityLevel.RESTRICTED,
                             action=SQLSensitiveDataDecision.DENY)
    with pytest.raises(SQLSensitiveDataPolicyContractError):
        SQLSensitiveDataRule(resource_type=SQLSensitiveResourceType.TABLE, resource_id="users",
                             sensitivity_level="restricted", action=SQLSensitiveDataDecision.DENY)
    with pytest.raises(SQLSensitiveDataPolicyContractError):
        SQLSensitiveDataRule(resource_type=SQLSensitiveResourceType.TABLE, resource_id="users",
                             sensitivity_level=SQLSensitivityLevel.RESTRICTED, action="deny")


def test_rule_rejects_empty_resource_id():
    with pytest.raises(SQLSensitiveDataPolicyContractError):
        _table_rule(name="   ")


def test_rule_rejects_unqualified_column():
    with pytest.raises(SQLSensitiveDataPolicyContractError):
        _column_rule(name="ssn")  # no '.' -> not table-qualified


def test_rule_rejects_blank_policy_id():
    with pytest.raises(SQLSensitiveDataPolicyContractError):
        _table_rule(policy_id="  ")
