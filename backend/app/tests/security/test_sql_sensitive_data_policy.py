import json
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
    SQLSensitiveDataMatch,
    SQLSensitiveDataPolicyResult,
    SQLSensitiveDataPolicyRequest,
    _LEVEL_ORDER,
    _DECISION_RESTRICTIVENESS,
    _normalize_id,
    _extract_tables,
    _extract_columns,
    _has_unqualified_star,
    _star_qualifiers,
)
from app.security._sql_text import to_executable_core


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


def _match():
    return SQLSensitiveDataMatch(
        resource_type=SQLSensitiveResourceType.COLUMN, resource_id="users.ssn",
        sensitivity_level=SQLSensitivityLevel.RESTRICTED,
        action=SQLSensitiveDataDecision.DENY, policy_id="pci")


def _result(**kw):
    base = dict(
        version=SQL_SENSITIVE_DATA_POLICY_CONTRACT_VERSION,
        decision=SQLSensitiveDataDecision.DENY,
        sensitivity_level=SQLSensitivityLevel.RESTRICTED,
        matched=(_match(),),
        reason_code=SQLSensitiveDataReasonCode.SENSITIVE_MATCH_DENY,
        reason="matched",
        sql_sha256="a" * 64,
        evaluated_via=SQLSensitiveDataEvaluatedVia.EXPLICIT_REFERENCES,
        dialect="generic",
    )
    base.update(kw)
    return SQLSensitiveDataPolicyResult(**base)


def test_match_to_dict_is_json_safe():
    d = _match().to_dict()
    assert json.loads(json.dumps(d)) == d
    assert d["resource_id"] == "users.ssn"
    assert d["sensitivity_level"] == "restricted"
    assert d["action"] == "deny"


def test_result_to_dict_is_json_safe_and_secret_free():
    d = _result().to_dict()
    s = json.dumps(d)
    assert json.loads(s) == d
    assert d["decision"] == "deny"
    assert d["sensitivity_level"] == "restricted"
    assert d["evaluated_via"] == "explicit_references"
    assert d["matched"][0]["resource_id"] == "users.ssn"
    # secret-free: no raw-SQL key anywhere
    assert "sql" not in d
    assert "raw_sql" not in d


def test_result_is_frozen():
    with pytest.raises(FrozenInstanceError):
        _result().decision = SQLSensitiveDataDecision.ALLOW


def test_result_rejects_bad_version():
    with pytest.raises(SQLSensitiveDataPolicyContractError):
        _result(version="nope")


def test_result_rejects_bad_sha256():
    with pytest.raises(SQLSensitiveDataPolicyContractError):
        _result(sql_sha256="XYZ")


def test_result_allows_none_sha256():
    assert _result(sql_sha256=None).sql_sha256 is None


def test_result_rejects_non_match_in_matched():
    with pytest.raises(SQLSensitiveDataPolicyContractError):
        _result(matched=("not-a-match",))


def test_request_defaults():
    req = SQLSensitiveDataPolicyRequest(version=SQL_SENSITIVE_DATA_POLICY_CONTRACT_VERSION)
    assert req.sql is None
    assert req.referenced_tables is None
    assert req.referenced_columns is None
    assert req.dialect == "generic"


def test_request_rejects_bad_version():
    with pytest.raises(SQLSensitiveDataPolicyContractError):
        SQLSensitiveDataPolicyRequest(version="nope")


def test_request_rejects_empty_dialect():
    with pytest.raises(SQLSensitiveDataPolicyContractError):
        SQLSensitiveDataPolicyRequest(
            version=SQL_SENSITIVE_DATA_POLICY_CONTRACT_VERSION, dialect="  ")


def test_request_is_frozen():
    req = SQLSensitiveDataPolicyRequest(version=SQL_SENSITIVE_DATA_POLICY_CONTRACT_VERSION)
    with pytest.raises(FrozenInstanceError):
        req.sql = "SELECT 1"


def test_extract_tables_from_and_join():
    core = to_executable_core("SELECT a FROM Users u JOIN Orders o ON o.uid = u.id")
    assert _extract_tables(core) == {"users", "orders"}


def test_extract_tables_schema_qualified():
    core = to_executable_core("SELECT 1 FROM public.users")
    assert "public.users" in _extract_tables(core)


def test_extract_columns_qualified():
    core = to_executable_core("SELECT u.ssn, o.total FROM users u JOIN orders o ON o.uid = u.id")
    cols = _extract_columns(core)
    assert "u.ssn" in cols and "o.total" in cols


def test_has_unqualified_star():
    assert _has_unqualified_star(to_executable_core("SELECT * FROM users"))
    assert _has_unqualified_star(to_executable_core("SELECT id, * FROM users"))
    assert not _has_unqualified_star(to_executable_core("SELECT id FROM users"))


def test_star_qualifiers():
    core = to_executable_core("SELECT u.* FROM users u JOIN orders o ON o.uid = u.id")
    assert _star_qualifiers(core) == {"u"}
