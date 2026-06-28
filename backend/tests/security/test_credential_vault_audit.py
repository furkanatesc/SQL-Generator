# backend/tests/security/test_credential_vault_audit.py
from app.security.audit_event import (
    AuditCategory, AuditOutcome, AuditSeverity, AuditActor, AuditResource,
    from_credential_vault, verify_chain,
)
from app.security.connection_credential_vault import (
    ConnectionCredentialVaultResult, CredentialResolutionDecision,
    CredentialVaultReasonCode, CredentialLeakSignal,
    CONNECTION_CREDENTIAL_VAULT_CONTRACT_VERSION,
)

_ACTOR = AuditActor(subject="svc-exec", tenant="t1")
_RES = AuditResource(type="connection", id="conn-1")


def _result(decision, reason, leak=False, fields=()):
    return ConnectionCredentialVaultResult(
        decision=decision, reason_code=reason,
        leak_signal=CredentialLeakSignal(leak_detected=leak, fields_flagged=fields),
        resolved_secret_ref=None,
        contract_version=CONNECTION_CREDENTIAL_VAULT_CONTRACT_VERSION,
    )


def test_category_member_exists():
    assert AuditCategory.CONNECTION_CREDENTIAL.value == "connection_credential"


def test_allow_maps_to_allowed_info():
    from app.evaluation.connection_abstraction import SQLConnectionSecretRef
    res = ConnectionCredentialVaultResult(
        decision=CredentialResolutionDecision.ALLOW,
        reason_code=CredentialVaultReasonCode.ALLOWED,
        leak_signal=CredentialLeakSignal(leak_detected=False, fields_flagged=()),
        resolved_secret_ref=SQLConnectionSecretRef(provider="aws_sm", key="prod/db"),
        contract_version=CONNECTION_CREDENTIAL_VAULT_CONTRACT_VERSION,
    )
    ev = from_credential_vault(res, event_id="e1", occurred_at="2026-06-28T00:00:00Z",
                              actor=_ACTOR, resource=_RES)
    assert ev.category == AuditCategory.CONNECTION_CREDENTIAL
    assert ev.outcome == AuditOutcome.ALLOWED
    assert ev.severity == AuditSeverity.INFO
    # Secret-free invariant: the ALLOW path serializes ONLY the reference
    # (provider/key), never a resolved secret value or any extra field.
    assert ev.details["resolved_secret_ref"] == {"provider": "aws_sm", "key": "prod/db"}
    assert ev.to_dict()["details"]["resolved_secret_ref"] == {"provider": "aws_sm", "key": "prod/db"}


def test_deny_tenant_maps_to_denied_medium():
    ev = from_credential_vault(
        _result(CredentialResolutionDecision.DENY, CredentialVaultReasonCode.TENANT_MISMATCH),
        event_id="e1", occurred_at="2026-06-28T00:00:00Z", actor=_ACTOR, resource=_RES)
    assert ev.outcome == AuditOutcome.DENIED
    assert ev.severity == AuditSeverity.MEDIUM


def test_deny_leak_maps_to_denied_high():
    ev = from_credential_vault(
        _result(CredentialResolutionDecision.DENY,
                CredentialVaultReasonCode.SECRET_LEAK_SUSPECTED, leak=True,
                fields=("connection_ref",)),
        event_id="e1", occurred_at="2026-06-28T00:00:00Z", actor=_ACTOR, resource=_RES)
    assert ev.outcome == AuditOutcome.DENIED
    assert ev.severity == AuditSeverity.HIGH


def test_event_is_secret_free_and_chains():
    e1 = from_credential_vault(
        _result(CredentialResolutionDecision.DENY, CredentialVaultReasonCode.PROVIDER_NOT_ALLOWED),
        event_id="e1", occurred_at="2026-06-28T00:00:00Z", actor=_ACTOR, resource=_RES)
    e2 = from_credential_vault(
        _result(CredentialResolutionDecision.DENY, CredentialVaultReasonCode.TENANT_MISMATCH),
        event_id="e2", occurred_at="2026-06-28T00:00:01Z", actor=_ACTOR, resource=_RES, prev=e1)
    assert verify_chain([e1, e2]) is None
    assert "password" not in str(e1.to_dict()).lower()
