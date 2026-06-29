"""Sprint 26.11 — per-contract projectors (native result -> SecurityEvalOutcome).

Each projector is pure and emits ONLY enum `.value` symbols, so covered ⊆ universe
holds (see coverage module). The projection table is the behavioral baseline.
"""
from __future__ import annotations

from typing import Mapping

from app.evaluation.security_policy_eval import Projector, SecurityEvalOutcome

CONTRACT_PERMISSION = "26.0-permission-policy"
CONTRACT_TENANT = "26.1-tenant-boundary"
CONTRACT_READ_ONLY = "26.2-read-only"
CONTRACT_RISK = "26.3-risk-classifier"
CONTRACT_SENSITIVE = "26.4-sensitive-data"
CONTRACT_PII_PHI = "26.5-pii-phi"
CONTRACT_AUDIT = "26.6-audit-event"
CONTRACT_APPROVAL = "26.7-approval"
CONTRACT_INJECTION = "26.8-prompt-injection"
CONTRACT_RESULT_SET = "26.9-result-set-privacy"
CONTRACT_CREDENTIAL = "26.10-credential-vault"


def project_permission(result) -> SecurityEvalOutcome:
    return SecurityEvalOutcome(result.decision.value, frozenset({result.reason_code.value}))


def project_tenant(result) -> SecurityEvalOutcome:
    return SecurityEvalOutcome(result.decision.value, frozenset({result.reason_code.value}))


def project_read_only(result) -> SecurityEvalOutcome:
    return SecurityEvalOutcome(result.decision.value, frozenset({result.reason_code.value}))


def project_risk(result) -> SecurityEvalOutcome:
    return SecurityEvalOutcome(
        result.risk_level.value, frozenset(s.value for s in result.signals))


def project_sensitive(result) -> SecurityEvalOutcome:
    return SecurityEvalOutcome(result.decision.value, frozenset({result.reason_code.value}))


def project_pii_phi(result) -> SecurityEvalOutcome:
    return SecurityEvalOutcome(
        result.reason_code.value, frozenset(c.value for c in result.categories))


def project_audit(result) -> SecurityEvalOutcome:
    return SecurityEvalOutcome(result.outcome.value, frozenset())


def project_approval(result) -> SecurityEvalOutcome:
    return SecurityEvalOutcome(result.state.value, frozenset({result.reason_code.value}))


def project_injection(result) -> SecurityEvalOutcome:
    return SecurityEvalOutcome(
        result.disposition.value,
        frozenset({result.reason_code.value})
        | frozenset(c.value for c in result.categories))


def project_result_set(result) -> SecurityEvalOutcome:
    return SecurityEvalOutcome(
        result.limit_disposition.value,
        frozenset({result.limit_reason_code.value})
        | frozenset(c.value for c in result.privacy_categories))


def project_credential(result) -> SecurityEvalOutcome:
    return SecurityEvalOutcome(result.decision.value, frozenset({result.reason_code.value}))


PROJECTOR_REGISTRY: Mapping[str, Projector] = {
    CONTRACT_PERMISSION: project_permission,
    CONTRACT_TENANT: project_tenant,
    CONTRACT_READ_ONLY: project_read_only,
    CONTRACT_RISK: project_risk,
    CONTRACT_SENSITIVE: project_sensitive,
    CONTRACT_PII_PHI: project_pii_phi,
    CONTRACT_AUDIT: project_audit,
    CONTRACT_APPROVAL: project_approval,
    CONTRACT_INJECTION: project_injection,
    CONTRACT_RESULT_SET: project_result_set,
    CONTRACT_CREDENTIAL: project_credential,
}
