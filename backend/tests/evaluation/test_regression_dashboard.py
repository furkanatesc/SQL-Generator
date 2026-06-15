from dataclasses import FrozenInstanceError
import pytest

from app.evaluation.failure_analytics import (
    SQLFailureCategory,
    SQLFailureSeverity,
    SQLFailureSignal,
    SQLFailureAnalysisResult,
    SQLFailureCategoryCount,
    SQLFailureAnalyticsRunResult,
)
from app.evaluation.eval_gate import (
    SQLEvalGateStatus,
    SQLEvalGateSeverity,
    SQLEvalGateRuleType,
    SQLEvalGateRuleResult,
    SQLEvalGateRunSummary,
    SQLEvalGateDecision,
)
from app.evaluation.regression_dashboard import (
    SQL_REGRESSION_DASHBOARD_VERSION,
    SQLRegressionDashboardContractError,
    SQLRegressionDashboardSeverity,
    SQLRegressionDashboardMetric,
    SQLRegressionDashboardFailureBreakdown,
    SQLRegressionDashboardCaseRow,
    SQLRegressionDashboardGateSummary,
    SQLRegressionDashboardReport,
    SQLRegressionDashboardConfig,
    SQLRegressionDashboardBuilder,
)


def create_mock_data(
    total: int = 10,
    passed: int = 8,
    failed: int = 2,
    categories_dict: dict = None,
    gate_status: SQLEvalGateStatus = SQLEvalGateStatus.FAIL,
    decision_reason: str = "Gate failed: test cases failed.",
    failed_rules: tuple = (),
    warning_rules: tuple = ()
):
    if categories_dict is None:
        categories_dict = {
            SQLFailureCategory.PASSED: passed,
            SQLFailureCategory.VALUE_MISMATCH: failed
        }
        
    category_counts = []
    for cat, count in categories_dict.items():
        category_counts.append(SQLFailureCategoryCount(category=cat, count=count))
        
    case_results = []
    # Passed cases
    for i in range(passed):
        case_results.append(
            SQLFailureAnalysisResult(
                case_id=f"case_{i:03d}",
                category=SQLFailureCategory.PASSED,
                severity=SQLFailureSeverity.INFO,
                passed=True,
                evidence="Passed case"
            )
        )
    # Failed cases
    for i in range(failed):
        # determine which failure category to assign
        fail_cat = SQLFailureCategory.VALUE_MISMATCH
        # Find first non-passed category in dict
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
                evidence="Failed case"
            )
        )
        
    pass_rate = (passed / total) if total > 0 else 0.0
    run_result = SQLFailureAnalyticsRunResult(
        total_cases=total,
        passed_cases=passed,
        failed_cases=failed,
        pass_rate=pass_rate,
        category_counts=tuple(category_counts),
        case_results=tuple(case_results),
        duration_ms=25.0
    )
    
    summary = SQLEvalGateRunSummary(
        total_cases=total,
        passed_cases=passed,
        failed_cases=failed,
        pass_rate=pass_rate
    )
    
    gate_decision = SQLEvalGateDecision(
        version="sql_eval_gate_v1",
        status=gate_status,
        passed=(gate_status != SQLEvalGateStatus.FAIL),
        summary=summary,
        rules_evaluated=(),
        failed_rules=tuple(failed_rules),
        warning_rules=tuple(warning_rules),
        total_cases=total,
        passed_cases=passed,
        failed_cases=failed,
        pass_rate=pass_rate,
        category_counts=tuple(category_counts),
        decision_reason=decision_reason
    )
    
    return run_result, gate_decision


def test_dashboard_version_is_v1():
    assert SQL_REGRESSION_DASHBOARD_VERSION == "sql_regression_dashboard_v1"
    run_result, gate_decision = create_mock_data()
    report = SQLRegressionDashboardBuilder.build(run_result, gate_decision)
    assert report.version == "sql_regression_dashboard_v1"


def test_dashboard_report_is_frozen():
    run_result, gate_decision = create_mock_data()
    report = SQLRegressionDashboardBuilder.build(run_result, gate_decision)
    with pytest.raises(FrozenInstanceError):
        report.total_cases = 20  # type: ignore


def test_builder_rejects_invalid_failure_analytics_input():
    _, gate_decision = create_mock_data()
    with pytest.raises(SQLRegressionDashboardContractError):
        SQLRegressionDashboardBuilder.build("invalid_run_result", gate_decision)  # type: ignore


def test_builder_rejects_invalid_gate_decision_input():
    run_result, _ = create_mock_data()
    with pytest.raises(SQLRegressionDashboardContractError):
        SQLRegressionDashboardBuilder.build(run_result, "invalid_gate_decision")  # type: ignore


def test_builder_uses_deterministic_generated_at_from_config():
    run_result, gate_decision = create_mock_data()
    custom_time = "2026-06-15T21:40:00Z"
    config = SQLRegressionDashboardConfig(generated_at=custom_time)
    report = SQLRegressionDashboardBuilder.build(run_result, gate_decision, config)
    assert report.generated_at == custom_time


def test_builder_copies_gate_summary():
    run_result, gate_decision = create_mock_data(
        gate_status=SQLEvalGateStatus.WARN,
        decision_reason="Warning: pass rate meets limit but unknown failure rate is high.",
        warning_rules=(
            SQLEvalGateRuleResult(
                rule_type=SQLEvalGateRuleType.MAX_UNKNOWN_FAILURE_RATE,
                status=SQLEvalGateStatus.WARN,
                severity=SQLEvalGateSeverity.MEDIUM,
                message="Unknown failure rate limit warning"
            ),
        )
    )
    report = SQLRegressionDashboardBuilder.build(run_result, gate_decision)
    assert report.gate_summary.status == SQLEvalGateStatus.WARN
    assert report.gate_summary.passed is True
    assert report.gate_summary.decision_reason == "Warning: pass rate meets limit but unknown failure rate is high."
    assert report.gate_summary.failed_rule_count == 0
    assert report.gate_summary.warning_rule_count == 1
    assert report.warnings == ("Unknown failure rate limit warning",)


def test_builder_copies_total_pass_fail_metrics():
    run_result, gate_decision = create_mock_data(total=10, passed=7, failed=3)
    report = SQLRegressionDashboardBuilder.build(run_result, gate_decision)
    assert report.total_cases == 10
    assert report.passed_cases == 7
    assert report.failed_cases == 3
    assert report.pass_rate == 0.7


def test_builder_computes_unknown_failure_rate():
    run_result, gate_decision = create_mock_data(
        total=10,
        passed=7,
        failed=3,
        categories_dict={
            SQLFailureCategory.PASSED: 7,
            SQLFailureCategory.UNKNOWN_FAILURE: 2,
            SQLFailureCategory.VALUE_MISMATCH: 1
        }
    )
    report = SQLRegressionDashboardBuilder.build(run_result, gate_decision)
    # unknown count is 2, rate is 2 / 10 = 0.2
    assert report.unknown_failure_rate == 0.2


def test_builder_builds_failure_breakdown():
    run_result, gate_decision = create_mock_data(
        total=10,
        passed=6,
        failed=4,
        categories_dict={
            SQLFailureCategory.PASSED: 6,
            SQLFailureCategory.UNSAFE_SQL_REJECTED: 3,
            SQLFailureCategory.VALUE_MISMATCH: 1
        }
    )
    report = SQLRegressionDashboardBuilder.build(run_result, gate_decision)
    breakdown_map = {fb.category: fb.count for fb in report.failure_breakdown}
    assert SQLFailureCategory.PASSED not in breakdown_map
    assert breakdown_map[SQLFailureCategory.UNSAFE_SQL_REJECTED] == 3
    assert breakdown_map[SQLFailureCategory.VALUE_MISMATCH] == 1


def test_builder_sorts_failure_breakdown_by_count_desc_then_category():
    run_result, gate_decision = create_mock_data(
        total=10,
        passed=3,
        failed=7,
        categories_dict={
            SQLFailureCategory.PASSED: 3,
            SQLFailureCategory.UNSAFE_SQL_REJECTED: 3,
            SQLFailureCategory.VALUE_MISMATCH: 3,
            SQLFailureCategory.ROW_COUNT_MISMATCH: 1
        }
    )
    report = SQLRegressionDashboardBuilder.build(run_result, gate_decision)
    
    # Sort order: count desc, then category.value asc. PASSED is excluded.
    # UNSAFE_SQL_REJECTED (3), VALUE_MISMATCH (3) have count = 3.
    # Order: "unsafe_sql_rejected", "value_mismatch"
    # Then ROW_COUNT_MISMATCH (1)
    
    breakdown_categories = [fb.category for fb in report.failure_breakdown]
    expected_order = [
        SQLFailureCategory.UNSAFE_SQL_REJECTED,
        SQLFailureCategory.VALUE_MISMATCH,
        SQLFailureCategory.ROW_COUNT_MISMATCH
    ]
    assert breakdown_categories == expected_order


def test_builder_builds_top_failing_cases_only_by_default():
    run_result, gate_decision = create_mock_data(total=10, passed=8, failed=2)
    report = SQLRegressionDashboardBuilder.build(run_result, gate_decision)
    
    # top_failing_cases should contain only failed cases (len = 2)
    assert len(report.top_failing_cases) == 2
    for case in report.top_failing_cases:
        assert case.passed is False


def test_builder_respects_top_failing_case_limit():
    run_result, gate_decision = create_mock_data(total=10, passed=5, failed=5)
    config = SQLRegressionDashboardConfig(top_failing_case_limit=3)
    report = SQLRegressionDashboardBuilder.build(run_result, gate_decision, config)
    assert len(report.top_failing_cases) == 3


def test_builder_can_include_passed_cases_when_configured():
    run_result, gate_decision = create_mock_data(total=5, passed=4, failed=1)
    config = SQLRegressionDashboardConfig(include_passed_cases=True)
    report = SQLRegressionDashboardBuilder.build(run_result, gate_decision, config)
    assert len(report.top_failing_cases) == 5
    passed_cases_count = sum(1 for c in report.top_failing_cases if c.passed)
    assert passed_cases_count == 4


def test_builder_sorts_top_failing_cases_deterministically():
    # Let's construct explicit cases with different severities and IDs
    category_counts = (
        SQLFailureCategoryCount(category=SQLFailureCategory.PASSED, count=1),
        SQLFailureCategoryCount(category=SQLFailureCategory.VALUE_MISMATCH, count=3),
    )
    
    case_results = (
        # passed = True
        SQLFailureAnalysisResult(
            case_id="case_passed",
            category=SQLFailureCategory.PASSED,
            severity=SQLFailureSeverity.INFO,
            passed=True,
            evidence="Passed case"
        ),
        # passed = False, severity = MEDIUM
        SQLFailureAnalysisResult(
            case_id="case_b",
            category=SQLFailureCategory.VALUE_MISMATCH,
            severity=SQLFailureSeverity.MEDIUM,
            passed=False,
            evidence="Failed case b"
        ),
        # passed = False, severity = CRITICAL
        SQLFailureAnalysisResult(
            case_id="case_a",
            category=SQLFailureCategory.VALUE_MISMATCH,
            severity=SQLFailureSeverity.CRITICAL,
            passed=False,
            evidence="Failed case a"
        ),
        # passed = False, severity = CRITICAL, but category has higher lexicographical value?
        # Let's use different categories: EMPTY_PREDICTED_SQL vs VALUE_MISMATCH
        SQLFailureAnalysisResult(
            case_id="case_c",
            category=SQLFailureCategory.EMPTY_PREDICTED_SQL,
            severity=SQLFailureSeverity.CRITICAL,
            passed=False,
            evidence="Failed case c"
        ),
    )
    
    run_result = SQLFailureAnalyticsRunResult(
        total_cases=4,
        passed_cases=1,
        failed_cases=3,
        pass_rate=0.25,
        category_counts=category_counts,
        case_results=case_results,
        duration_ms=10.0
    )
    
    summary = SQLEvalGateRunSummary(
        total_cases=4,
        passed_cases=1,
        failed_cases=3,
        pass_rate=0.25
    )
    
    gate_decision = SQLEvalGateDecision(
        version="sql_eval_gate_v1",
        status=SQLEvalGateStatus.FAIL,
        passed=False,
        summary=summary,
        rules_evaluated=(),
        failed_rules=(),
        warning_rules=(),
        total_cases=4,
        passed_cases=1,
        failed_cases=3,
        pass_rate=0.25,
        category_counts=category_counts,
        decision_reason="failed"
    )
    
    # Enable include_passed_cases to sort all of them
    config = SQLRegressionDashboardConfig(include_passed_cases=True)
    report = SQLRegressionDashboardBuilder.build(run_result, gate_decision, config)
    
    # Expected deterministic sorting:
    # 1. passed == False cases first
    # 2. severity priority desc: CRITICAL (4) > MEDIUM (2)
    #    So "case_a" (CRITICAL) and "case_c" (CRITICAL) before "case_b" (MEDIUM)
    # 3. category value asc: "empty_predicted_sql" ("case_c") before "value_mismatch" ("case_a")
    #    So "case_c" comes before "case_a"
    # 4. case_id asc (if identical on all other keys)
    # Then passed == True cases:
    #    "case_passed" (passed=True, severity=INFO, category=passed)
    #
    # Final order: "case_c", "case_a", "case_b", "case_passed"
    
    actual_ids = [c.case_id for c in report.top_failing_cases]
    assert actual_ids == ["case_c", "case_a", "case_b", "case_passed"]


def test_builder_metrics_are_in_fixed_order():
    run_result, gate_decision = create_mock_run_with_failure()
    report = SQLRegressionDashboardBuilder.build(run_result, gate_decision)
    
    expected_names = [
        "total_cases",
        "passed_cases",
        "failed_cases",
        "pass_rate",
        "unknown_failure_rate",
        "gate_status"
    ]
    actual_names = [m.name for m in report.metrics]
    assert actual_names == expected_names


def test_dashboard_config_rejects_invalid_top_failing_case_limit():
    with pytest.raises(SQLRegressionDashboardContractError):
        SQLRegressionDashboardConfig(top_failing_case_limit=-5)
        
    with pytest.raises(SQLRegressionDashboardContractError):
        SQLRegressionDashboardConfig(top_failing_case_limit="invalid_limit")  # type: ignore


# Helper for order/metric test
def create_mock_run_with_failure():
    cc = (
        SQLFailureCategoryCount(category=SQLFailureCategory.PASSED, count=1),
        SQLFailureCategoryCount(category=SQLFailureCategory.VALUE_MISMATCH, count=1),
    )
    case_res = (
        SQLFailureAnalysisResult(
            case_id="case_1", category=SQLFailureCategory.PASSED, severity=SQLFailureSeverity.INFO, passed=True, evidence="Passed"
        ),
        SQLFailureAnalysisResult(
            case_id="case_2", category=SQLFailureCategory.VALUE_MISMATCH, severity=SQLFailureSeverity.MEDIUM, passed=False, evidence="Failed"
        ),
    )
    run_res = SQLFailureAnalyticsRunResult(
        total_cases=2, passed_cases=1, failed_cases=1, pass_rate=0.5, category_counts=cc, case_results=case_res, duration_ms=1.0
    )
    sum_res = SQLEvalGateRunSummary(
        total_cases=2, passed_cases=1, failed_cases=1, pass_rate=0.5
    )
    gate_res = SQLEvalGateDecision(
        version="sql_eval_gate_v1",
        status=SQLEvalGateStatus.FAIL,
        passed=False,
        summary=sum_res,
        rules_evaluated=(),
        failed_rules=(),
        warning_rules=(),
        total_cases=2,
        passed_cases=1,
        failed_cases=1,
        pass_rate=0.5,
        category_counts=cc,
        decision_reason="failed"
    )
    return run_res, gate_res


def test_builder_rejects_mismatched_gate_total_cases():
    run_res, gate_res = create_mock_data()
    # mismatch total cases
    gate_res_mismatch = SQLEvalGateDecision(
        version=gate_res.version,
        status=gate_res.status,
        passed=gate_res.passed,
        summary=gate_res.summary,
        rules_evaluated=gate_res.rules_evaluated,
        failed_rules=gate_res.failed_rules,
        warning_rules=gate_res.warning_rules,
        total_cases=999,  # Mismatched total_cases
        passed_cases=gate_res.passed_cases,
        failed_cases=gate_res.failed_cases,
        pass_rate=gate_res.pass_rate,
        category_counts=gate_res.category_counts,
        decision_reason=gate_res.decision_reason
    )
    with pytest.raises(SQLRegressionDashboardContractError):
        SQLRegressionDashboardBuilder.build(run_res, gate_res_mismatch)


def test_builder_rejects_mismatched_gate_pass_rate():
    run_res, gate_res = create_mock_data()
    # mismatch pass_rate
    gate_res_mismatch = SQLEvalGateDecision(
        version=gate_res.version,
        status=gate_res.status,
        passed=gate_res.passed,
        summary=gate_res.summary,
        rules_evaluated=gate_res.rules_evaluated,
        failed_rules=gate_res.failed_rules,
        warning_rules=gate_res.warning_rules,
        total_cases=gate_res.total_cases,
        passed_cases=gate_res.passed_cases,
        failed_cases=gate_res.failed_cases,
        pass_rate=0.12345,  # Mismatched pass_rate
        category_counts=gate_res.category_counts,
        decision_reason=gate_res.decision_reason
    )
    with pytest.raises(SQLRegressionDashboardContractError):
        SQLRegressionDashboardBuilder.build(run_res, gate_res_mismatch)


def test_builder_rejects_mismatched_gate_category_counts():
    run_res, gate_res = create_mock_data()
    # mismatch category counts
    gate_res_mismatch = SQLEvalGateDecision(
        version=gate_res.version,
        status=gate_res.status,
        passed=gate_res.passed,
        summary=gate_res.summary,
        rules_evaluated=gate_res.rules_evaluated,
        failed_rules=gate_res.failed_rules,
        warning_rules=gate_res.warning_rules,
        total_cases=gate_res.total_cases,
        passed_cases=gate_res.passed_cases,
        failed_cases=gate_res.failed_cases,
        pass_rate=gate_res.pass_rate,
        category_counts=(SQLFailureCategoryCount(category=SQLFailureCategory.PASSED, count=0),),  # Mismatched category_counts
        decision_reason=gate_res.decision_reason
    )
    with pytest.raises(SQLRegressionDashboardContractError):
        SQLRegressionDashboardBuilder.build(run_res, gate_res_mismatch)


def test_dashboard_metric_rejects_invalid_value_type():
    with pytest.raises(SQLRegressionDashboardContractError):
        SQLRegressionDashboardMetric(
            name="test_metric",
            value=[1, 2, 3],  # invalid list type
            severity=SQLRegressionDashboardSeverity.INFO,
            description="test metric description"
        )


def test_dashboard_metric_rejects_bool_value():
    with pytest.raises(SQLRegressionDashboardContractError):
        SQLRegressionDashboardMetric(
            name="test_metric",
            value=True,  # boolean not allowed
            severity=SQLRegressionDashboardSeverity.INFO,
            description="test metric description"
        )
