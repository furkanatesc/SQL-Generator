from app.security.sql_sensitive_data_policy import (
    SQL_SENSITIVE_DATA_POLICY_CONTRACT_VERSION,
    SQLSensitiveDataPolicyContractError,
    SQLSensitivityLevel,
    SQLSensitiveDataDecision,
    SQLSensitiveResourceType,
    SQLSensitiveDataReasonCode,
    SQLSensitiveDataEvaluatedVia,
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
