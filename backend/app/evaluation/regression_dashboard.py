from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Tuple

from app.evaluation.failure_analytics import (
    SQLFailureCategory,
    SQLFailureSeverity,
    SQLFailureSignal,
    SQLFailureAnalyticsRunResult,
    SQLFailureCategoryCount,
)
from app.evaluation.eval_gate import (
    SQLEvalGateStatus,
    SQLEvalGateRuleType,
    SQLEvalGateDecision,
)

SQL_REGRESSION_DASHBOARD_VERSION = "sql_regression_dashboard_v1"


class SQLRegressionDashboardContractError(ValueError):
    """Raised when regression dashboard contract rules, configurations, or schemas are violated."""
    pass


class SQLRegressionDashboardSeverity(str, Enum):
    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"


@dataclass(frozen=True)
class SQLRegressionDashboardMetric:
    name: str
    value: Any  # Union[float, int, str]
    severity: SQLRegressionDashboardSeverity
    description: str

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str) or not self.name.strip():
            raise SQLRegressionDashboardContractError("name must be a non-empty string")
        if not (isinstance(self.value, str) or (isinstance(self.value, (int, float)) and not isinstance(self.value, bool))):
            raise SQLRegressionDashboardContractError("value must be int, float, or string")
        if not isinstance(self.severity, SQLRegressionDashboardSeverity):
            raise SQLRegressionDashboardContractError("severity must be a SQLRegressionDashboardSeverity")
        if not isinstance(self.description, str):
            raise SQLRegressionDashboardContractError("description must be a string")


@dataclass(frozen=True)
class SQLRegressionDashboardFailureBreakdown:
    category: SQLFailureCategory
    count: int
    rate: float

    def __post_init__(self):
        if not isinstance(self.category, SQLFailureCategory):
            raise SQLRegressionDashboardContractError("category must be a SQLFailureCategory")
        if not isinstance(self.count, int) or isinstance(self.count, bool) or self.count < 0:
            raise SQLRegressionDashboardContractError("count must be a non-negative integer")
        if not isinstance(self.rate, (int, float)) or isinstance(self.rate, bool) or not (0.0 <= self.rate <= 1.0):
            raise SQLRegressionDashboardContractError("rate must be a number between 0.0 and 1.0")


@dataclass(frozen=True)
class SQLRegressionDashboardCaseRow:
    case_id: str
    category: SQLFailureCategory
    severity: SQLFailureSeverity
    passed: bool
    evidence: str
    signals: Tuple[SQLFailureSignal, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if not self.case_id or not isinstance(self.case_id, str) or not self.case_id.strip():
            raise SQLRegressionDashboardContractError("case_id cannot be empty")
        if not isinstance(self.category, SQLFailureCategory):
            raise SQLRegressionDashboardContractError("category must be a SQLFailureCategory")
        if not isinstance(self.severity, SQLFailureSeverity):
            raise SQLRegressionDashboardContractError("severity must be a SQLFailureSeverity")
        if not isinstance(self.passed, bool):
            raise SQLRegressionDashboardContractError("passed must be a boolean")
        if not isinstance(self.evidence, str) or not self.evidence.strip():
            raise SQLRegressionDashboardContractError("evidence cannot be empty")
        
        if not isinstance(self.signals, tuple):
            try:
                object.__setattr__(self, "signals", tuple(self.signals))
            except TypeError:
                raise SQLRegressionDashboardContractError("signals must be a tuple")
        for sig in self.signals:
            if not isinstance(sig, SQLFailureSignal):
                raise SQLRegressionDashboardContractError("All signals items must be SQLFailureSignal")


@dataclass(frozen=True)
class SQLRegressionDashboardGateSummary:
    status: SQLEvalGateStatus
    passed: bool
    decision_reason: str
    failed_rule_count: int
    warning_rule_count: int

    def __post_init__(self):
        if not isinstance(self.status, SQLEvalGateStatus):
            raise SQLRegressionDashboardContractError("status must be SQLEvalGateStatus")
        if not isinstance(self.passed, bool):
            raise SQLRegressionDashboardContractError("passed must be a boolean")
        if not self.decision_reason or not isinstance(self.decision_reason, str) or not self.decision_reason.strip():
            raise SQLRegressionDashboardContractError("decision_reason cannot be empty")
        if not isinstance(self.failed_rule_count, int) or isinstance(self.failed_rule_count, bool) or self.failed_rule_count < 0:
            raise SQLRegressionDashboardContractError("failed_rule_count must be a non-negative integer")
        if not isinstance(self.warning_rule_count, int) or isinstance(self.warning_rule_count, bool) or self.warning_rule_count < 0:
            raise SQLRegressionDashboardContractError("warning_rule_count must be a non-negative integer")


@dataclass(frozen=True)
class SQLRegressionDashboardReport:
    version: str
    generated_at: str
    gate_summary: SQLRegressionDashboardGateSummary
    metrics: Tuple[SQLRegressionDashboardMetric, ...]
    failure_breakdown: Tuple[SQLRegressionDashboardFailureBreakdown, ...]
    top_failing_cases: Tuple[SQLRegressionDashboardCaseRow, ...]
    unknown_failure_rate: float
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    warnings: Tuple[str, ...]

    def __post_init__(self):
        if self.version != "sql_regression_dashboard_v1":
            raise SQLRegressionDashboardContractError(f"Invalid version: {self.version}")
        if not self.generated_at or not isinstance(self.generated_at, str) or not self.generated_at.strip():
            raise SQLRegressionDashboardContractError("generated_at cannot be empty")
        if not isinstance(self.gate_summary, SQLRegressionDashboardGateSummary):
            raise SQLRegressionDashboardContractError("gate_summary must be SQLRegressionDashboardGateSummary")
        
        if not isinstance(self.metrics, tuple):
            try:
                object.__setattr__(self, "metrics", tuple(self.metrics))
            except TypeError:
                raise SQLRegressionDashboardContractError("metrics must be a tuple")
        for m in self.metrics:
            if not isinstance(m, SQLRegressionDashboardMetric):
                raise SQLRegressionDashboardContractError("All metrics items must be SQLRegressionDashboardMetric")

        if not isinstance(self.failure_breakdown, tuple):
            try:
                object.__setattr__(self, "failure_breakdown", tuple(self.failure_breakdown))
            except TypeError:
                raise SQLRegressionDashboardContractError("failure_breakdown must be a tuple")
        for fb in self.failure_breakdown:
            if not isinstance(fb, SQLRegressionDashboardFailureBreakdown):
                raise SQLRegressionDashboardContractError("All failure_breakdown items must be SQLRegressionDashboardFailureBreakdown")

        if not isinstance(self.top_failing_cases, tuple):
            try:
                object.__setattr__(self, "top_failing_cases", tuple(self.top_failing_cases))
            except TypeError:
                raise SQLRegressionDashboardContractError("top_failing_cases must be a tuple")
        for tf in self.top_failing_cases:
            if not isinstance(tf, SQLRegressionDashboardCaseRow):
                raise SQLRegressionDashboardContractError("All top_failing_cases items must be SQLRegressionDashboardCaseRow")

        if not isinstance(self.unknown_failure_rate, (int, float)) or isinstance(self.unknown_failure_rate, bool) or not (0.0 <= self.unknown_failure_rate <= 1.0):
            raise SQLRegressionDashboardContractError("unknown_failure_rate must be a float between 0.0 and 1.0")

        if not isinstance(self.total_cases, int) or isinstance(self.total_cases, bool) or self.total_cases < 0:
            raise SQLRegressionDashboardContractError("total_cases must be a non-negative integer")
        if not isinstance(self.passed_cases, int) or isinstance(self.passed_cases, bool) or self.passed_cases < 0:
            raise SQLRegressionDashboardContractError("passed_cases must be a non-negative integer")
        if not isinstance(self.failed_cases, int) or isinstance(self.failed_cases, bool) or self.failed_cases < 0:
            raise SQLRegressionDashboardContractError("failed_cases must be a non-negative integer")
        if self.total_cases != self.passed_cases + self.failed_cases:
            raise SQLRegressionDashboardContractError("total_cases must equal passed_cases + failed_cases")
        
        expected_rate = (self.passed_cases / self.total_cases) if self.total_cases > 0 else 0.0
        if abs(self.pass_rate - expected_rate) > 1e-6:
            raise SQLRegressionDashboardContractError(f"pass_rate {self.pass_rate} does not match expected {expected_rate}")

        if not isinstance(self.warnings, tuple):
            try:
                object.__setattr__(self, "warnings", tuple(self.warnings))
            except TypeError:
                raise SQLRegressionDashboardContractError("warnings must be a tuple")
        for w in self.warnings:
            if not isinstance(w, str):
                raise SQLRegressionDashboardContractError("All warnings items must be strings")


@dataclass(frozen=True)
class SQLRegressionDashboardConfig:
    generated_at: str = "1970-01-01T00:00:00Z"
    top_failing_case_limit: int = 10
    include_passed_cases: bool = False

    def __post_init__(self):
        if not self.generated_at or not isinstance(self.generated_at, str) or not self.generated_at.strip():
            raise SQLRegressionDashboardContractError("generated_at cannot be empty")
        if not isinstance(self.top_failing_case_limit, int) or isinstance(self.top_failing_case_limit, bool) or self.top_failing_case_limit < 0:
            raise SQLRegressionDashboardContractError("top_failing_case_limit must be a non-negative integer")
        if not isinstance(self.include_passed_cases, bool):
            raise SQLRegressionDashboardContractError("include_passed_cases must be a boolean")


class SQLRegressionDashboardBuilder:
    @staticmethod
    def build(
        run_result: SQLFailureAnalyticsRunResult,
        gate_decision: SQLEvalGateDecision,
        config: SQLRegressionDashboardConfig = SQLRegressionDashboardConfig(),
    ) -> SQLRegressionDashboardReport:
        if not isinstance(run_result, SQLFailureAnalyticsRunResult):
            raise SQLRegressionDashboardContractError("run_result must be a SQLFailureAnalyticsRunResult")
        if not isinstance(gate_decision, SQLEvalGateDecision):
            raise SQLRegressionDashboardContractError("gate_decision must be a SQLEvalGateDecision")
        if not isinstance(config, SQLRegressionDashboardConfig):
            raise SQLRegressionDashboardContractError("config must be a SQLRegressionDashboardConfig")

        if run_result.total_cases != gate_decision.total_cases:
            raise SQLRegressionDashboardContractError("run_result and gate_decision total_cases mismatch")
        if run_result.passed_cases != gate_decision.passed_cases:
            raise SQLRegressionDashboardContractError("run_result and gate_decision passed_cases mismatch")
        if run_result.failed_cases != gate_decision.failed_cases:
            raise SQLRegressionDashboardContractError("run_result and gate_decision failed_cases mismatch")
        if abs(run_result.pass_rate - gate_decision.pass_rate) > 1e-6:
            raise SQLRegressionDashboardContractError("run_result and gate_decision pass_rate mismatch")

        run_counts = {c.category: c.count for c in run_result.category_counts}
        gate_counts = {c.category: c.count for c in gate_decision.category_counts}
        if run_counts != gate_counts:
            raise SQLRegressionDashboardContractError("run_result and gate_decision category_counts mismatch")

        total_cases = run_result.total_cases
        passed_cases = run_result.passed_cases
        failed_cases = run_result.failed_cases
        pass_rate = run_result.pass_rate

        # 1. Gate summary
        gate_summary = SQLRegressionDashboardGateSummary(
            status=gate_decision.status,
            passed=gate_decision.passed,
            decision_reason=gate_decision.decision_reason,
            failed_rule_count=len(gate_decision.failed_rules),
            warning_rule_count=len(gate_decision.warning_rules),
        )

        # 2. Unknown failure rate
        unknown_count = 0
        for cc in run_result.category_counts:
            if cc.category == SQLFailureCategory.UNKNOWN_FAILURE:
                unknown_count = cc.count
                break
        unknown_failure_rate = (unknown_count / total_cases) if total_cases > 0 else 0.0

        # 3. Failure breakdown
        breakdown_list = []
        for cc in run_result.category_counts:
            if cc.category == SQLFailureCategory.PASSED:
                continue
            if cc.count > 0:
                rate = (cc.count / total_cases) if total_cases > 0 else 0.0
                breakdown_list.append(
                    SQLRegressionDashboardFailureBreakdown(
                        category=cc.category,
                        count=cc.count,
                        rate=rate,
                    )
                )
        # Sort failure_breakdown: sort by count desc, then category.value asc
        breakdown_sorted = tuple(
            sorted(breakdown_list, key=lambda fb: (-fb.count, fb.category.value))
        )

        # 4. Top failing cases
        filtered_cases = []
        for cr in run_result.case_results:
            if not cr.passed or config.include_passed_cases:
                filtered_cases.append(
                    SQLRegressionDashboardCaseRow(
                        case_id=cr.case_id,
                        category=cr.category,
                        severity=cr.severity,
                        passed=cr.passed,
                        evidence=cr.evidence,
                        signals=cr.signals,
                    )
                )

        severity_order = {
            SQLFailureSeverity.CRITICAL: 4,
            SQLFailureSeverity.HIGH: 3,
            SQLFailureSeverity.MEDIUM: 2,
            SQLFailureSeverity.LOW: 1,
            SQLFailureSeverity.INFO: 0,
        }

        def top_failing_sort_key(case_row: SQLRegressionDashboardCaseRow):
            passed_val = 0 if not case_row.passed else 1
            sev_priority = severity_order.get(case_row.severity, 0)
            return (passed_val, -sev_priority, case_row.category.value, case_row.case_id)

        sorted_cases = sorted(filtered_cases, key=top_failing_sort_key)
        top_failing_cases = tuple(sorted_cases[:config.top_failing_case_limit])

        # 5. Metrics
        metrics_list = []

        # 1. total_cases
        metrics_list.append(
            SQLRegressionDashboardMetric(
                name="total_cases",
                value=total_cases,
                severity=SQLRegressionDashboardSeverity.INFO,
                description="Total number of evaluated golden dataset cases."
            )
        )

        # 2. passed_cases
        metrics_list.append(
            SQLRegressionDashboardMetric(
                name="passed_cases",
                value=passed_cases,
                severity=SQLRegressionDashboardSeverity.INFO,
                description="Number of golden cases that successfully passed accuracy checks."
            )
        )

        # 3. failed_cases
        failed_severity = SQLRegressionDashboardSeverity.CRITICAL if failed_cases > 0 else SQLRegressionDashboardSeverity.INFO
        metrics_list.append(
            SQLRegressionDashboardMetric(
                name="failed_cases",
                value=failed_cases,
                severity=failed_severity,
                description="Number of golden cases that failed accuracy checks."
            )
        )

        # 4. pass_rate
        pr_severity = SQLRegressionDashboardSeverity.CRITICAL if gate_decision.status == SQLEvalGateStatus.FAIL else (
            SQLRegressionDashboardSeverity.WARN if gate_decision.status == SQLEvalGateStatus.WARN else SQLRegressionDashboardSeverity.INFO
        )
        metrics_list.append(
            SQLRegressionDashboardMetric(
                name="pass_rate",
                value=pass_rate,
                severity=pr_severity,
                description="Ratio of passed cases to total cases."
            )
        )

        # 5. unknown_failure_rate
        unk_severity = SQLRegressionDashboardSeverity.INFO
        if unknown_failure_rate > 0.05:
            has_failed_unk = any(r.rule_type == SQLEvalGateRuleType.MAX_UNKNOWN_FAILURE_RATE and r.status == SQLEvalGateStatus.FAIL for r in gate_decision.failed_rules)
            has_warn_unk = any(r.rule_type == SQLEvalGateRuleType.MAX_UNKNOWN_FAILURE_RATE and r.status == SQLEvalGateStatus.WARN for r in gate_decision.warning_rules)
            if has_failed_unk:
                unk_severity = SQLRegressionDashboardSeverity.CRITICAL
            elif has_warn_unk:
                unk_severity = SQLRegressionDashboardSeverity.WARN
            else:
                unk_severity = SQLRegressionDashboardSeverity.WARN

        metrics_list.append(
            SQLRegressionDashboardMetric(
                name="unknown_failure_rate",
                value=unknown_failure_rate,
                severity=unk_severity,
                description="Ratio of unknown failure cases to total cases."
            )
        )

        # 6. gate_status
        gate_sev = SQLRegressionDashboardSeverity.CRITICAL if gate_decision.status == SQLEvalGateStatus.FAIL else (
            SQLRegressionDashboardSeverity.WARN if gate_decision.status == SQLEvalGateStatus.WARN else SQLRegressionDashboardSeverity.INFO
        )
        metrics_list.append(
            SQLRegressionDashboardMetric(
                name="gate_status",
                value=gate_decision.status.value,
                severity=gate_sev,
                description="Final merge readiness decision status for the evaluation run."
            )
        )

        metrics = tuple(metrics_list)

        # Warnings: collect messages from warning rules
        warnings = tuple(r.message for r in gate_decision.warning_rules)

        return SQLRegressionDashboardReport(
            version=SQL_REGRESSION_DASHBOARD_VERSION,
            generated_at=config.generated_at,
            gate_summary=gate_summary,
            metrics=metrics,
            failure_breakdown=breakdown_sorted,
            top_failing_cases=top_failing_cases,
            unknown_failure_rate=unknown_failure_rate,
            total_cases=total_cases,
            passed_cases=passed_cases,
            failed_cases=failed_cases,
            pass_rate=pass_rate,
            warnings=warnings,
        )
