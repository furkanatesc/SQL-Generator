import pytest
import json
from dataclasses import FrozenInstanceError

from app.security.sql_permission_policy import (
    SQL_PERMISSION_POLICY_CONTRACT_VERSION,
    SQLPermissionPolicyContractError,
    SQLPermissionDecision,
    SQLPermissionAction,
    SQLPermissionResourceType,
    SQLPermissionReasonCode,
    SQLPermissionPolicyRule,
    SQLPermissionPolicyRequest,
    SQLPermissionPolicyResult,
    SQLPermissionPolicyContract,
)

EXPECTED_RESULT_KEYS = {
    "version", "decision", "reason_code", "reason",
    "subject_id", "action", "resource_type", "resource_id", "policy_id",
}


def _request(
    *,
    subject_id="agent-1",
    action=SQLPermissionAction.READ_SCHEMA,
    resource_type=SQLPermissionResourceType.SCHEMA,
    resource_id="public",
    context=None,
):
    return SQLPermissionPolicyRequest(
        version=SQL_PERMISSION_POLICY_CONTRACT_VERSION,
        subject_id=subject_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        context=context or {},
    )


def _allow_rule(policy_id="rule-allow-public-schema"):
    return SQLPermissionPolicyRule(
        action=SQLPermissionAction.READ_SCHEMA,
        resource_type=SQLPermissionResourceType.SCHEMA,
        resource_id="public",
        decision=SQLPermissionDecision.ALLOW,
        policy_id=policy_id,
    )


def test_permission_policy_contract_version_is_stable():
    assert SQL_PERMISSION_POLICY_CONTRACT_VERSION == "sql_permission_policy_contract_v1"


def test_permission_policy_request_is_immutable():
    req = _request()
    with pytest.raises((FrozenInstanceError, AttributeError)):
        req.subject_id = "someone-else"  # type: ignore


def test_permission_policy_result_is_immutable():
    policy = SQLPermissionPolicyContract(rules=[_allow_rule()])
    result = policy.evaluate(_request())
    with pytest.raises((FrozenInstanceError, AttributeError)):
        result.decision = SQLPermissionDecision.ALLOW  # type: ignore


def test_permission_policy_default_denies_without_rules():
    policy = SQLPermissionPolicyContract()  # no rules configured
    result = policy.evaluate(_request())
    assert result.decision == SQLPermissionDecision.DENY
    assert result.reason_code == SQLPermissionReasonCode.POLICY_NOT_CONFIGURED


def test_permission_policy_denies_missing_subject():
    policy = SQLPermissionPolicyContract(rules=[_allow_rule()])
    result = policy.evaluate(_request(subject_id="   "))
    assert result.decision == SQLPermissionDecision.DENY
    assert result.reason_code == SQLPermissionReasonCode.MISSING_SUBJECT


def test_permission_policy_denies_missing_resource():
    policy = SQLPermissionPolicyContract(rules=[_allow_rule()])
    result = policy.evaluate(_request(resource_id=""))
    assert result.decision == SQLPermissionDecision.DENY
    assert result.reason_code == SQLPermissionReasonCode.MISSING_RESOURCE


def test_permission_policy_denies_unknown_action():
    policy = SQLPermissionPolicyContract(rules=[_allow_rule()])
    result = policy.evaluate(_request(action="frobnicate_sql"))
    assert result.decision == SQLPermissionDecision.DENY
    assert result.reason_code == SQLPermissionReasonCode.UNKNOWN_ACTION


def test_permission_policy_denies_unknown_resource():
    policy = SQLPermissionPolicyContract(rules=[_allow_rule()])
    result = policy.evaluate(_request(resource_type="tablespace"))
    assert result.decision == SQLPermissionDecision.DENY
    assert result.reason_code == SQLPermissionReasonCode.UNKNOWN_RESOURCE


def test_permission_policy_allows_explicit_allow_rule():
    policy = SQLPermissionPolicyContract(rules=[_allow_rule()])
    result = policy.evaluate(_request())
    assert result.decision == SQLPermissionDecision.ALLOW
    assert result.reason_code == SQLPermissionReasonCode.EXPLICIT_ALLOW
    assert result.policy_id == "rule-allow-public-schema"


def test_permission_policy_denies_explicit_deny_rule():
    deny_rule = SQLPermissionPolicyRule(
        action=SQLPermissionAction.EXECUTE_SQL,
        resource_type=SQLPermissionResourceType.QUERY,
        resource_id="q-1",
        decision=SQLPermissionDecision.DENY,
    )
    policy = SQLPermissionPolicyContract(rules=[deny_rule])
    result = policy.evaluate(_request(
        action=SQLPermissionAction.EXECUTE_SQL,
        resource_type=SQLPermissionResourceType.QUERY,
        resource_id="q-1",
    ))
    assert result.decision == SQLPermissionDecision.DENY
    assert result.reason_code == SQLPermissionReasonCode.EXPLICIT_DENY


def test_permission_policy_returns_requires_approval_for_approval_rule():
    approval_rule = SQLPermissionPolicyRule(
        action=SQLPermissionAction.EXECUTE_SQL,
        resource_type=SQLPermissionResourceType.QUERY,
        resource_id="q-2",
        decision=SQLPermissionDecision.REQUIRES_APPROVAL,
    )
    policy = SQLPermissionPolicyContract(rules=[approval_rule])
    result = policy.evaluate(_request(
        action=SQLPermissionAction.EXECUTE_SQL,
        resource_type=SQLPermissionResourceType.QUERY,
        resource_id="q-2",
    ))
    assert result.decision == SQLPermissionDecision.REQUIRES_APPROVAL
    assert result.reason_code == SQLPermissionReasonCode.REQUIRES_APPROVAL


def test_permission_policy_deny_overrides_allow_when_both_match():
    rules = [
        _allow_rule(),
        SQLPermissionPolicyRule(
            action=SQLPermissionAction.READ_SCHEMA,
            resource_type=SQLPermissionResourceType.SCHEMA,
            resource_id="public",
            decision=SQLPermissionDecision.DENY,
        ),
    ]
    policy = SQLPermissionPolicyContract(rules=rules)
    result = policy.evaluate(_request())
    assert result.decision == SQLPermissionDecision.DENY
    assert result.reason_code == SQLPermissionReasonCode.EXPLICIT_DENY


def test_permission_policy_default_deny_when_configured_but_no_match():
    policy = SQLPermissionPolicyContract(rules=[_allow_rule()])
    result = policy.evaluate(_request(resource_id="private"))  # no rule for "private"
    assert result.decision == SQLPermissionDecision.DENY
    assert result.reason_code == SQLPermissionReasonCode.DEFAULT_DENY


def test_permission_policy_result_shape_is_deterministic():
    policy = SQLPermissionPolicyContract(rules=[_allow_rule()])
    result = policy.evaluate(_request())
    serialized = result.to_dict()
    assert set(serialized.keys()) == EXPECTED_RESULT_KEYS
    assert serialized["version"] == SQL_PERMISSION_POLICY_CONTRACT_VERSION
    assert serialized["decision"] == "allow"
    assert serialized["action"] == "read_schema"
    assert serialized["resource_type"] == "schema"


def test_permission_policy_result_is_json_serializable():
    policy = SQLPermissionPolicyContract()
    result = policy.evaluate(_request())
    # Must round-trip through JSON without custom encoders.
    json.dumps(result.to_dict())


def test_permission_policy_result_does_not_leak_secret_like_context():
    secret_context = {
        "connection_string": "postgres://user:password@localhost/db",
        "password": "secret",
        "token": "abc",
    }
    policy = SQLPermissionPolicyContract(rules=[_allow_rule()])
    result = policy.evaluate(_request(context=secret_context))
    serialized_str = json.dumps(result.to_dict())
    assert "postgres://user:password@localhost/db" not in serialized_str
    assert "password" not in serialized_str
    assert "secret" not in serialized_str
    assert "abc" not in serialized_str
    assert "token" not in serialized_str


def test_permission_policy_does_not_import_db_adapters_or_drivers():
    import os
    import subprocess
    import sys
    import app.security
    security_dir = os.path.dirname(app.security.__file__)

    code = (
        "import sys\n"
        f"sys.path.insert(0, {repr(security_dir)})\n"
        "import sql_permission_policy\n"
        "forbidden = ['psycopg2', 'psycopg', 'asyncpg', 'cx_Oracle', 'oracledb',\n"
        "             'sqlalchemy', 'socket', 'requests', 'urllib', 'http.client']\n"
        "for mod in forbidden:\n"
        "    if mod in sys.modules:\n"
        "        print(f'FORBIDDEN:{mod}')\n"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert "FORBIDDEN" not in res.stdout, f"Importing sql_permission_policy loaded a forbidden module: {res.stdout}"


def test_permission_policy_rejects_invalid_request_version():
    with pytest.raises(SQLPermissionPolicyContractError, match="version"):
        SQLPermissionPolicyRequest(
            version="wrong_version",
            subject_id="agent-1",
            action=SQLPermissionAction.READ_SCHEMA,
            resource_type=SQLPermissionResourceType.SCHEMA,
            resource_id="public",
        )


def test_permission_policy_evaluate_rejects_non_request_object():
    policy = SQLPermissionPolicyContract()
    with pytest.raises(SQLPermissionPolicyContractError, match="request must be a SQLPermissionPolicyRequest"):
        policy.evaluate("not-a-request")  # type: ignore
