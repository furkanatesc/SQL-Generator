"""Sprint 26.11 — Policy/Security Eval harness core.

Pure, deterministic, secret-free, I/O-free meta-evaluation primitives:
the normalized outcome envelope, the blessed-case model, the runner, and
exact-match comparison. Lives in app.evaluation so app.security stays
driver-free.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Mapping, Optional, Tuple

SECURITY_POLICY_EVAL_CONTRACT_VERSION = "security_policy_eval_v1"


class SecurityPolicyEvalError(Exception):
    """Raised on harness/wiring bugs (unknown contract_id, bad projector,
    malformed case/outcome). NOT used for case outcomes."""


class EvalAdjudicationStatus(str, Enum):
    APPROVED = "approved"
    NEEDS_REVIEW = "needs_review"


@dataclass(frozen=True)
class SecurityEvalOutcome:
    """Normalized projection of any contract result. Symbol names only —
    never values — so it is secret-free by construction."""
    verdict: str
    codes: frozenset

    def __post_init__(self) -> None:
        if not isinstance(self.verdict, str) or not self.verdict:
            raise SecurityPolicyEvalError("verdict must be a non-empty str")
        if not isinstance(self.codes, frozenset):
            raise SecurityPolicyEvalError("codes must be a frozenset")
        for code in self.codes:
            if not isinstance(code, str) or not code:
                raise SecurityPolicyEvalError("each code must be a non-empty str")


Projector = Callable[[object], SecurityEvalOutcome]


@dataclass(frozen=True)
class SecurityEvalCase:
    case_id: str
    contract_id: str
    run: Callable[[], object]
    expected: SecurityEvalOutcome
    adjudication_status: EvalAdjudicationStatus = EvalAdjudicationStatus.APPROVED

    def __post_init__(self) -> None:
        if not self.case_id:
            raise SecurityPolicyEvalError("case_id required")
        if not self.contract_id:
            raise SecurityPolicyEvalError("contract_id required")
        if not callable(self.run):
            raise SecurityPolicyEvalError("run must be callable")
        if not isinstance(self.expected, SecurityEvalOutcome):
            raise SecurityPolicyEvalError("expected must be a SecurityEvalOutcome")
        if not isinstance(self.adjudication_status, EvalAdjudicationStatus):
            raise SecurityPolicyEvalError(
                "adjudication_status must be EvalAdjudicationStatus")


@dataclass(frozen=True)
class SecurityEvalCaseResult:
    case_id: str
    contract_id: str
    passed: bool
    expected: SecurityEvalOutcome
    actual: SecurityEvalOutcome
    adjudication_status: EvalAdjudicationStatus
    mismatch_detail: Optional[str]


@dataclass(frozen=True)
class SecurityEvalRunResult:
    total: int
    passed: int
    failed: int
    case_results: Tuple[SecurityEvalCaseResult, ...]
    per_contract: Mapping[str, Tuple[int, int]]   # contract_id -> (passed, total)


def _diff(expected: SecurityEvalOutcome, actual: SecurityEvalOutcome) -> Optional[str]:
    if expected == actual:
        return None
    parts = []
    if expected.verdict != actual.verdict:
        parts.append(f"verdict expected={expected.verdict!r} actual={actual.verdict!r}")
    missing = expected.codes - actual.codes
    extra = actual.codes - expected.codes
    if missing:
        parts.append(f"missing_codes={sorted(missing)}")
    if extra:
        parts.append(f"extra_codes={sorted(extra)}")
    return "; ".join(parts)


def run_security_eval(
    cases: Tuple[SecurityEvalCase, ...],
    projectors: Mapping[str, Projector],
) -> SecurityEvalRunResult:
    """Run each case through its projector and exact-match against expected.

    The only side effect is calling each case's `run` thunk (which calls the
    contract under test). Everything else is pure.
    """
    results = []
    counts: dict = {}
    for case in cases:
        projector = projectors.get(case.contract_id)
        if projector is None:
            raise SecurityPolicyEvalError(
                f"no projector for contract_id {case.contract_id!r}")
        native = case.run()
        actual = projector(native)
        if not isinstance(actual, SecurityEvalOutcome):
            raise SecurityPolicyEvalError(
                f"projector for {case.contract_id!r} did not return a "
                f"SecurityEvalOutcome")
        detail = _diff(case.expected, actual)
        passed = detail is None
        results.append(SecurityEvalCaseResult(
            case_id=case.case_id, contract_id=case.contract_id, passed=passed,
            expected=case.expected, actual=actual,
            adjudication_status=case.adjudication_status, mismatch_detail=detail))
        bucket = counts.setdefault(case.contract_id, [0, 0])
        bucket[1] += 1
        if passed:
            bucket[0] += 1
    passed_total = sum(1 for r in results if r.passed)
    return SecurityEvalRunResult(
        total=len(results), passed=passed_total,
        failed=len(results) - passed_total, case_results=tuple(results),
        per_contract={k: (v[0], v[1]) for k, v in counts.items()})
