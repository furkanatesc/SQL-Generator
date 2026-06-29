# backend/tests/evaluation/test_security_policy_eval_suite.py
from app.evaluation.security_policy_eval import run_security_eval
from app.evaluation.security_policy_eval_cases import SECURITY_EVAL_CASES
from app.evaluation.security_policy_eval_projectors import PROJECTOR_REGISTRY
from app.evaluation.security_policy_eval_coverage import (
    build_universe, compute_coverage, COVERAGE_UNIVERSE, COVERAGE_EXCLUSIONS,
)
from app.evaluation.security_policy_eval_gate import (
    SecurityEvalGateAggregator, SecurityEvalGateStatus,
)


def _run_and_report():
    run = run_security_eval(SECURITY_EVAL_CASES, PROJECTOR_REGISTRY)
    universe = build_universe(COVERAGE_UNIVERSE)
    coverage = compute_coverage(run, universe, COVERAGE_EXCLUSIONS)
    return run, universe, coverage


def test_shipped_baseline_is_green():
    run, _, coverage = _run_and_report()
    assert run.failed == 0, [r.mismatch_detail for r in run.case_results if not r.passed]
    decision = SecurityEvalGateAggregator().aggregate(run, coverage)
    # Default config: case mismatch=FAIL (none), coverage gap=WARN. Must not FAIL.
    assert decision.status in {SecurityEvalGateStatus.PASS, SecurityEvalGateStatus.WARN}
    assert decision.passed is True


def test_covered_subset_of_universe():
    run, universe, _ = _run_and_report()
    # Enum-purity invariant: no passing case emits a symbol outside its universe.
    for r in run.case_results:
        if not r.passed:
            continue
        symbols = {r.expected.verdict} | set(r.expected.codes)
        assert symbols <= universe[r.contract_id], (r.contract_id, symbols - universe[r.contract_id])


def test_every_contract_in_universe_has_a_projector():
    assert set(COVERAGE_UNIVERSE) == set(PROJECTOR_REGISTRY)
