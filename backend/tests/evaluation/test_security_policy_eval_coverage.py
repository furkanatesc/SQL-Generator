# backend/tests/evaluation/test_security_policy_eval_coverage.py
import pytest
from enum import Enum

from app.evaluation.security_policy_eval import (
    SecurityEvalRunResult, SecurityEvalCaseResult, SecurityEvalOutcome,
    EvalAdjudicationStatus, SecurityPolicyEvalError,
)
from app.evaluation.security_policy_eval_coverage import (
    build_universe, compute_coverage, COVERAGE_UNIVERSE, COVERAGE_EXCLUSIONS,
)


class _Verdict(str, Enum):
    A = "a"
    B = "b"


class _Code(str, Enum):
    X = "x"
    Y = "y"


def _result(passed, verdict, codes, status=EvalAdjudicationStatus.APPROVED, cid="fake"):
    out = SecurityEvalOutcome(verdict, frozenset(codes))
    return SecurityEvalRunResult(
        total=1, passed=int(passed), failed=int(not passed),
        case_results=(SecurityEvalCaseResult("c", cid, passed, out, out, status, None),),
        per_contract={cid: (int(passed), 1)})


def test_build_universe_collects_member_values():
    uni = build_universe({"fake": (_Verdict, _Code)})
    assert uni["fake"] == frozenset({"a", "b", "x", "y"})


def test_build_universe_rejects_non_enum():
    with pytest.raises(SecurityPolicyEvalError):
        build_universe({"fake": (str,)})


def test_passing_approved_case_covers_its_symbols():
    uni = {"fake": frozenset({"a", "b", "x", "y"})}
    report = compute_coverage(_result(True, "a", ["x"]), uni, frozenset())
    assert "fake:a" in report.covered and "fake:x" in report.covered
    assert "fake:b" in report.gaps and "fake:y" in report.gaps


def test_failing_case_does_not_cover():
    uni = {"fake": frozenset({"a", "b"})}
    report = compute_coverage(_result(False, "a", []), uni, frozenset())
    assert "fake:a" in report.gaps


def test_unapproved_case_does_not_cover():
    uni = {"fake": frozenset({"a", "b"})}
    report = compute_coverage(
        _result(True, "a", [], status=EvalAdjudicationStatus.NEEDS_REVIEW), uni, frozenset())
    assert "fake:a" in report.gaps


def test_exclusion_is_not_a_gap():
    uni = {"fake": frozenset({"a", "b"})}
    report = compute_coverage(_result(True, "a", []), uni, frozenset({"fake:b"}))
    assert "fake:b" not in report.gaps
    assert "fake:b" in report.excluded


def test_real_universe_registry_has_all_eleven():
    assert len(COVERAGE_UNIVERSE) == 11
