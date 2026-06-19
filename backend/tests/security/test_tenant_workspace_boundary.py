import json
import pytest
from dataclasses import FrozenInstanceError

from app.security.tenant_workspace_boundary import (
    TENANT_WORKSPACE_BOUNDARY_CONTRACT_VERSION,
    TenantWorkspaceBoundaryContractError,
    TenantWorkspaceBoundaryDecision,
    TenantWorkspaceBoundaryReasonCode,
    TenantWorkspaceBoundary,
    TenantWorkspaceBoundaryRequest,
    TenantWorkspaceBoundaryResult,
    TenantWorkspaceBoundaryContract,
)

EXPECTED_RESULT_KEYS = {
    "version", "decision", "reason_code", "reason",
    "tenant_id", "workspace_id", "action", "resource_type", "resource_id",
}


def _request(
    *,
    subject_tenant_id="tenant-a",
    subject_workspace_id="ws-1",
    resource_tenant_id="tenant-a",
    resource_workspace_id="ws-1",
    action="read_schema",
    resource_type="schema",
    resource_id="public",
):
    return TenantWorkspaceBoundaryRequest(
        version=TENANT_WORKSPACE_BOUNDARY_CONTRACT_VERSION,
        subject_tenant_id=subject_tenant_id,
        subject_workspace_id=subject_workspace_id,
        resource_tenant_id=resource_tenant_id,
        resource_workspace_id=resource_workspace_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
    )


def test_tenant_workspace_boundary_contract_version_is_stable():
    assert TENANT_WORKSPACE_BOUNDARY_CONTRACT_VERSION == "tenant_workspace_boundary_contract_v1"


def test_tenant_workspace_boundary_request_is_immutable():
    req = _request()
    with pytest.raises((FrozenInstanceError, AttributeError)):
        req.subject_tenant_id = "tenant-b"  # type: ignore


def test_tenant_workspace_boundary_result_is_immutable():
    result = TenantWorkspaceBoundaryContract().validate(_request())
    with pytest.raises((FrozenInstanceError, AttributeError)):
        result.decision = TenantWorkspaceBoundaryDecision.DENY  # type: ignore


def test_tenant_workspace_boundary_allows_matching_scope():
    result = TenantWorkspaceBoundaryContract().validate(_request())
    assert result.decision == TenantWorkspaceBoundaryDecision.ALLOW
    assert result.reason_code == TenantWorkspaceBoundaryReasonCode.BOUNDARY_MATCH
    assert result.tenant_id == "tenant-a"
    assert result.workspace_id == "ws-1"


def test_tenant_workspace_boundary_denies_missing_subject_tenant():
    result = TenantWorkspaceBoundaryContract().validate(_request(subject_tenant_id="   "))
    assert result.decision == TenantWorkspaceBoundaryDecision.DENY
    assert result.reason_code == TenantWorkspaceBoundaryReasonCode.MISSING_TENANT


def test_tenant_workspace_boundary_denies_missing_resource_tenant():
    result = TenantWorkspaceBoundaryContract().validate(_request(resource_tenant_id=""))
    assert result.decision == TenantWorkspaceBoundaryDecision.DENY
    assert result.reason_code == TenantWorkspaceBoundaryReasonCode.MISSING_TENANT


def test_tenant_workspace_boundary_denies_missing_subject_workspace():
    result = TenantWorkspaceBoundaryContract().validate(_request(subject_workspace_id=""))
    assert result.decision == TenantWorkspaceBoundaryDecision.DENY
    assert result.reason_code == TenantWorkspaceBoundaryReasonCode.MISSING_WORKSPACE


def test_tenant_workspace_boundary_denies_missing_resource_workspace():
    result = TenantWorkspaceBoundaryContract().validate(_request(resource_workspace_id="  "))
    assert result.decision == TenantWorkspaceBoundaryDecision.DENY
    assert result.reason_code == TenantWorkspaceBoundaryReasonCode.MISSING_WORKSPACE


def test_tenant_workspace_boundary_denies_tenant_mismatch():
    result = TenantWorkspaceBoundaryContract().validate(_request(resource_tenant_id="tenant-b"))
    assert result.decision == TenantWorkspaceBoundaryDecision.DENY
    assert result.reason_code == TenantWorkspaceBoundaryReasonCode.TENANT_MISMATCH
    # A denied (mismatched) boundary must never echo a resolved tenant/workspace.
    assert result.tenant_id is None
    assert result.workspace_id is None


def test_tenant_workspace_boundary_denies_workspace_mismatch():
    result = TenantWorkspaceBoundaryContract().validate(_request(resource_workspace_id="ws-2"))
    assert result.decision == TenantWorkspaceBoundaryDecision.DENY
    assert result.reason_code == TenantWorkspaceBoundaryReasonCode.WORKSPACE_MISMATCH


def test_tenant_workspace_boundary_tenant_mismatch_wins_over_workspace_match():
    # Even if workspace ids collide across tenants, tenant isolation is checked first.
    result = TenantWorkspaceBoundaryContract().validate(
        _request(subject_tenant_id="tenant-a", resource_tenant_id="tenant-b",
                 subject_workspace_id="ws-1", resource_workspace_id="ws-1")
    )
    assert result.decision == TenantWorkspaceBoundaryDecision.DENY
    assert result.reason_code == TenantWorkspaceBoundaryReasonCode.TENANT_MISMATCH


def test_tenant_workspace_boundary_result_shape_is_deterministic():
    result = TenantWorkspaceBoundaryContract().validate(_request())
    serialized = result.to_dict()
    assert set(serialized.keys()) == EXPECTED_RESULT_KEYS
    assert serialized["version"] == TENANT_WORKSPACE_BOUNDARY_CONTRACT_VERSION
    assert serialized["decision"] == "allow"
    assert serialized["reason_code"] == "boundary_match"
    assert serialized["action"] == "read_schema"
    assert serialized["resource_type"] == "schema"


def test_tenant_workspace_boundary_result_is_json_serializable():
    result = TenantWorkspaceBoundaryContract().validate(_request(resource_tenant_id="tenant-b"))
    # Must round-trip through JSON without custom encoders.
    json.dumps(result.to_dict())


def test_tenant_workspace_boundary_result_does_not_leak_secret_like_context():
    # The request has no context/metadata field by design, so there is structurally
    # no path for a connection string, token, or raw SQL to reach the result. Lock
    # that in: the serialized result exposes exactly the fixed, safe key set and
    # nothing more, even on a denied (mismatched) boundary.
    result = TenantWorkspaceBoundaryContract().validate(
        _request(subject_tenant_id="tenant-a", resource_tenant_id="tenant-b")
    )
    serialized = result.to_dict()
    assert set(serialized.keys()) == EXPECTED_RESULT_KEYS
    assert "context" not in serialized
    # A denied boundary echoes no resolved tenant/workspace.
    assert serialized["tenant_id"] is None and serialized["workspace_id"] is None


def test_tenant_workspace_boundary_boundary_value_object_requires_full_scope():
    ok = TenantWorkspaceBoundary(
        version=TENANT_WORKSPACE_BOUNDARY_CONTRACT_VERSION,
        tenant_id="tenant-a",
        workspace_id="ws-1",
    )
    assert ok.to_dict() == {
        "version": TENANT_WORKSPACE_BOUNDARY_CONTRACT_VERSION,
        "tenant_id": "tenant-a",
        "workspace_id": "ws-1",
    }
    with pytest.raises(TenantWorkspaceBoundaryContractError):
        TenantWorkspaceBoundary(
            version=TENANT_WORKSPACE_BOUNDARY_CONTRACT_VERSION,
            tenant_id="",
            workspace_id="ws-1",
        )


def test_tenant_workspace_boundary_rejects_invalid_request_version():
    with pytest.raises(TenantWorkspaceBoundaryContractError, match="version"):
        TenantWorkspaceBoundaryRequest(
            version="wrong_version",
            subject_tenant_id="tenant-a",
            subject_workspace_id="ws-1",
            resource_tenant_id="tenant-a",
            resource_workspace_id="ws-1",
            action="read_schema",
            resource_type="schema",
            resource_id="public",
        )


def test_tenant_workspace_boundary_validate_rejects_non_request_object():
    contract = TenantWorkspaceBoundaryContract()
    with pytest.raises(TenantWorkspaceBoundaryContractError, match="request must be a TenantWorkspaceBoundaryRequest"):
        contract.validate("not-a-request")  # type: ignore


def test_tenant_workspace_boundary_does_not_import_db_adapters_or_drivers():
    import os
    import subprocess
    import sys
    import app.security
    security_dir = os.path.dirname(app.security.__file__)

    code = (
        "import sys\n"
        f"sys.path.insert(0, {repr(security_dir)})\n"
        "import tenant_workspace_boundary\n"
        "forbidden = ['psycopg2', 'psycopg', 'asyncpg', 'cx_Oracle', 'oracledb',\n"
        "             'sqlalchemy', 'socket', 'requests', 'urllib', 'http.client']\n"
        "for mod in forbidden:\n"
        "    if mod in sys.modules:\n"
        "        print(f'FORBIDDEN:{mod}')\n"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert "FORBIDDEN" not in res.stdout, f"Importing tenant_workspace_boundary loaded a forbidden module: {res.stdout}"


def test_tenant_workspace_boundary_does_not_implement_rbac_or_authn():
    # Guard against scope creep: this contract must NOT pull in RBAC/AuthN/session
    # machinery. The module source should not reference those concepts.
    import inspect
    from app.security import tenant_workspace_boundary as mod

    source = inspect.getsource(mod).lower()
    for forbidden in ("rbac", "authn", "authz", "password", "session", "login", "jwt", "oauth"):
        # Allowed only inside docstrings stating these are out of scope; assert no
        # functional symbol uses them by checking they don't appear as identifiers.
        assert f"def {forbidden}" not in source
        assert f"class {forbidden}" not in source
