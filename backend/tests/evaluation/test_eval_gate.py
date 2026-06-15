from dataclasses import FrozenInstanceError
import pytest

from app.evaluation.failure_analytics import (
    SQLFailureCategory,
    SQLFailureSeverity,
    SQLFailureAnalysisResult,
    SQLFailureCategoryCount,
    SQLFailureAnalyticsRunResult,
)
from app.evaluation.eval_gate import (
    SQL_EVAL_GATE_VERSION,
    SQLEvalGateStatus,
    SQLEvalGateSeverity,
    SQLEvalGateRuleType,
    SQLEvalGateRule,
    SQLEvalGateRuleResult,
    SQLEvalGateRunSummary,
    SQLEvalGateDecision,
    SQLEvalGateConfig,
    SQLEvalGateAggregator,
    SQLEvalGateContractError,
)


def assert_gate_consistency(decision):
    if decision.status == SQLEvalGateStatus.FAIL:
        assert len(decision.failed_rules) > 0
    elif decision.status == SQLEvalGateStatus.WARN:
        assert len(decision.warning_rules) > 0
        assert len(decision.failed_rules) == 0
    else:
        assert len(decision.failed_rules) == 0
        assert len(decision.warning_rules) == 0


def create_mock_run(
    total: int = 10,
    passed: int = 10,
    failed: int = 0,
    categories_dict: dict = None,
) -> SQLFailureAnalyticsRunResult:
    if categories_dict is None:
        categories_dict = {SQLFailureCategory.PASSED: passed}
        if failed > 0:
            categories_dict[SQLFailureCategory.VALUE_MISMATCH] = failed

    category_counts = []
    for cat, count in categories_dict.items():
        category_counts.append(SQLFailureCategoryCount(category=cat, count=count))

    case_results = []
    # Generate mock case analysis results
    for i in range(passed):
        case_results.append(
            SQLFailureAnalysisResult(
                case_id=f"case_{i:03d}",
                category=SQLFailureCategory.PASSED,
                severity=SQLFailureSeverity.INFO,
                passed=True,
                evidence="Mock passed case result."
            )
        )
    for i in range(failed):
        # Find which category is failing
        fail_cat = SQLFailureCategory.VALUE_MISMATCH
        for cat in categories_dict:
            if cat != SQLFailureCategory.PASSED:
                fail_cat = cat
                break
        case_results.append(
            SQLFailureAnalysisResult(
                case_id=f"case_fail_{i:03d}",
                category=fail_cat,
                severity=SQLFailureSeverity.MEDIUM,
                passed=False,
                evidence="Mock failed case result."
            )
        )

    pass_rate = (passed / total) if total > 0 else 0.0
    return SQLFailureAnalyticsRunResult(
        total_cases=total,
        passed_cases=passed,
        failed_cases=failed,
        pass_rate=pass_rate,
        category_counts=tuple(category_counts),
        case_results=tuple(case_results),
        duration_ms=15.5
    )


def test_gate_version_is_v1():
    assert SQL_EVAL_GATE_VERSION == "sql_eval_gate_v1"
    run = create_mock_run(total=5, passed=5, failed=0)
    decision = SQLEvalGateAggregator.aggregate(run)
    assert decision.version == "sql_eval_gate_v1"


def test_gate_decision_is_frozen():
    run = create_mock_run(total=5, passed=5, failed=0)
    decision = SQLEvalGateAggregator.aggregate(run)
    with pytest.raises(FrozenInstanceError):
        decision.status = SQLEvalGateStatus.FAIL  # type: ignore


def test_gate_passes_all_green_run():
    run = create_mock_run(total=10, passed=10, failed=0)
    decision = SQLEvalGateAggregator.aggregate(run)
    assert decision.status == SQLEvalGateStatus.PASS
    assert decision.passed is True
    assert len(decision.failed_rules) == 0
    assert len(decision.warning_rules) == 0
    assert decision.total_cases == 10
    assert decision.passed_cases == 10
    assert decision.failed_cases == 0
    assert decision.pass_rate == 1.0
    assert_gate_consistency(decision)


def test_gate_fails_empty_dataset_by_default():
    run = create_mock_run(total=0, passed=0, failed=0, categories_dict={})
    # Default config has fail_on_empty_dataset = True
    config = SQLEvalGateConfig()
    decision = SQLEvalGateAggregator.aggregate(run, config)
    assert decision.status == SQLEvalGateStatus.FAIL
    assert decision.passed is False
    assert "no test cases" in decision.decision_reason
    assert_gate_consistency(decision)


def test_gate_allows_empty_dataset_when_configured():
    run = create_mock_run(total=0, passed=0, failed=0, categories_dict={})
    
    # 1. Configured to PASS on empty
    config_pass = SQLEvalGateConfig(fail_on_empty_dataset=False, empty_dataset_status=SQLEvalGateStatus.PASS)
    decision_pass = SQLEvalGateAggregator.aggregate(run, config_pass)
    assert decision_pass.status == SQLEvalGateStatus.PASS
    assert decision_pass.passed is True
    assert_gate_consistency(decision_pass)
    
    # 2. Configured to WARN on empty
    config_warn = SQLEvalGateConfig(fail_on_empty_dataset=False, empty_dataset_status=SQLEvalGateStatus.WARN)
    decision_warn = SQLEvalGateAggregator.aggregate(run, config_warn)
    assert decision_warn.status == SQLEvalGateStatus.WARN
    assert decision_warn.passed is True
    assert_gate_consistency(decision_warn)


def test_gate_empty_dataset_warn_has_warning_rule():
    run = create_mock_run(total=0, passed=0, failed=0, categories_dict={})
    config = SQLEvalGateConfig(fail_on_empty_dataset=False, empty_dataset_status=SQLEvalGateStatus.WARN)
    decision = SQLEvalGateAggregator.aggregate(run, config)
    assert decision.status == SQLEvalGateStatus.WARN
    assert decision.passed is True
    assert len(decision.warning_rules) > 0
    assert any(r.status == SQLEvalGateStatus.WARN for r in decision.warning_rules)
    assert_gate_consistency(decision)


def test_gate_empty_dataset_configured_fail_has_failed_rule():
    run = create_mock_run(total=0, passed=0, failed=0, categories_dict={})
    config = SQLEvalGateConfig(fail_on_empty_dataset=True)
    decision = SQLEvalGateAggregator.aggregate(run, config)
    assert decision.status == SQLEvalGateStatus.FAIL
    assert decision.passed is False
    assert len(decision.failed_rules) > 0
    assert any(r.status == SQLEvalGateStatus.FAIL for r in decision.failed_rules)
    assert_gate_consistency(decision)


def test_gate_fails_when_pass_rate_below_threshold():
    # 90% pass rate
    run = create_mock_run(total=10, passed=9, failed=1)
    # Require 95%
    config = SQLEvalGateConfig(min_pass_rate=0.95)
    decision = SQLEvalGateAggregator.aggregate(run, config)
    assert decision.status == SQLEvalGateStatus.FAIL
    assert decision.passed is False
    assert any(r.rule_type == SQLEvalGateRuleType.MIN_PASS_RATE and r.status == SQLEvalGateStatus.FAIL for r in decision.failed_rules)
    assert_gate_consistency(decision)


def test_gate_fails_on_blocked_category():
    # 90% pass rate, but includes 1 UNSAFE_SQL_REJECTED (blocked by default)
    run = create_mock_run(
        total=10,
        passed=9,
        failed=1,
        categories_dict={
            SQLFailureCategory.PASSED: 9,
            SQLFailureCategory.UNSAFE_SQL_REJECTED: 1
        }
    )
    # Set min_pass_rate to 0.90 so that it passes the pass rate threshold check, isolating blocked category check
    config = SQLEvalGateConfig(
        min_pass_rate=0.90,
        blocked_categories=(SQLFailureCategory.UNSAFE_SQL_REJECTED,)
    )
    decision = SQLEvalGateAggregator.aggregate(run, config)
    assert decision.status == SQLEvalGateStatus.FAIL
    assert decision.passed is False
    assert any(r.rule_type == SQLEvalGateRuleType.BLOCK_FAILURE_CATEGORY and r.status == SQLEvalGateStatus.FAIL for r in decision.failed_rules)
    assert_gate_consistency(decision)


def test_gate_warns_on_warn_category():
    # 90% pass rate, includes 1 UNKNOWN_FAILURE (warn by default)
    run = create_mock_run(
        total=10,
        passed=9,
        failed=1,
        categories_dict={
            SQLFailureCategory.PASSED: 9,
            SQLFailureCategory.UNKNOWN_FAILURE: 1
        }
    )
    config = SQLEvalGateConfig(
        min_pass_rate=0.90,
        warn_categories=(SQLFailureCategory.UNKNOWN_FAILURE,)
    )
    decision = SQLEvalGateAggregator.aggregate(run, config)
    assert decision.status == SQLEvalGateStatus.WARN
    assert decision.passed is True
    assert len(decision.failed_rules) == 0
    assert any(r.rule_type == SQLEvalGateRuleType.BLOCK_FAILURE_CATEGORY and r.status == SQLEvalGateStatus.WARN for r in decision.warning_rules)
    assert_gate_consistency(decision)


def test_gate_fail_takes_priority_over_warn():
    # 80% pass rate. Contains both UNKNOWN_FAILURE (warn) and UNSAFE_SQL_REJECTED (fail)
    run = create_mock_run(
        total=10,
        passed=8,
        failed=2,
        categories_dict={
            SQLFailureCategory.PASSED: 8,
            SQLFailureCategory.UNKNOWN_FAILURE: 1,
            SQLFailureCategory.UNSAFE_SQL_REJECTED: 1
        }
    )
    config = SQLEvalGateConfig(
        min_pass_rate=0.80,
        blocked_categories=(SQLFailureCategory.UNSAFE_SQL_REJECTED,),
        warn_categories=(SQLFailureCategory.UNKNOWN_FAILURE,)
    )
    decision = SQLEvalGateAggregator.aggregate(run, config)
    assert decision.status == SQLEvalGateStatus.FAIL  # FAIL wins
    assert decision.passed is False
    assert_gate_consistency(decision)


def test_gate_warns_or_fails_on_unknown_failure_rate_threshold():
    # 7 passed, 3 unknown. Unknown rate is 30%
    run = create_mock_run(
        total=10,
        passed=7,
        failed=3,
        categories_dict={
            SQLFailureCategory.PASSED: 7,
            SQLFailureCategory.UNKNOWN_FAILURE: 3
        }
    )
    
    # 1. Configured as WARN on threshold exceeded
    config_warn = SQLEvalGateConfig(
        min_pass_rate=0.70,
        max_unknown_failure_rate=0.10,
        unknown_failure_rate_status=SQLEvalGateStatus.WARN
    )
    decision_warn = SQLEvalGateAggregator.aggregate(run, config_warn)
    assert decision_warn.status == SQLEvalGateStatus.WARN
    assert decision_warn.passed is True
    assert_gate_consistency(decision_warn)
    
    # 2. Configured as FAIL on threshold exceeded
    config_fail = SQLEvalGateConfig(
        min_pass_rate=0.70,
        max_unknown_failure_rate=0.10,
        unknown_failure_rate_status=SQLEvalGateStatus.FAIL
    )
    decision_fail = SQLEvalGateAggregator.aggregate(run, config_fail)
    assert decision_fail.status == SQLEvalGateStatus.FAIL
    assert decision_fail.passed is False
    assert_gate_consistency(decision_fail)


def test_gate_rule_results_are_deterministically_ordered():
    run = create_mock_run(total=5, passed=5, failed=0)
    decision = SQLEvalGateAggregator.aggregate(run)
    
    expected_order = list(SQLEvalGateRuleType)
    actual_order = [r.rule_type for r in decision.rules_evaluated]
    
    assert actual_order == expected_order


def test_gate_rejects_invalid_input():
    with pytest.raises(SQLEvalGateContractError):
        SQLEvalGateAggregator.aggregate(None)  # type: ignore
        
    with pytest.raises(SQLEvalGateContractError):
        SQLEvalGateAggregator.aggregate("invalid_run_result")  # type: ignore

    run = create_mock_run(total=5, passed=5, failed=0)
    with pytest.raises(SQLEvalGateContractError):
        SQLEvalGateAggregator.aggregate(run, config="invalid_config")  # type: ignore


def test_gate_config_rejects_invalid_pass_rate():
    with pytest.raises(SQLEvalGateContractError):
        SQLEvalGateConfig(min_pass_rate=-0.1)
        
    with pytest.raises(SQLEvalGateContractError):
        SQLEvalGateConfig(min_pass_rate=1.1)

    with pytest.raises(SQLEvalGateContractError):
        SQLEvalGateConfig(min_pass_rate="invalid_type")  # type: ignore


def test_gate_config_rejects_invalid_unknown_failure_rate():
    with pytest.raises(SQLEvalGateContractError):
        SQLEvalGateConfig(max_unknown_failure_rate=-0.01)
        
    with pytest.raises(SQLEvalGateContractError):
        SQLEvalGateConfig(max_unknown_failure_rate=1.05)

    with pytest.raises(SQLEvalGateContractError):
        SQLEvalGateConfig(max_unknown_failure_rate="invalid_type")  # type: ignore


def test_gate_config_rejects_pass_unknown_failure_rate_status():
    with pytest.raises(SQLEvalGateContractError):
        SQLEvalGateConfig(unknown_failure_rate_status=SQLEvalGateStatus.PASS)
        
    with pytest.raises(SQLEvalGateContractError):
        SQLEvalGateConfig(unknown_failure_rate_status="invalid_status")  # type: ignore


def test_gate_category_counts_are_preserved():
    run = create_mock_run(
        total=10,
        passed=8,
        failed=2,
        categories_dict={
            SQLFailureCategory.PASSED: 8,
            SQLFailureCategory.VALUE_MISMATCH: 2
        }
    )
    decision = SQLEvalGateAggregator.aggregate(run)
    
    input_counts = {cc.category: cc.count for cc in run.category_counts}
    output_counts = {cc.category: cc.count for cc in decision.category_counts}
    
    assert input_counts == output_counts
    assert isinstance(decision.category_counts, tuple)
    for cc in decision.category_counts:
        assert isinstance(cc, SQLFailureCategoryCount)


def test_gate_run_summary_rejects_inconsistent_counts():
    with pytest.raises(SQLEvalGateContractError):
        SQLEvalGateRunSummary(total_cases=10, passed_cases=8, failed_cases=1, pass_rate=0.8)


def test_gate_run_summary_rejects_inconsistent_pass_rate():
    with pytest.raises(SQLEvalGateContractError):
        # pass_rate must match passed/total = 0.8
        SQLEvalGateRunSummary(total_cases=10, passed_cases=8, failed_cases=2, pass_rate=0.7)
