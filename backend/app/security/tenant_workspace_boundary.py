"""Sprint 26.1 — Tenant / Workspace Boundary Contract (Phase 7: Security & Governance).

Maturity: MVP / early beta. NOT production-ready. This sprint does NOT build a
SaaS tenant system, RBAC, AuthN/AuthZ, a workspace API, or any tenant
persistence. It defines only the *contract* that represents, for every future
security/policy decision, the tenant + workspace boundary that decision is valid
within.

Where 26.0 (SQL permission policy) answers "is this action allowed / denied /
needs approval on this resource?", 26.1 adds the prior, coarser dimension:
"within which tenant/workspace boundary is that decision even valid?". The most
dangerous failure of a multi-tenant system is **cross-tenant leakage** — tenant A
reaching tenant B's schema, query, connection, or result data. This contract
locks the boundary vocabulary that future policy, audit, query-run, schema-sync,
and connection-registry work will reuse, so that boundary is never assumed
implicitly.

Core security principle — **fail closed** (carried over from 26.0): if the
tenant/workspace boundary is uncertain, there is no allow. Missing tenant,
missing workspace, tenant mismatch, and workspace mismatch all resolve to
``DENY``. "I don't know the boundary, so let it through" is exactly the behavior
this contract forbids.

Out of scope (deliberately NOT in this PR): user/organization model, workspace
DB tables, RBAC, AuthN/AuthZ, sessions, API endpoints, UI, admin console, billing
tenant model, real tenant persistence, query/adapter/connection-registry
integration, schema-sync tenant filtering, audit persistence, approval workflow,
and any DB or network I/O. This module imports no DB driver and performs no I/O.
Composition with the 26.0 permission policy is intentionally left to a later
sprint (no composition helper here — boundary contract stays small).
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

TENANT_WORKSPACE_BOUNDARY_CONTRACT_VERSION = "tenant_workspace_boundary_contract_v1"


class TenantWorkspaceBoundaryContractError(ValueError):
    """Raised when tenant/workspace boundary contract rules are violated."""
    pass


class TenantWorkspaceBoundaryDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    # No REQUIRES_APPROVAL: a boundary mismatch is never an approval question, it
    # is always a deny. Approval semantics live in the permission policy (26.0).


class TenantWorkspaceBoundaryReasonCode(str, Enum):
    # Allow reason
    BOUNDARY_MATCH = "boundary_match"
    # Deny reasons (fail closed)
    MISSING_TENANT = "missing_tenant"
    MISSING_WORKSPACE = "missing_workspace"
    TENANT_MISMATCH = "tenant_mismatch"
    WORKSPACE_MISMATCH = "workspace_mismatch"
    # Reserved for forward-compatibility — part of the locked vocabulary but not
    # yet emitted by validate(). UNKNOWN_BOUNDARY: a boundary kind beyond
    # tenant/workspace (e.g. region/cell) is introduced later. INVALID_BOUNDARY:
    # a structurally malformed boundary that a future, stricter validator rejects.
    UNKNOWN_BOUNDARY = "unknown_boundary"
    INVALID_BOUNDARY = "invalid_boundary"


@dataclass(frozen=True)
class TenantWorkspaceBoundary:
    """An immutable, resolved (tenant, workspace) scope.

    The canonical value object for "the boundary a decision was made within".
    Both identifiers are required and non-blank — a boundary with a missing tenant
    or workspace is not a boundary, so this object cannot represent one (fail
    closed at construction).
    """
    version: str
    tenant_id: str
    workspace_id: str

    def __post_init__(self):
        if self.version != TENANT_WORKSPACE_BOUNDARY_CONTRACT_VERSION:
            raise TenantWorkspaceBoundaryContractError(f"Invalid boundary version: {self.version}")
        if not isinstance(self.tenant_id, str) or not self.tenant_id.strip():
            raise TenantWorkspaceBoundaryContractError("tenant_id must be a non-empty string")
        if not isinstance(self.workspace_id, str) or not self.workspace_id.strip():
            raise TenantWorkspaceBoundaryContractError("workspace_id must be a non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
        }


@dataclass(frozen=True)
class TenantWorkspaceBoundaryRequest:
    """An immutable tenant/workspace boundary-validation request.

    Carries the subject's claimed (tenant, workspace) and the resource's owning
    (tenant, workspace), plus the action / resource descriptors purely for
    audit echo. All identifiers cross the trust boundary, so they are type-checked
    here; blank or mismatched values resolve to a deny in validate() (fail closed).

    Deliberately carries NO ``context`` / metadata field: the boundary contract is
    intentionally minimal, and keeping raw metadata out of the request removes any
    path by which a connection string, token, or raw SQL could reach the result.
    """
    version: str
    subject_tenant_id: str
    subject_workspace_id: str
    resource_tenant_id: str
    resource_workspace_id: str
    action: str
    resource_type: str
    resource_id: str

    def __post_init__(self):
        if self.version != TENANT_WORKSPACE_BOUNDARY_CONTRACT_VERSION:
            raise TenantWorkspaceBoundaryContractError(f"Invalid request version: {self.version}")
        for name in (
            "subject_tenant_id", "subject_workspace_id",
            "resource_tenant_id", "resource_workspace_id",
            "action", "resource_type", "resource_id",
        ):
            if not isinstance(getattr(self, name), str):
                raise TenantWorkspaceBoundaryContractError(f"{name} must be a string")


@dataclass(frozen=True)
class TenantWorkspaceBoundaryResult:
    """An immutable, audit-grade, secret-free boundary decision.

    Carries only the decision, an audit reason code, a short reason string, the
    resolved tenant/workspace (set on allow, ``None`` on deny so a mismatched or
    missing boundary is never echoed as if it were valid), and the action /
    resource descriptors. No raw context, credential, SQL, connection string, or
    token can appear here — the request has no place to carry one.
    """
    version: str
    decision: TenantWorkspaceBoundaryDecision
    reason_code: TenantWorkspaceBoundaryReasonCode
    reason: str
    tenant_id: Optional[str]
    workspace_id: Optional[str]
    action: str
    resource_type: str
    resource_id: str

    def __post_init__(self):
        if self.version != TENANT_WORKSPACE_BOUNDARY_CONTRACT_VERSION:
            raise TenantWorkspaceBoundaryContractError(f"Invalid result version: {self.version}")
        if not isinstance(self.decision, TenantWorkspaceBoundaryDecision):
            raise TenantWorkspaceBoundaryContractError("decision must be a TenantWorkspaceBoundaryDecision")
        if not isinstance(self.reason_code, TenantWorkspaceBoundaryReasonCode):
            raise TenantWorkspaceBoundaryContractError("reason_code must be a TenantWorkspaceBoundaryReasonCode")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise TenantWorkspaceBoundaryContractError("reason must be a non-empty string")
        if self.tenant_id is not None and not isinstance(self.tenant_id, str):
            raise TenantWorkspaceBoundaryContractError("tenant_id must be a string or None")
        if self.workspace_id is not None and not isinstance(self.workspace_id, str):
            raise TenantWorkspaceBoundaryContractError("workspace_id must be a string or None")
        for name in ("action", "resource_type", "resource_id"):
            if not isinstance(getattr(self, name), str):
                raise TenantWorkspaceBoundaryContractError(f"{name} must be a string")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "decision": self.decision.value,
            "reason_code": self.reason_code.value,
            "reason": self.reason,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
        }


class TenantWorkspaceBoundaryContract:
    """Deterministic, fail-closed tenant/workspace isolation boundary validator.

    Stateless: the decision is a pure function of the request. The order is
    fail-closed — every missing or mismatched identifier denies before an allow
    can be reached:

    1. Missing subject OR resource tenant       -> DENY / MISSING_TENANT
    2. Missing subject OR resource workspace     -> DENY / MISSING_WORKSPACE
    3. subject_tenant != resource_tenant         -> DENY / TENANT_MISMATCH
    4. subject_workspace != resource_workspace   -> DENY / WORKSPACE_MISMATCH
    5. tenant AND workspace match                -> ALLOW / BOUNDARY_MATCH

    The tenant check precedes the workspace check (step 3 before step 4): a subject
    can never cross into another tenant, even if a workspace id happens to collide
    across tenants.
    """

    def validate(self, request: TenantWorkspaceBoundaryRequest) -> TenantWorkspaceBoundaryResult:
        if not isinstance(request, TenantWorkspaceBoundaryRequest):
            raise TenantWorkspaceBoundaryContractError("request must be a TenantWorkspaceBoundaryRequest")

        # 1. Both sides must carry a tenant identity.
        if not request.subject_tenant_id.strip() or not request.resource_tenant_id.strip():
            return self._deny(request, TenantWorkspaceBoundaryReasonCode.MISSING_TENANT,
                              "Boundary denied: a tenant identity is missing.")

        # 2. Both sides must carry a workspace identity.
        if not request.subject_workspace_id.strip() or not request.resource_workspace_id.strip():
            return self._deny(request, TenantWorkspaceBoundaryReasonCode.MISSING_WORKSPACE,
                              "Boundary denied: a workspace identity is missing.")

        # 3. Tenants must match exactly — the hard isolation boundary.
        if request.subject_tenant_id != request.resource_tenant_id:
            return self._deny(request, TenantWorkspaceBoundaryReasonCode.TENANT_MISMATCH,
                              "Boundary denied: subject and resource belong to different tenants.")

        # 4. Workspaces must match within the (already-matched) tenant.
        if request.subject_workspace_id != request.resource_workspace_id:
            return self._deny(request, TenantWorkspaceBoundaryReasonCode.WORKSPACE_MISMATCH,
                              "Boundary denied: subject and resource belong to different workspaces.")

        # 5. Tenant and workspace both match -> inside the boundary.
        return TenantWorkspaceBoundaryResult(
            version=TENANT_WORKSPACE_BOUNDARY_CONTRACT_VERSION,
            decision=TenantWorkspaceBoundaryDecision.ALLOW,
            reason_code=TenantWorkspaceBoundaryReasonCode.BOUNDARY_MATCH,
            reason="Boundary allowed: subject and resource share the same tenant and workspace.",
            tenant_id=request.resource_tenant_id,
            workspace_id=request.resource_workspace_id,
            action=request.action,
            resource_type=request.resource_type,
            resource_id=request.resource_id,
        )

    def _deny(
        self,
        request: TenantWorkspaceBoundaryRequest,
        reason_code: TenantWorkspaceBoundaryReasonCode,
        reason: str,
    ) -> TenantWorkspaceBoundaryResult:
        # On deny the boundary is not valid, so neither tenant nor workspace is
        # echoed as resolved — a missing/mismatched scope must never look authoritative.
        return TenantWorkspaceBoundaryResult(
            version=TENANT_WORKSPACE_BOUNDARY_CONTRACT_VERSION,
            decision=TenantWorkspaceBoundaryDecision.DENY,
            reason_code=reason_code,
            reason=reason,
            tenant_id=None,
            workspace_id=None,
            action=request.action,
            resource_type=request.resource_type,
            resource_id=request.resource_id,
        )
