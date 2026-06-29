"""Sprint 26.11 — coverage-completeness over the security contract surface.

Universe = introspected enum members per contract. Coverage = symbols
demonstrated by passing APPROVED cases. Gaps = (universe - exclusions) -
covered. Symbols are namespaced per contract: "contract_id:symbol".
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Tuple

from app.evaluation.security_policy_eval import (
    EvalAdjudicationStatus, SecurityPolicyEvalError, SecurityEvalRunResult,
)
from app.evaluation.security_policy_eval_projectors import (
    CONTRACT_PERMISSION, CONTRACT_TENANT, CONTRACT_READ_ONLY, CONTRACT_RISK,
    CONTRACT_SENSITIVE, CONTRACT_PII_PHI, CONTRACT_AUDIT, CONTRACT_APPROVAL,
    CONTRACT_INJECTION, CONTRACT_RESULT_SET, CONTRACT_CREDENTIAL,
)

from app.security.sql_permission_policy import SQLPermissionDecision, SQLPermissionReasonCode
from app.security.tenant_workspace_boundary import (
    TenantWorkspaceBoundaryDecision, TenantWorkspaceBoundaryReasonCode,
)
from app.security.sql_read_only_enforcement import SQLReadOnlyDecision, SQLReadOnlyReasonCode
from app.security.sql_query_risk_classifier import SQLQueryRiskLevel, SQLQueryRiskSignal
from app.security.sql_sensitive_data_policy import (
    SQLSensitiveDataDecision, SQLSensitiveDataReasonCode,
)
from app.security.sql_pii_phi_detection import SQLPiiPhiReasonCode, SQLPiiPhiCategory
from app.security.audit_event import AuditOutcome
from app.security.approval_workflow import ApprovalState, ApprovalReasonCode
from app.security.prompt_injection_defense import (
    InjectionDisposition, InjectionReasonCode, InjectionCategory,
)
from app.security.result_set_privacy_limits import (
    ResultSetLimitDisposition, ResultSetLimitReasonCode,
)
from app.security.connection_credential_vault import (
    CredentialResolutionDecision, CredentialVaultReasonCode,
)

COVERAGE_UNIVERSE: Mapping[str, Tuple[type, ...]] = {
    CONTRACT_PERMISSION: (SQLPermissionDecision, SQLPermissionReasonCode),
    CONTRACT_TENANT: (TenantWorkspaceBoundaryDecision, TenantWorkspaceBoundaryReasonCode),
    CONTRACT_READ_ONLY: (SQLReadOnlyDecision, SQLReadOnlyReasonCode),
    CONTRACT_RISK: (SQLQueryRiskLevel, SQLQueryRiskSignal),
    CONTRACT_SENSITIVE: (SQLSensitiveDataDecision, SQLSensitiveDataReasonCode),
    CONTRACT_PII_PHI: (SQLPiiPhiReasonCode, SQLPiiPhiCategory),
    CONTRACT_AUDIT: (AuditOutcome,),
    CONTRACT_APPROVAL: (ApprovalState, ApprovalReasonCode),
    CONTRACT_INJECTION: (InjectionDisposition, InjectionReasonCode, InjectionCategory),
    CONTRACT_RESULT_SET: (ResultSetLimitDisposition, ResultSetLimitReasonCode, SQLPiiPhiCategory),
    CONTRACT_CREDENTIAL: (CredentialResolutionDecision, CredentialVaultReasonCode),
}

COVERAGE_EXCLUSIONS: frozenset = frozenset({
    # 26.1 reserved reason codes, never emitted by validate().
    f"{CONTRACT_TENANT}:unknown_boundary",
    f"{CONTRACT_TENANT}:invalid_boundary",
    # 26.9 name-only categories: the result-set cell scan reuses
    # scan_value_categories, which only emits value-format detections
    # (email/ssn/iban/credit_card/phone). These 6 are name-pattern-only and
    # thus never observable in a value scan — unreachable in result-set privacy.
    f"{CONTRACT_RESULT_SET}:date_of_birth",
    f"{CONTRACT_RESULT_SET}:person_name",
    f"{CONTRACT_RESULT_SET}:postal_address",
    f"{CONTRACT_RESULT_SET}:medical_record_number",
    f"{CONTRACT_RESULT_SET}:diagnosis",
    f"{CONTRACT_RESULT_SET}:health_generic",
})


@dataclass(frozen=True)
class ContractCoverage:
    contract_id: str
    universe: frozenset
    covered: frozenset
    gaps: frozenset


@dataclass(frozen=True)
class CoverageReport:
    universe_size: int
    covered: frozenset        # qualified "contract_id:symbol"
    excluded: frozenset
    gaps: frozenset
    per_contract: Mapping[str, ContractCoverage]


def _qualify(contract_id: str, symbol: str) -> str:
    return f"{contract_id}:{symbol}"


def build_universe(registry: Mapping[str, Tuple[type, ...]]) -> Mapping[str, frozenset]:
    universe = {}
    for contract_id, enums in registry.items():
        symbols = set()
        for enum_cls in enums:
            if not (isinstance(enum_cls, type) and issubclass(enum_cls, Enum)):
                raise SecurityPolicyEvalError(
                    f"COVERAGE_UNIVERSE[{contract_id!r}] has non-enum {enum_cls!r}")
            for member in enum_cls:
                symbols.add(member.value)
        universe[contract_id] = frozenset(symbols)
    return universe


def compute_coverage(
    run_result: SecurityEvalRunResult,
    universe: Mapping[str, frozenset],
    exclusions: frozenset,
) -> CoverageReport:
    covered_by_contract: dict = {}
    for r in run_result.case_results:
        if not r.passed or r.adjudication_status != EvalAdjudicationStatus.APPROVED:
            continue
        bucket = covered_by_contract.setdefault(r.contract_id, set())
        bucket.add(r.expected.verdict)
        bucket.update(r.expected.codes)

    per_contract = {}
    all_covered, all_gaps = set(), set()
    universe_size = 0
    for contract_id, symbols in universe.items():
        covered = frozenset(covered_by_contract.get(contract_id, set()) & symbols)
        excluded_here = frozenset(
            s for s in symbols if _qualify(contract_id, s) in exclusions)
        gaps = frozenset(symbols - covered - excluded_here)
        per_contract[contract_id] = ContractCoverage(
            contract_id, frozenset(symbols), covered, gaps)
        universe_size += len(symbols)
        all_covered.update(_qualify(contract_id, s) for s in covered)
        all_gaps.update(_qualify(contract_id, s) for s in gaps)

    return CoverageReport(
        universe_size=universe_size, covered=frozenset(all_covered),
        excluded=frozenset(exclusions), gaps=frozenset(all_gaps),
        per_contract=per_contract)
