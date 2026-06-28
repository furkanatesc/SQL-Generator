import pytest
from app.evaluation.connection_abstraction import (
    SQLConnectionProfile, SQLConnectionSecretRef, SQLConnectionEndpoint,
    SQLConnectionEnvironment, SQLConnectionAuthMode, SQLConnectionAccessMode,
)
from app.evaluation.multi_database_execution import SQLDatabaseDialect
from app.security.connection_credential_vault import (
    CONNECTION_CREDENTIAL_VAULT_CONTRACT_VERSION,
    ConnectionCredentialVaultContractError,
    CredentialResolutionDecision,
    CredentialCallerPurpose,
    CredentialVaultReasonCode,
    CredentialLeakSignal,
    ConnectionCredentialVaultPolicy,
    ConnectionCredentialVaultRequest,
    ConnectionCredentialVaultResult,
    evaluate,
)


def _profile(provider="aws_sm", key="prod/db", env=SQLConnectionEnvironment.PROD):
    return SQLConnectionProfile(
        connection_ref="conn-1",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        environment=env,
        endpoint=SQLConnectionEndpoint(host="db.internal", port=5432, database="app"),
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.SECRET_REF,
        secret_ref=SQLConnectionSecretRef(provider=provider, key=key),
    )


def test_version_constant():
    assert CONNECTION_CREDENTIAL_VAULT_CONTRACT_VERSION == "connection_credential_vault_v1"


def test_leak_signal_frozen_and_typed():
    sig = CredentialLeakSignal(leak_detected=False, fields_flagged=())
    with pytest.raises((AttributeError, TypeError)):
        sig.leak_detected = True  # frozen


def test_policy_rejects_non_tuple_providers():
    with pytest.raises(ConnectionCredentialVaultContractError):
        ConnectionCredentialVaultPolicy(
            owner_tenant="t1", allowed_providers="aws_sm",  # type: ignore[arg-type]
            allowed_environments=(SQLConnectionEnvironment.PROD,),
        )


def test_request_rejects_bad_purpose():
    with pytest.raises(ConnectionCredentialVaultContractError):
        ConnectionCredentialVaultRequest(
            profile=_profile(), request_environment=SQLConnectionEnvironment.PROD,
            request_tenant="t1", caller_purpose="execution",  # type: ignore[arg-type]
        )


def test_result_to_dict_is_secret_free():
    result = ConnectionCredentialVaultResult(
        decision=CredentialResolutionDecision.DENY,
        reason_code=CredentialVaultReasonCode.TENANT_MISMATCH,
        leak_signal=CredentialLeakSignal(leak_detected=False, fields_flagged=()),
        resolved_secret_ref=None,
        contract_version=CONNECTION_CREDENTIAL_VAULT_CONTRACT_VERSION,
    )
    d = result.to_dict()
    assert d["decision"] == "deny"
    assert d["reason_code"] == "tenant_mismatch"
    assert d["resolved_secret_ref"] is None
    assert d["leak_signal"] == {"leak_detected": False, "fields_flagged": []}


def test_deny_result_rejects_resolved_secret_ref():
    # DENY invariant: a denied result must never carry a resolved reference.
    with pytest.raises(ConnectionCredentialVaultContractError):
        ConnectionCredentialVaultResult(
            decision=CredentialResolutionDecision.DENY,
            reason_code=CredentialVaultReasonCode.TENANT_MISMATCH,
            leak_signal=CredentialLeakSignal(leak_detected=False, fields_flagged=()),
            resolved_secret_ref=SQLConnectionSecretRef(provider="aws_sm", key="prod/db"),
            contract_version=CONNECTION_CREDENTIAL_VAULT_CONTRACT_VERSION,
        )


def test_allow_result_to_dict_emits_reference_only():
    # ALLOW carries the secret REFERENCE (provider + key) and never a raw value.
    result = ConnectionCredentialVaultResult(
        decision=CredentialResolutionDecision.ALLOW,
        reason_code=CredentialVaultReasonCode.ALLOWED,
        leak_signal=CredentialLeakSignal(leak_detected=False, fields_flagged=()),
        resolved_secret_ref=SQLConnectionSecretRef(provider="aws_sm", key="prod/db"),
        contract_version=CONNECTION_CREDENTIAL_VAULT_CONTRACT_VERSION,
    )
    d = result.to_dict()
    assert d["decision"] == "allow"
    assert d["reason_code"] == "allowed"
    assert d["resolved_secret_ref"] == {"provider": "aws_sm", "key": "prod/db"}


# ---------------------------------------------------------------------------
# Task 3: evaluate — gate + leak-guard with deterministic precedence
# ---------------------------------------------------------------------------

def _policy(owner="t1", providers=("aws_sm",), envs=(SQLConnectionEnvironment.PROD,)):
    return ConnectionCredentialVaultPolicy(
        owner_tenant=owner, allowed_providers=providers, allowed_environments=envs,
    )


def _request(profile=None, env=SQLConnectionEnvironment.PROD, tenant="t1",
             purpose=CredentialCallerPurpose.EXECUTION):
    return ConnectionCredentialVaultRequest(
        profile=profile or _profile(),
        request_environment=env, request_tenant=tenant, caller_purpose=purpose,
    )


def test_allow_happy_path():
    r = evaluate(_request(), _policy())
    assert r.decision == CredentialResolutionDecision.ALLOW
    assert r.reason_code == CredentialVaultReasonCode.ALLOWED
    assert r.resolved_secret_ref is not None
    assert r.resolved_secret_ref.provider == "aws_sm"
    assert r.leak_signal.leak_detected is False


def test_deny_provider_not_allowed():
    r = evaluate(_request(_profile(provider="rogue_vault")), _policy(providers=("aws_sm",)))
    assert r.decision == CredentialResolutionDecision.DENY
    assert r.reason_code == CredentialVaultReasonCode.PROVIDER_NOT_ALLOWED
    assert r.resolved_secret_ref is None


def test_deny_environment_mismatch_not_in_policy():
    prof = _profile(env=SQLConnectionEnvironment.DEV)
    r = evaluate(_request(prof, env=SQLConnectionEnvironment.DEV),
                 _policy(envs=(SQLConnectionEnvironment.PROD,)))
    assert r.reason_code == CredentialVaultReasonCode.ENVIRONMENT_MISMATCH


def test_deny_environment_mismatch_request_vs_profile():
    # request env differs from the profile's own environment
    r = evaluate(_request(_profile(env=SQLConnectionEnvironment.PROD),
                          env=SQLConnectionEnvironment.STAGING),
                 _policy(envs=(SQLConnectionEnvironment.PROD, SQLConnectionEnvironment.STAGING)))
    assert r.reason_code == CredentialVaultReasonCode.ENVIRONMENT_MISMATCH


def test_deny_tenant_mismatch():
    r = evaluate(_request(tenant="t2"), _policy(owner="t1"))
    assert r.reason_code == CredentialVaultReasonCode.TENANT_MISMATCH


def test_deny_purpose_not_permitted():
    r = evaluate(_request(purpose=CredentialCallerPurpose.NON_EXECUTION), _policy())
    assert r.reason_code == CredentialVaultReasonCode.PURPOSE_NOT_PERMITTED


def test_deny_auth_mode_inconsistent_none():
    prof = SQLConnectionProfile(
        connection_ref="conn-2", dialect=SQLDatabaseDialect.POSTGRESQL,
        environment=SQLConnectionEnvironment.PROD,
        endpoint=SQLConnectionEndpoint(host="db.internal", port=5432, database="app"),
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.NONE, secret_ref=None,
    )
    r = evaluate(_request(prof), _policy())
    assert r.reason_code == CredentialVaultReasonCode.AUTH_MODE_INCONSISTENT
    assert r.resolved_secret_ref is None


def test_deny_secret_leak_suspected_in_connection_ref():
    prof = SQLConnectionProfile(
        connection_ref="postgres://u:pw@h/db",  # connection string leaked into a ref field
        dialect=SQLDatabaseDialect.POSTGRESQL, environment=SQLConnectionEnvironment.PROD,
        endpoint=SQLConnectionEndpoint(host="db.internal", port=5432, database="app"),
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.SECRET_REF,
        secret_ref=SQLConnectionSecretRef(provider="aws_sm", key="prod/db"),
    )
    r = evaluate(_request(prof), _policy())
    assert r.decision == CredentialResolutionDecision.DENY
    assert r.reason_code == CredentialVaultReasonCode.SECRET_LEAK_SUSPECTED
    assert r.leak_signal.leak_detected is True
    assert "connection_ref" in r.leak_signal.fields_flagged


def test_leak_precedence_over_tenant_mismatch():
    prof = SQLConnectionProfile(
        connection_ref="postgres://u:pw@h/db", dialect=SQLDatabaseDialect.POSTGRESQL,
        environment=SQLConnectionEnvironment.PROD,
        endpoint=SQLConnectionEndpoint(host="db.internal", port=5432, database="app"),
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.SECRET_REF,
        secret_ref=SQLConnectionSecretRef(provider="aws_sm", key="prod/db"),
    )
    r = evaluate(_request(prof, tenant="t2"), _policy(owner="t1"))
    assert r.reason_code == CredentialVaultReasonCode.SECRET_LEAK_SUSPECTED


def test_resolved_ref_carries_no_secret_value():
    r = evaluate(_request(), _policy())
    # only provider + key (a reference), never a value
    assert set(r.to_dict()["resolved_secret_ref"].keys()) == {"provider", "key"}


def test_deny_auth_mode_inconsistent_iam():
    # Spec names both NONE and IAM as AUTH_MODE_INCONSISTENT triggers.
    prof = SQLConnectionProfile(
        connection_ref="conn-iam", dialect=SQLDatabaseDialect.POSTGRESQL,
        environment=SQLConnectionEnvironment.PROD,
        endpoint=SQLConnectionEndpoint(host="db.internal", port=5432, database="app"),
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.IAM, secret_ref=None,
    )
    r = evaluate(_request(prof), _policy())
    assert r.decision == CredentialResolutionDecision.DENY
    assert r.reason_code == CredentialVaultReasonCode.AUTH_MODE_INCONSISTENT
    assert r.resolved_secret_ref is None


@pytest.mark.parametrize(
    "field, host, database",
    [
        ("endpoint.host", "postgres://u:pw@h/db", "app"),
        ("endpoint.database", "db.internal", "password=swordfish"),
    ],
)
def test_deny_secret_leak_suspected_in_endpoint_fields(field, host, database):
    # endpoint.host / endpoint.database are NOT scanned by SQLConnectionEndpoint's
    # own __post_init__, so a planted leak survives construction and must be
    # caught by evaluate's leak-guard. (connection_ref is covered separately;
    # secret_ref.provider/.key are construction-rejected and unreachable here.)
    prof = SQLConnectionProfile(
        connection_ref="conn-leak", dialect=SQLDatabaseDialect.POSTGRESQL,
        environment=SQLConnectionEnvironment.PROD,
        endpoint=SQLConnectionEndpoint(host=host, port=5432, database=database),
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.SECRET_REF,
        secret_ref=SQLConnectionSecretRef(provider="aws_sm", key="prod/db"),
    )
    r = evaluate(_request(prof), _policy())
    assert r.decision == CredentialResolutionDecision.DENY
    assert r.reason_code == CredentialVaultReasonCode.SECRET_LEAK_SUSPECTED
    assert r.leak_signal.leak_detected is True
    assert field in r.leak_signal.fields_flagged
    assert r.resolved_secret_ref is None


def test_evaluate_raises_on_non_request_argument():
    with pytest.raises(ConnectionCredentialVaultContractError):
        evaluate(None, _policy())


def test_evaluate_raises_on_non_policy_argument():
    with pytest.raises(ConnectionCredentialVaultContractError):
        evaluate(_request(), object())  # type: ignore[arg-type]


def test_auth_mode_precedence_over_environment_mismatch():
    # Profile is BOTH auth-mode-inconsistent (NONE) AND environment-mismatched
    # (DEV not in a PROD-only policy). Auth-mode sits higher on the ladder.
    prof = SQLConnectionProfile(
        connection_ref="conn-precedence", dialect=SQLDatabaseDialect.POSTGRESQL,
        environment=SQLConnectionEnvironment.DEV,
        endpoint=SQLConnectionEndpoint(host="db.internal", port=5432, database="app"),
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.NONE, secret_ref=None,
    )
    r = evaluate(_request(prof, env=SQLConnectionEnvironment.DEV),
                 _policy(envs=(SQLConnectionEnvironment.PROD,)))
    assert r.reason_code == CredentialVaultReasonCode.AUTH_MODE_INCONSISTENT


def test_public_api_exports():
    import app.security as sec
    for name in (
        "CONNECTION_CREDENTIAL_VAULT_CONTRACT_VERSION",
        "ConnectionCredentialVaultContractError",
        "CredentialResolutionDecision",
        "CredentialCallerPurpose",
        "CredentialVaultReasonCode",
        "CredentialLeakSignal",
        "ConnectionCredentialVaultPolicy",
        "ConnectionCredentialVaultRequest",
        "ConnectionCredentialVaultResult",
        "evaluate_connection_credential_vault",
        "from_credential_vault",
    ):
        assert hasattr(sec, name), f"missing export: {name}"
