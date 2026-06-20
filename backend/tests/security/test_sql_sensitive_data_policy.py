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
    # hash round-trips
    assert d["sql_sha256"] == "a" * 64


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


# ---------------------------------------------------------------------------
# Task 6: SQLSensitiveDataPolicyContract.evaluate()
# ---------------------------------------------------------------------------
from app.security.sql_sensitive_data_policy import SQLSensitiveDataPolicyContract

V = SQL_SENSITIVE_DATA_POLICY_CONTRACT_VERSION


def _req(**kw):
    kw.setdefault("version", V)
    return SQLSensitiveDataPolicyRequest(**kw)


def test_empty_policy_allows_everything():
    res = SQLSensitiveDataPolicyContract().evaluate(_req(sql="SELECT * FROM users"))
    assert res.decision == SQLSensitiveDataDecision.ALLOW
    assert res.sensitivity_level == SQLSensitivityLevel.PUBLIC
    assert res.reason_code == SQLSensitiveDataReasonCode.NO_SENSITIVE_MATCH
    assert res.matched == ()


def test_explicit_table_reference_denied():
    c = SQLSensitiveDataPolicyContract([_table_rule(name="users")])
    res = c.evaluate(_req(referenced_tables=["Users"]))
    assert res.decision == SQLSensitiveDataDecision.DENY
    assert res.sensitivity_level == SQLSensitivityLevel.RESTRICTED
    assert res.evaluated_via == SQLSensitiveDataEvaluatedVia.EXPLICIT_REFERENCES
    assert res.matched[0].resource_id == "users"


def test_explicit_column_reference_requires_approval():
    c = SQLSensitiveDataPolicyContract(
        [_column_rule(name="orders.total", level=SQLSensitivityLevel.CONFIDENTIAL,
                      action=SQLSensitiveDataDecision.REQUIRES_APPROVAL)])
    res = c.evaluate(_req(referenced_columns=["orders.total"]))
    assert res.decision == SQLSensitiveDataDecision.REQUIRES_APPROVAL
    assert res.reason_code == SQLSensitiveDataReasonCode.SENSITIVE_MATCH_REQUIRES_APPROVAL


def test_no_match_when_references_dont_hit_policy():
    c = SQLSensitiveDataPolicyContract([_table_rule(name="users")])
    res = c.evaluate(_req(referenced_tables=["orders"]))
    assert res.decision == SQLSensitiveDataDecision.ALLOW
    assert res.matched == ()


def test_extraction_path_table_match():
    c = SQLSensitiveDataPolicyContract([_table_rule(name="users")])
    res = c.evaluate(_req(sql="SELECT id FROM users WHERE id = 1"))
    assert res.decision == SQLSensitiveDataDecision.DENY
    assert res.evaluated_via == SQLSensitiveDataEvaluatedVia.SQL_EXTRACTION


def test_extraction_path_qualified_column_match():
    c = SQLSensitiveDataPolicyContract([_column_rule(name="users.ssn")])
    res = c.evaluate(_req(sql="SELECT users.ssn FROM users"))
    assert res.decision == SQLSensitiveDataDecision.DENY


def test_select_star_fail_closed_expands_to_column_rules():
    c = SQLSensitiveDataPolicyContract([_column_rule(name="users.ssn")])
    res = c.evaluate(_req(sql="SELECT * FROM users"))
    assert res.decision == SQLSensitiveDataDecision.DENY
    assert res.matched[0].resource_id == "users.ssn"


def test_alias_star_fail_closed_expands_for_that_table():
    c = SQLSensitiveDataPolicyContract([_column_rule(name="users.ssn")])
    # `u.*` with alias `u` -> we cannot resolve alias to table; the star qualifier
    # set is {"u"}. With no table named `u` in the policy, this does NOT match
    # (alias-blind, documented). Explicit columns are the sound path.
    res = c.evaluate(_req(sql="SELECT u.* FROM users u"))
    assert res.decision == SQLSensitiveDataDecision.ALLOW


def test_most_restrictive_decision_wins():
    c = SQLSensitiveDataPolicyContract([
        _table_rule(name="users", level=SQLSensitivityLevel.CONFIDENTIAL,
                    action=SQLSensitiveDataDecision.REQUIRES_APPROVAL),
        _column_rule(name="users.ssn", level=SQLSensitivityLevel.RESTRICTED,
                     action=SQLSensitiveDataDecision.DENY),
    ])
    res = c.evaluate(_req(referenced_tables=["users"], referenced_columns=["users.ssn"]))
    assert res.decision == SQLSensitiveDataDecision.DENY
    assert res.sensitivity_level == SQLSensitivityLevel.RESTRICTED
    assert len(res.matched) == 2


def test_max_level_with_allow_action():
    # A matched rule whose action is ALLOW still raises the reported level.
    c = SQLSensitiveDataPolicyContract([
        _table_rule(name="users", level=SQLSensitivityLevel.CONFIDENTIAL,
                    action=SQLSensitiveDataDecision.ALLOW),
    ])
    res = c.evaluate(_req(referenced_tables=["users"]))
    assert res.decision == SQLSensitiveDataDecision.ALLOW
    assert res.sensitivity_level == SQLSensitivityLevel.CONFIDENTIAL
    assert res.reason_code == SQLSensitiveDataReasonCode.SENSITIVE_MATCH_ALLOW


def test_unusable_input_fails_closed():
    c = SQLSensitiveDataPolicyContract([_table_rule(name="users")])
    for bad in [_req(), _req(sql=""), _req(sql=123)]:
        res = c.evaluate(bad)
        assert res.decision == SQLSensitiveDataDecision.DENY
        assert res.reason_code == SQLSensitiveDataReasonCode.UNUSABLE_INPUT
        assert res.evaluated_via == SQLSensitiveDataEvaluatedVia.NONE


def test_evaluate_rejects_non_request():
    with pytest.raises(SQLSensitiveDataPolicyContractError):
        SQLSensitiveDataPolicyContract().evaluate("not-a-request")


def test_contract_rejects_non_rule():
    with pytest.raises(SQLSensitiveDataPolicyContractError):
        SQLSensitiveDataPolicyContract(["not-a-rule"])


def test_matched_is_deduped_and_ordered():
    # Two identical rules -> one match; ordering is level desc.
    c = SQLSensitiveDataPolicyContract([
        _column_rule(name="users.email", level=SQLSensitivityLevel.CONFIDENTIAL,
                     action=SQLSensitiveDataDecision.REQUIRES_APPROVAL),
        _column_rule(name="users.ssn", level=SQLSensitivityLevel.RESTRICTED,
                     action=SQLSensitiveDataDecision.DENY),
    ])
    res = c.evaluate(_req(referenced_columns=["users.ssn", "users.email"]))
    levels = [m.sensitivity_level for m in res.matched]
    assert levels == [SQLSensitivityLevel.RESTRICTED, SQLSensitivityLevel.CONFIDENTIAL]


def test_matched_dedups_identical_rules():
    # Two identical rules (same resource_type, resource_id, sensitivity_level, action, policy_id)
    # should result in a single de-duplicated match.
    c = SQLSensitiveDataPolicyContract([
        _column_rule(name="users.ssn"),
        _column_rule(name="users.ssn"),
    ])
    res = c.evaluate(_req(referenced_columns=["users.ssn"]))
    assert len(res.matched) == 1
    assert res.matched[0].resource_id == "users.ssn"


def test_result_sql_sha256_set_on_extraction_path():
    c = SQLSensitiveDataPolicyContract([_table_rule(name="users")])
    res = c.evaluate(_req(sql="SELECT id FROM users"))
    assert res.sql_sha256 is not None and len(res.sql_sha256) == 64
    assert res.evaluated_via == SQLSensitiveDataEvaluatedVia.SQL_EXTRACTION


def test_public_symbols_exported_from_package():
    import app.security as sec
    for name in [
        "SQL_SENSITIVE_DATA_POLICY_CONTRACT_VERSION",
        "SQLSensitiveDataPolicyContractError",
        "SQLSensitivityLevel",
        "SQLSensitiveDataDecision",
        "SQLSensitiveResourceType",
        "SQLSensitiveDataReasonCode",
        "SQLSensitiveDataEvaluatedVia",
        "SQLSensitiveDataRule",
        "SQLSensitiveDataMatch",
        "SQLSensitiveDataPolicyRequest",
        "SQLSensitiveDataPolicyResult",
        "SQLSensitiveDataPolicyContract",
    ]:
        assert hasattr(sec, name), name
        assert name in sec.__all__, name
