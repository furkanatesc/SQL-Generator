"""Sprint 26.10 — Connection Credential Vault Governance Contract (Phase 7).

Pure, deterministic, secret-free, I/O-free. Decides whether a call context may
RESOLVE a connection ``secret_ref`` (a gate) and flags raw secrets leaking into
reference-only fields (an advisory signal). Never holds, stores, encrypts, or
resolves a raw password / connection string / token — it governs the *reference*
and the *decision* only; real secret storage/resolution is delegated to
infrastructure outside Phase 7.

Reuses the connection types from ``app.evaluation.connection_abstraction`` as
inputs. ``SQLConnectionProfile`` self-validates (READ_ONLY access, secret_ref
present for SECRET_REF auth), so this contract does not re-check those and emits
no ACCESS_MODE_VIOLATION / SECRET_REF_MISSING reason codes.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from app.evaluation.connection_abstraction import (
    SQLConnectionAuthMode,
    SQLConnectionProfile,
    SQLConnectionSecretRef,
    SQLConnectionEnvironment,
)
from app.security._secret_pattern_scan import scan_secret_patterns

CONNECTION_CREDENTIAL_VAULT_CONTRACT_VERSION = "connection_credential_vault_v1"


class ConnectionCredentialVaultContractError(ValueError):
    """Raised when credential-vault contract structural constraints are violated."""


class CredentialResolutionDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class CredentialCallerPurpose(str, Enum):
    EXECUTION = "execution"
    NON_EXECUTION = "non_execution"


class CredentialVaultReasonCode(str, Enum):
    ALLOWED = "allowed"
    SECRET_LEAK_SUSPECTED = "secret_leak_suspected"
    AUTH_MODE_INCONSISTENT = "auth_mode_inconsistent"
    PROVIDER_NOT_ALLOWED = "provider_not_allowed"
    ENVIRONMENT_MISMATCH = "environment_mismatch"
    TENANT_MISMATCH = "tenant_mismatch"
    PURPOSE_NOT_PERMITTED = "purpose_not_permitted"


@dataclass(frozen=True)
class CredentialLeakSignal:
    leak_detected: bool
    fields_flagged: Tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.leak_detected, bool):
            raise ConnectionCredentialVaultContractError("leak_detected must be a bool")
        if not isinstance(self.fields_flagged, tuple) or not all(
            isinstance(f, str) for f in self.fields_flagged
        ):
            raise ConnectionCredentialVaultContractError(
                "fields_flagged must be a tuple of str"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "leak_detected": self.leak_detected,
            "fields_flagged": list(self.fields_flagged),
        }


@dataclass(frozen=True)
class ConnectionCredentialVaultPolicy:
    owner_tenant: str
    allowed_providers: Tuple[str, ...]
    allowed_environments: Tuple[SQLConnectionEnvironment, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.owner_tenant, str) or not self.owner_tenant.strip():
            raise ConnectionCredentialVaultContractError("owner_tenant must be a non-empty str")
        if not isinstance(self.allowed_providers, tuple) or not all(
            isinstance(p, str) for p in self.allowed_providers
        ):
            raise ConnectionCredentialVaultContractError("allowed_providers must be a tuple of str")
        if not isinstance(self.allowed_environments, tuple) or not all(
            isinstance(e, SQLConnectionEnvironment) for e in self.allowed_environments
        ):
            raise ConnectionCredentialVaultContractError(
                "allowed_environments must be a tuple of SQLConnectionEnvironment"
            )


@dataclass(frozen=True)
class ConnectionCredentialVaultRequest:
    profile: SQLConnectionProfile
    request_environment: SQLConnectionEnvironment
    request_tenant: str
    caller_purpose: CredentialCallerPurpose

    def __post_init__(self) -> None:
        if not isinstance(self.profile, SQLConnectionProfile):
            raise ConnectionCredentialVaultContractError("profile must be a SQLConnectionProfile")
        if not isinstance(self.request_environment, SQLConnectionEnvironment):
            raise ConnectionCredentialVaultContractError(
                "request_environment must be a SQLConnectionEnvironment"
            )
        if not isinstance(self.request_tenant, str) or not self.request_tenant.strip():
            raise ConnectionCredentialVaultContractError("request_tenant must be a non-empty str")
        if not isinstance(self.caller_purpose, CredentialCallerPurpose):
            raise ConnectionCredentialVaultContractError(
                "caller_purpose must be a CredentialCallerPurpose"
            )


@dataclass(frozen=True)
class ConnectionCredentialVaultResult:
    decision: CredentialResolutionDecision
    reason_code: CredentialVaultReasonCode
    leak_signal: CredentialLeakSignal
    resolved_secret_ref: Optional[SQLConnectionSecretRef]
    contract_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.decision, CredentialResolutionDecision):
            raise ConnectionCredentialVaultContractError("decision must be a CredentialResolutionDecision")
        if not isinstance(self.reason_code, CredentialVaultReasonCode):
            raise ConnectionCredentialVaultContractError("reason_code must be a CredentialVaultReasonCode")
        if not isinstance(self.leak_signal, CredentialLeakSignal):
            raise ConnectionCredentialVaultContractError("leak_signal must be a CredentialLeakSignal")
        if self.resolved_secret_ref is not None and not isinstance(
            self.resolved_secret_ref, SQLConnectionSecretRef
        ):
            raise ConnectionCredentialVaultContractError(
                "resolved_secret_ref must be a SQLConnectionSecretRef or None"
            )
        # Secret-free invariant: a DENY never carries a resolved reference.
        if self.decision == CredentialResolutionDecision.DENY and self.resolved_secret_ref is not None:
            raise ConnectionCredentialVaultContractError(
                "resolved_secret_ref must be None on a DENY result"
            )

    def to_dict(self) -> Dict[str, Any]:
        ref = self.resolved_secret_ref
        return {
            "decision": self.decision.value,
            "reason_code": self.reason_code.value,
            "leak_signal": self.leak_signal.to_dict(),
            "resolved_secret_ref": (
                {"provider": ref.provider, "key": ref.key} if ref is not None else None
            ),
            "contract_version": self.contract_version,
        }


# ---------------------------------------------------------------------------
# evaluate — gate + leak-guard with deterministic precedence
# ---------------------------------------------------------------------------

def _scan_reference_fields(profile: SQLConnectionProfile) -> Tuple[str, ...]:
    """Return the reference-only field names that contain raw-secret patterns."""
    candidates = {
        "connection_ref": profile.connection_ref,
        "endpoint.host": profile.endpoint.host,
        "endpoint.database": profile.endpoint.database,
    }
    if profile.secret_ref is not None:
        candidates["secret_ref.provider"] = profile.secret_ref.provider
        candidates["secret_ref.key"] = profile.secret_ref.key
    flagged = [name for name, value in candidates.items() if scan_secret_patterns(value)]
    return tuple(flagged)


def _deny(
    reason: CredentialVaultReasonCode,
    leak: CredentialLeakSignal,
) -> "ConnectionCredentialVaultResult":
    return ConnectionCredentialVaultResult(
        decision=CredentialResolutionDecision.DENY,
        reason_code=reason,
        leak_signal=leak,
        resolved_secret_ref=None,
        contract_version=CONNECTION_CREDENTIAL_VAULT_CONTRACT_VERSION,
    )


def evaluate(
    request: ConnectionCredentialVaultRequest,
    policy: ConnectionCredentialVaultPolicy,
) -> ConnectionCredentialVaultResult:
    """Decide whether ``request`` may resolve its profile's secret_ref under
    ``policy`` (gate), plus an advisory leak signal. Pure, deterministic,
    fail-closed. Exactly one reason_code, by fixed precedence:
    leak -> auth_mode -> provider -> environment -> tenant -> purpose -> ALLOW.
    """
    if not isinstance(request, ConnectionCredentialVaultRequest):
        raise ConnectionCredentialVaultContractError(
            "request must be a ConnectionCredentialVaultRequest"
        )
    if not isinstance(policy, ConnectionCredentialVaultPolicy):
        raise ConnectionCredentialVaultContractError(
            "policy must be a ConnectionCredentialVaultPolicy"
        )

    profile = request.profile

    # 1. Leak scan (fail-closed hygiene invariant, highest precedence).
    flagged = _scan_reference_fields(profile)
    if flagged:
        return _deny(
            CredentialVaultReasonCode.SECRET_LEAK_SUSPECTED,
            CredentialLeakSignal(leak_detected=True, fields_flagged=flagged),
        )
    clean = CredentialLeakSignal(leak_detected=False, fields_flagged=())

    # 2. Auth-mode consistency: only SECRET_REF profiles have a vault secret to resolve.
    if profile.auth_mode != SQLConnectionAuthMode.SECRET_REF:
        return _deny(CredentialVaultReasonCode.AUTH_MODE_INCONSISTENT, clean)

    # 3. Provider allowlist.
    if profile.secret_ref.provider not in policy.allowed_providers:
        return _deny(CredentialVaultReasonCode.PROVIDER_NOT_ALLOWED, clean)

    # 4. Environment: request env must be allowed AND match the profile's env.
    if (
        request.request_environment not in policy.allowed_environments
        or request.request_environment != profile.environment
    ):
        return _deny(CredentialVaultReasonCode.ENVIRONMENT_MISMATCH, clean)

    # 5. Tenant ownership.
    if request.request_tenant != policy.owner_tenant:
        return _deny(CredentialVaultReasonCode.TENANT_MISMATCH, clean)

    # 6. Caller purpose (least-privilege).
    if request.caller_purpose != CredentialCallerPurpose.EXECUTION:
        return _deny(CredentialVaultReasonCode.PURPOSE_NOT_PERMITTED, clean)

    # 7. ALLOW — carry the reference only (never a resolved value).
    return ConnectionCredentialVaultResult(
        decision=CredentialResolutionDecision.ALLOW,
        reason_code=CredentialVaultReasonCode.ALLOWED,
        leak_signal=clean,
        resolved_secret_ref=profile.secret_ref,
        contract_version=CONNECTION_CREDENTIAL_VAULT_CONTRACT_VERSION,
    )
