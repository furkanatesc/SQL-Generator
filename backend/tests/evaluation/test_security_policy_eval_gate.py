from app.evaluation.security_policy_eval import (
    SecurityEvalRunResult, SecurityEvalCaseResult, SecurityEvalOutcome,
    EvalAdjudicationStatus,
)
from app.evaluation.security_policy_eval_coverage import CoverageReport
from app.evaluation.security_policy_eval_gate import (
    SecurityEvalGateAggregator, SecurityEvalGateConfig, SecurityEvalGateStatus,
)

_OUT = SecurityEvalOutcome("allow", frozenset())


def _run(total, failed):
    crs = tuple(
        SecurityEvalCaseResult(f"c{i}", "fake", i >= failed, _OUT, _OUT,
                               EvalAdjudicationStatus.APPROVED,
                               None if i >= failed else "diff")
        for i in range(total))
    return SecurityEvalRunResult(total, total - failed, failed, crs, {"fake": (total - failed, total)})


def _cov(gaps):
    return CoverageReport(10, frozenset(), frozenset(), frozenset(gaps), {})


def test_clean_run_passes():
    d = SecurityEvalGateAggregator().aggregate(_run(3, 0), _cov([]))
    assert d.status == SecurityEvalGateStatus.PASS and d.passed is True
    assert d.failed_rules == () and d.warning_rules == ()


def test_case_mismatch_fails():
    d = SecurityEvalGateAggregator().aggregate(_run(3, 1), _cov([]))
    assert d.status == SecurityEvalGateStatus.FAIL and d.passed is False
    assert "CASE_MISMATCH" in d.failed_rules


def test_coverage_gap_warns_by_default():
    d = SecurityEvalGateAggregator().aggregate(_run(3, 0), _cov(["fake:x"]))
    assert d.status == SecurityEvalGateStatus.WARN and d.passed is True
    assert "COVERAGE_GAP" in d.warning_rules


def test_coverage_gap_can_be_configured_fail():
    cfg = SecurityEvalGateConfig(coverage_gap_status=SecurityEvalGateStatus.FAIL)
    d = SecurityEvalGateAggregator().aggregate(_run(3, 0), _cov(["fake:x"]), cfg)
    assert d.status == SecurityEvalGateStatus.FAIL and d.passed is False
    assert "COVERAGE_GAP" in d.failed_rules


def test_empty_dataset_fails():
    d = SecurityEvalGateAggregator().aggregate(_run(0, 0), _cov([]))
    assert d.status == SecurityEvalGateStatus.FAIL
    assert "EMPTY_DATASET" in d.failed_rules


def test_worst_status_wins_and_version_set():
    d = SecurityEvalGateAggregator().aggregate(_run(3, 1), _cov(["fake:x"]))
    assert d.status == SecurityEvalGateStatus.FAIL          # FAIL beats WARN
    assert d.version == "security_policy_eval_v1"
    assert "CASE_MISMATCH" in d.failed_rules and "COVERAGE_GAP" in d.warning_rules
