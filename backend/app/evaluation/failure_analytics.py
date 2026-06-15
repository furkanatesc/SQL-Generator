import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from app.evaluation.execution_accuracy import (
    SQLExecutionAccuracyCaseResult,
    SQLExecutionAccuracyRunResult,
)

SQL_FAILURE_ANALYTICS_VERSION = "sql_failure_analytics_v1"


class SQLFailureAnalyticsContractError(ValueError):
    """Raised when failure analytics contract rules or argument types are violated."""
    pass


class SQLFailureCategory(str, Enum):
    PASSED = "passed"
    EMPTY_PREDICTED_SQL = "empty_predicted_sql"
    UNSAFE_SQL_REJECTED = "unsafe_sql_rejected"
    SQL_EXECUTION_ERROR = "sql_execution_error"
    FIXTURE_NOT_FOUND = "fixture_not_found"
    EXPECTED_RESULT_INVALID = "expected_result_invalid"
    GOLD_SQL_EXECUTION_ERROR = "gold_sql_execution_error"
    ROW_COUNT_MISMATCH = "row_count_mismatch"
    COLUMN_SHAPE_MISMATCH = "column_shape_mismatch"
    VALUE_MISMATCH = "value_mismatch"
    ORDER_MISMATCH = "order_mismatch"
    NUMERIC_TOLERANCE_MISMATCH = "numeric_tolerance_mismatch"
    DIALECT_MISMATCH_WARNING = "dialect_mismatch_warning"
    UNKNOWN_FAILURE = "unknown_failure"


class SQLFailureSeverity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class SQLFailureSignal:
    name: str
    value: Any
    description: Optional[str] = None


@dataclass(frozen=True)
class SQLFailureAnalysisResult:
    case_id: str
    category: SQLFailureCategory
    severity: SQLFailureSeverity
    passed: bool
    evidence: str
    signals: Tuple[SQLFailureSignal, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SQLFailureAnalyticsRunResult:
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    category_counts: Dict[SQLFailureCategory, int]
    case_results: Tuple[SQLFailureAnalysisResult, ...]
    duration_ms: float


class SQLFailureAnalyzer:
    @classmethod
    def analyze_case(cls, result: SQLExecutionAccuracyCaseResult) -> SQLFailureAnalysisResult:
        """Analyze a single SQLExecutionAccuracyCaseResult and classify failure category and severity."""
        if not isinstance(result, SQLExecutionAccuracyCaseResult):
            raise SQLFailureAnalyticsContractError(
                "Input must be an instance of SQLExecutionAccuracyCaseResult"
            )

        signals = []
        for warning in result.warnings:
            if "dialect" in warning.lower():
                signals.append(
                    SQLFailureSignal(
                        name="dialect_mismatch_warning",
                        value=warning,
                        description="Dialect mismatch warning found during execution"
                    )
                )

        # 1. Passed Case
        if result.passed:
            return SQLFailureAnalysisResult(
                case_id=result.case_id,
                category=SQLFailureCategory.PASSED,
                severity=SQLFailureSeverity.INFO,
                passed=True,
                evidence="Evaluation case passed denotation comparison.",
                signals=tuple(signals),
            )

        # 2. Execution Errors
        if result.execution_error:
            err = result.execution_error
            err_lower = err.lower()

            # Empty predicted sql
            if "predicted_sql cannot be empty" in err_lower:
                return SQLFailureAnalysisResult(
                    case_id=result.case_id,
                    category=SQLFailureCategory.EMPTY_PREDICTED_SQL,
                    severity=SQLFailureSeverity.HIGH,
                    passed=False,
                    evidence=f"Empty predicted SQL query: {err}",
                    signals=tuple(signals),
                )

            # Unsafe SQL rejected
            if (
                "write operation detected" in err_lower
                or "only read-only select statements are allowed" in err_lower
                or "read_only_violation" in err_lower
            ):
                return SQLFailureAnalysisResult(
                    case_id=result.case_id,
                    category=SQLFailureCategory.UNSAFE_SQL_REJECTED,
                    severity=SQLFailureSeverity.CRITICAL,
                    passed=False,
                    evidence=f"Unsafe SQL or write statement rejected: {err}",
                    signals=tuple(signals),
                )

            # Fixture not found
            if (
                "fixture database not found" in err_lower
                or "database_not_found" in err_lower
                or "unable to open database file" in err_lower
            ):
                return SQLFailureAnalysisResult(
                    case_id=result.case_id,
                    category=SQLFailureCategory.FIXTURE_NOT_FOUND,
                    severity=SQLFailureSeverity.CRITICAL,
                    passed=False,
                    evidence=f"Fixture database not found: {err}",
                    signals=tuple(signals),
                )

            # Gold SQL execution error
            if "gold sql execution failed" in err_lower:
                return SQLFailureAnalysisResult(
                    case_id=result.case_id,
                    category=SQLFailureCategory.GOLD_SQL_EXECUTION_ERROR,
                    severity=SQLFailureSeverity.HIGH,
                    passed=False,
                    evidence=f"Gold reference SQL execution failed: {err}",
                    signals=tuple(signals),
                )

            # Expected result invalid
            if "expected result canonicalization failed" in err_lower:
                return SQLFailureAnalysisResult(
                    case_id=result.case_id,
                    category=SQLFailureCategory.EXPECTED_RESULT_INVALID,
                    severity=SQLFailureSeverity.HIGH,
                    passed=False,
                    evidence=f"Expected result was malformed or invalid: {err}",
                    signals=tuple(signals),
                )

            # General SQL execution error
            return SQLFailureAnalysisResult(
                case_id=result.case_id,
                category=SQLFailureCategory.SQL_EXECUTION_ERROR,
                severity=SQLFailureSeverity.MEDIUM,
                passed=False,
                evidence=f"SQL execution error during sandbox run: {err}",
                signals=tuple(signals),
            )

        # 3. Denotation Comparison Mismatches
        exp_count = result.expected_row_count
        act_count = result.actual_row_count

        # Row count mismatch takes priority over column and value mismatches
        if exp_count is not None and act_count is not None and exp_count != act_count:
            return SQLFailureAnalysisResult(
                case_id=result.case_id,
                category=SQLFailureCategory.ROW_COUNT_MISMATCH,
                severity=SQLFailureSeverity.MEDIUM,
                passed=False,
                evidence=f"Row count mismatch: expected {exp_count} rows, got {act_count} rows.",
                signals=tuple(signals),
            )

        act_res = result.normalized_actual_result
        exp_res = result.normalized_expected_result

        # Missing result sets with no execution error is classified as unknown_failure
        if act_res is None or exp_res is None:
            return SQLFailureAnalysisResult(
                case_id=result.case_id,
                category=SQLFailureCategory.UNKNOWN_FAILURE,
                severity=SQLFailureSeverity.MEDIUM,
                passed=False,
                evidence="Unknown evaluation failure: result sets are missing but no execution error was reported.",
                signals=tuple(signals),
            )

        # Column shape mismatch (keys are different)
        if act_res and exp_res:
            act_cols = set(act_res[0].keys())
            exp_cols = set(exp_res[0].keys())
            if act_cols != exp_cols:
                return SQLFailureAnalysisResult(
                    case_id=result.case_id,
                    category=SQLFailureCategory.COLUMN_SHAPE_MISMATCH,
                    severity=SQLFailureSeverity.MEDIUM,
                    passed=False,
                    evidence=f"Column shape mismatch: expected columns {sorted(exp_cols)}, got {sorted(act_cols)}.",
                    signals=tuple(signals),
                )

        # Order mismatch (exact_ordered failed, but exact_unordered passes)
        is_exact_ordered = result.comparison_policy in (
            "exact_ordered",
            "SQLResultComparePolicy.EXACT_ORDERED",
        )
        if is_exact_ordered:
            from app.evaluation.execution_accuracy import SQLExecutionResultComparator
            try:
                # Check if they are identical under EXACT_UNORDERED
                if SQLExecutionResultComparator.compare(act_res, exp_res, "exact_unordered", order_sensitive=False):
                    return SQLFailureAnalysisResult(
                        case_id=result.case_id,
                        category=SQLFailureCategory.ORDER_MISMATCH,
                        severity=SQLFailureSeverity.LOW,
                        passed=False,
                        evidence="Order mismatch: result matches expected rows but row ordering differs.",
                        signals=tuple(signals),
                    )
            except Exception:
                pass

        # Numeric tolerance mismatch
        is_numeric_tolerance = result.comparison_policy in (
            "numeric_tolerance",
            "SQLResultComparePolicy.NUMERIC_TOLERANCE",
        )
        if is_numeric_tolerance:
            return SQLFailureAnalysisResult(
                case_id=result.case_id,
                category=SQLFailureCategory.NUMERIC_TOLERANCE_MISMATCH,
                severity=SQLFailureSeverity.LOW,
                passed=False,
                evidence="Numeric tolerance mismatch: actual values fall outside the tolerance policy epsilon.",
                signals=tuple(signals),
            )

        # Value mismatch fallback
        return SQLFailureAnalysisResult(
            case_id=result.case_id,
            category=SQLFailureCategory.VALUE_MISMATCH,
            severity=SQLFailureSeverity.MEDIUM,
            passed=False,
            evidence="Value mismatch: row and column counts match, but cell values differ.",
            signals=tuple(signals),
        )

    @classmethod
    def analyze_run(cls, run_result: SQLExecutionAccuracyRunResult) -> SQLFailureAnalyticsRunResult:
        """Analyze and classify a complete run result, sorting the list by case_id."""
        if not isinstance(run_result, SQLExecutionAccuracyRunResult):
            raise SQLFailureAnalyticsContractError(
                "Input must be an instance of SQLExecutionAccuracyRunResult"
            )

        start_time = time.monotonic()
        results = [cls.analyze_case(r) for r in run_result.case_results]

        # Sort results deterministically by case_id
        sorted_results = tuple(sorted(results, key=lambda r: r.case_id))

        # Initialize counts
        counts = {cat: 0 for cat in SQLFailureCategory}
        passed_cases = 0
        failed_cases = 0

        for r in sorted_results:
            counts[r.category] += 1
            if r.passed:
                passed_cases += 1
            else:
                failed_cases += 1

        total = len(sorted_results)
        pass_rate = (passed_cases / total) if total > 0 else 0.0
        duration_ms = (time.monotonic() - start_time) * 1000.0

        return SQLFailureAnalyticsRunResult(
            total_cases=total,
            passed_cases=passed_cases,
            failed_cases=failed_cases,
            pass_rate=pass_rate,
            category_counts=counts,
            case_results=sorted_results,
            duration_ms=duration_ms,
        )
