import pytest
from app.evaluation.security_policy_eval import (
    SecurityEvalOutcome, SecurityEvalCase, SecurityEvalCaseResult,
    SecurityEvalRunResult, EvalAdjudicationStatus, SecurityPolicyEvalError,
    run_security_eval, SECURITY_POLICY_EVAL_CONTRACT_VERSION,
)


def _outcome(verdict="allow", codes=("ok",)):
    return SecurityEvalOutcome(verdict, frozenset(codes))


def test_version_constant():
    assert SECURITY_POLICY_EVAL_CONTRACT_VERSION == "security_policy_eval_v1"


def test_outcome_rejects_empty_verdict():
    with pytest.raises(SecurityPolicyEvalError):
        SecurityEvalOutcome("", frozenset())


def test_outcome_rejects_non_frozenset_codes():
    with pytest.raises(SecurityPolicyEvalError):
        SecurityEvalOutcome("allow", {"ok"})  # set, not frozenset


def test_passing_case_matches_exactly():
    case = SecurityEvalCase(
        case_id="c1", contract_id="fake",
        run=lambda: "native", expected=_outcome("allow", ("ok",)))
    projectors = {"fake": lambda native: _outcome("allow", ("ok",))}
    run = run_security_eval((case,), projectors)
    assert run.total == 1 and run.passed == 1 and run.failed == 0
    r = run.case_results[0]
    assert r.passed is True and r.mismatch_detail is None
    assert run.per_contract == {"fake": (1, 1)}


def test_extra_code_fails():
    case = SecurityEvalCase("c", "fake", lambda: "n", _outcome("allow", ("ok",)))
    projectors = {"fake": lambda n: _outcome("allow", ("ok", "surprise"))}
    run = run_security_eval((case,), projectors)
    assert run.failed == 1
    assert "extra_codes" in run.case_results[0].mismatch_detail


def test_missing_code_and_verdict_fail():
    case = SecurityEvalCase("c", "fake", lambda: "n", _outcome("allow", ("ok", "x")))
    projectors = {"fake": lambda n: _outcome("deny", ("ok",))}
    detail = run_security_eval((case,), projectors).case_results[0].mismatch_detail
    assert "verdict" in detail and "missing_codes" in detail


def test_unknown_contract_id_raises():
    case = SecurityEvalCase("c", "missing", lambda: "n", _outcome())
    with pytest.raises(SecurityPolicyEvalError):
        run_security_eval((case,), {})


def test_projector_must_return_outcome():
    case = SecurityEvalCase("c", "fake", lambda: "n", _outcome())
    with pytest.raises(SecurityPolicyEvalError):
        run_security_eval((case,), {"fake": lambda n: "not-an-outcome"})
