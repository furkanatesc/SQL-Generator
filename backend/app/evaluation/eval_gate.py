from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Tuple, Optional

from app.evaluation.failure_analytics import (
    SQLFailureCategory,
    SQLFailureCategoryCount,
    SQLFailureAnalyticsRunResult,
)

SQL_EVAL_GATE_VERSION = "sql_eval_gate_v1"


class SQLEvalGateContractError(ValueError):
    """Raised when evaluation gate rules, configurations, or input schemas are violated."""
    pass


def _validate_rate(val: Any, name: str):
    """Helper to validate that a rate/probability is a float/int within [0.0, 1.0]."""
    if not isinstance(val, (int, float)) or isinstance(val, bool):
        raise SQLEvalGateContractError(f"{name} must be a number")
    if not (0.0 <= val <= 1.0):
        raise SQLEvalGateContractError(f"{name} must be between 0.0 and 1.0")


class SQLEvalGateStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class SQLEvalGateSeverity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SQLEvalGateRuleType(str, Enum):
    MIN_PASS_RATE = "min_pass_rate"
    MAX_FAILURE_COUNT = "max_failure_count"
    MAX_FAILURE_RATE = "max_failure_rate"
    BLOCK_FAILURE_CATEGORY = "block_failure_category"
    MAX_UNKNOWN_FAILURE_RATE = "max_unknown_failure_rate"
    REQUIRE_P0_PASS = "require_p0_pass"


@dataclass(frozen=True)
class SQLEvalGateRule:
    rule_type: SQLEvalGateRuleType
    severity: SQLEvalGateSeverity

    def __post_init__(self):
        if not isinstance(self.rule_type, SQLEvalGateRuleType):
            raise SQLEvalGateContractError("rule_type must be a SQLEvalGateRuleType")
        if not isinstance(self.severity, SQLEvalGateSeverity):
            raise SQLEvalGateContractError("severity must be a SQLEvalGateSeverity")


@dataclass(frozen=True)
class SQLEvalGateRuleResult:
    rule_type: SQLEvalGateRuleType
    status: SQLEvalGateStatus
    severity: SQLEvalGateSeverity
    message: str

    def __post_init__(self):
        if not isinstance(self.rule_type, SQLEvalGateRuleType):
            raise SQLEvalGateContractError("rule_type must be a SQLEvalGateRuleType")
        if not isinstance(self.status, SQLEvalGateStatus):
            raise SQLEvalGateContractError("status must be a SQLEvalGateStatus")
        if not isinstance(self.severity, SQLEvalGateSeverity):
            raise SQLEvalGateContractError("severity must be a SQLEvalGateSeverity")
        if not isinstance(self.message, str) or not self.message.strip():
            raise SQLEvalGateContractError("message must be a non-empty string")


@dataclass(frozen=True)
class SQLEvalGateRunSummary:
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float

    def __post_init__(self):
        if not isinstance(self.total_cases, int) or isinstance(self.total_cases, bool):
            raise SQLEvalGateContractError("total_cases must be an integer")
        if not isinstance(self.passed_cases, int) or isinstance(self.passed_cases, bool):
            raise SQLEvalGateContractError("passed_cases must be an integer")
        if not isinstance(self.failed_cases, int) or isinstance(self.failed_cases, bool):
            raise SQLEvalGateContractError("failed_cases must be an integer")
        if self.total_cases < 0 or self.passed_cases < 0 or self.failed_cases < 0:
            raise SQLEvalGateContractError("Case counts cannot be negative")
        _validate_rate(self.pass_rate, "pass_rate")

        if self.total_cases != self.passed_cases + self.failed_cases:
            raise SQLEvalGateContractError("total_cases must equal passed_cases + failed_cases")
        
        expected_rate = (self.passed_cases / self.total_cases) if self.total_cases > 0 else 0.0
        if abs(self.pass_rate - expected_rate) > 1e-6:
            raise SQLEvalGateContractError(f"pass_rate {self.pass_rate} does not match expected {expected_rate}")


@dataclass(frozen=True)
class SQLEvalGateConfig:
    """Configuration for the evaluation gate.
    
    Note: empty_dataset_status is only used when fail_on_empty_dataset is False.
    """
    min_pass_rate: float = 0.95
    max_unknown_failure_rate: float = 0.05
    blocked_categories: Tuple[SQLFailureCategory, ...] = (
        SQLFailureCategory.UNSAFE_SQL_REJECTED,
        SQLFailureCategory.FIXTURE_NOT_FOUND,
    )
    warn_categories: Tuple[SQLFailureCategory, ...] = (
        SQLFailureCategory.UNKNOWN_FAILURE,
    )
    fail_on_empty_dataset: bool = True
    unknown_failure_rate_status: SQLEvalGateStatus = SQLEvalGateStatus.WARN
    empty_dataset_status: SQLEvalGateStatus = SQLEvalGateStatus.PASS
    max_failure_count: Optional[int] = None
    max_failure_rate: Optional[float] = None

    def __post_init__(self):
        _validate_rate(self.min_pass_rate, "min_pass_rate")
        _validate_rate(self.max_unknown_failure_rate, "max_unknown_failure_rate")
        
        if not isinstance(self.blocked_categories, tuple):
            raise SQLEvalGateContractError("blocked_categories must be a tuple")
        for cat in self.blocked_categories:
            if not isinstance(cat, SQLFailureCategory):
                raise SQLEvalGateContractError("All blocked_categories items must be SQLFailureCategory")

        if not isinstance(self.warn_categories, tuple):
            raise SQLEvalGateContractError("warn_categories must be a tuple")
        for cat in self.warn_categories:
            if not isinstance(cat, SQLFailureCategory):
                raise SQLEvalGateContractError("All warn_categories items must be SQLFailureCategory")

        if not isinstance(self.unknown_failure_rate_status, SQLEvalGateStatus):
            try:
                object.__setattr__(self, "unknown_failure_rate_status", SQLEvalGateStatus(self.unknown_failure_rate_status))
            except ValueError:
                raise SQLEvalGateContractError("unknown_failure_rate_status must be a SQLEvalGateStatus")
                
        if self.unknown_failure_rate_status not in (SQLEvalGateStatus.WARN, SQLEvalGateStatus.FAIL):
            raise SQLEvalGateContractError("unknown_failure_rate_status must be WARN or FAIL")

        if not isinstance(self.empty_dataset_status, SQLEvalGateStatus):
            try:
                object.__setattr__(self, "empty_dataset_status", SQLEvalGateStatus(self.empty_dataset_status))
            except ValueError:
                raise SQLEvalGateContractError("empty_dataset_status must be a SQLEvalGateStatus")

        if self.max_failure_count is not None:
            if not isinstance(self.max_failure_count, int) or isinstance(self.max_failure_count, bool):
                raise SQLEvalGateContractError("max_failure_count must be an integer")
            if self.max_failure_count < 0:
                raise SQLEvalGateContractError("max_failure_count cannot be negative")

        if self.max_failure_rate is not None:
            _validate_rate(self.max_failure_rate, "max_failure_rate")


@dataclass(frozen=True)
class SQLEvalGateDecision:
    version: str
    status: SQLEvalGateStatus
    passed: bool
    summary: SQLEvalGateRunSummary
    rules_evaluated: Tuple[SQLEvalGateRuleResult, ...]
    failed_rules: Tuple[SQLEvalGateRuleResult, ...]
    warning_rules: Tuple[SQLEvalGateRuleResult, ...]
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    category_counts: Tuple[SQLFailureCategoryCount, ...]
    decision_reason: str

    def __post_init__(self):
        if self.version != "sql_eval_gate_v1":
            raise SQLEvalGateContractError(f"Invalid version: {self.version}")
        if not isinstance(self.status, SQLEvalGateStatus):
            raise SQLEvalGateContractError("status must be SQLEvalGateStatus")
        if not isinstance(self.passed, bool):
            raise SQLEvalGateContractError("passed must be a boolean")
        if not isinstance(self.summary, SQLEvalGateRunSummary):
            raise SQLEvalGateContractError("summary must be SQLEvalGateRunSummary")

        if not isinstance(self.rules_evaluated, tuple):
            try:
                object.__setattr__(self, "rules_evaluated", tuple(self.rules_evaluated))
            except TypeError:
                raise SQLEvalGateContractError("rules_evaluated must be a tuple")
        for rule in self.rules_evaluated:
            if not isinstance(rule, SQLEvalGateRuleResult):
                raise SQLEvalGateContractError("All rules_evaluated items must be SQLEvalGateRuleResult")

        if not isinstance(self.failed_rules, tuple):
            try:
                object.__setattr__(self, "failed_rules", tuple(self.failed_rules))
            except TypeError:
                raise SQLEvalGateContractError("failed_rules must be a tuple")
        for rule in self.failed_rules:
            if not isinstance(rule, SQLEvalGateRuleResult):
                raise SQLEvalGateContractError("All failed_rules items must be SQLEvalGateRuleResult")

        if not isinstance(self.warning_rules, tuple):
            try:
                object.__setattr__(self, "warning_rules", tuple(self.warning_rules))
            except TypeError:
                raise SQLEvalGateContractError("warning_rules must be a tuple")
        for rule in self.warning_rules:
            if not isinstance(rule, SQLEvalGateRuleResult):
                raise SQLEvalGateContractError("All warning_rules items must be SQLEvalGateRuleResult")

        if not isinstance(self.total_cases, int) or isinstance(self.total_cases, bool):
            raise SQLEvalGateContractError("total_cases must be an integer")
        if not isinstance(self.passed_cases, int) or isinstance(self.passed_cases, bool):
            raise SQLEvalGateContractError("passed_cases must be an integer")
        if not isinstance(self.failed_cases, int) or isinstance(self.failed_cases, bool):
            raise SQLEvalGateContractError("failed_cases must be an integer")
        if self.total_cases < 0 or self.passed_cases < 0 or self.failed_cases < 0:
            raise SQLEvalGateContractError("Case counts cannot be negative")
        _validate_rate(self.pass_rate, "pass_rate")

        if not isinstance(self.category_counts, tuple):
            try:
                object.__setattr__(self, "category_counts", tuple(self.category_counts))
            except TypeError:
                raise SQLEvalGateContractError("category_counts must be a tuple")
        for cc in self.category_counts:
            if not isinstance(cc, SQLFailureCategoryCount):
                raise SQLEvalGateContractError("All category_counts items must be SQLFailureCategoryCount")

        if not isinstance(self.decision_reason, str) or not self.decision_reason.strip():
            raise SQLEvalGateContractError("decision_reason must be a non-empty string")


class SQLEvalGateAggregator:
    @staticmethod
    def aggregate(
        run_result: SQLFailureAnalyticsRunResult,
        config: SQLEvalGateConfig = SQLEvalGateConfig(),
    ) -> SQLEvalGateDecision:
        if not isinstance(run_result, SQLFailureAnalyticsRunResult):
            raise SQLEvalGateContractError(
                "Input must be an instance of SQLFailureAnalyticsRunResult"
            )
        if not isinstance(config, SQLEvalGateConfig):
            raise SQLEvalGateContractError("Config must be an instance of SQLEvalGateConfig")

        total_cases = run_result.total_cases
        passed_cases = run_result.passed_cases
        failed_cases = run_result.failed_cases
        pass_rate = run_result.pass_rate

        category_counts_map = {cc.category: cc.count for cc in run_result.category_counts}

        rules_evaluated = []

        # 1. MIN_PASS_RATE
        if total_cases == 0:
            empty_status = (
                SQLEvalGateStatus.FAIL
                if config.fail_on_empty_dataset
                else config.empty_dataset_status
            )
            pass_rate_status = empty_status
            pass_rate_msg = f"Dataset is empty; configured empty dataset status is {empty_status.value}."
            severity = (
                SQLEvalGateSeverity.CRITICAL
                if empty_status == SQLEvalGateStatus.FAIL
                else (SQLEvalGateSeverity.MEDIUM if empty_status == SQLEvalGateStatus.WARN else SQLEvalGateSeverity.INFO)
            )
        else:
            min_pass_rate_ok = pass_rate >= config.min_pass_rate
            pass_rate_status = SQLEvalGateStatus.PASS if min_pass_rate_ok else SQLEvalGateStatus.FAIL
            pass_rate_msg = (
                f"Pass rate {pass_rate:.2%} meets or exceeds minimum threshold of {config.min_pass_rate:.2%}."
                if min_pass_rate_ok
                else f"Pass rate {pass_rate:.2%} is below minimum threshold of {config.min_pass_rate:.2%}."
            )
            severity = SQLEvalGateSeverity.CRITICAL

        rules_evaluated.append(
            SQLEvalGateRuleResult(
                rule_type=SQLEvalGateRuleType.MIN_PASS_RATE,
                status=pass_rate_status,
                severity=severity,
                message=pass_rate_msg,
            )
        )

        # 2. MAX_FAILURE_COUNT
        if config.max_failure_count is not None and failed_cases > config.max_failure_count:
            fc_status = SQLEvalGateStatus.FAIL
            fc_msg = f"Failure count {failed_cases} exceeds maximum limit of {config.max_failure_count}."
        else:
            limit_str = str(config.max_failure_count) if config.max_failure_count is not None else "disabled"
            fc_status = SQLEvalGateStatus.PASS
            fc_msg = f"Failure count {failed_cases} is within limit (limit: {limit_str})."
        rules_evaluated.append(
            SQLEvalGateRuleResult(
                rule_type=SQLEvalGateRuleType.MAX_FAILURE_COUNT,
                status=fc_status,
                severity=SQLEvalGateSeverity.HIGH,
                message=fc_msg,
            )
        )

        # 3. MAX_FAILURE_RATE
        failure_rate = (failed_cases / total_cases) if total_cases > 0 else 0.0
        if config.max_failure_rate is not None and failure_rate > config.max_failure_rate:
            fr_status = SQLEvalGateStatus.FAIL
            fr_msg = f"Failure rate {failure_rate:.2%} exceeds maximum limit of {config.max_failure_rate:.2%}."
        else:
            limit_str = f"{config.max_failure_rate:.2%}" if config.max_failure_rate is not None else "disabled"
            fr_status = SQLEvalGateStatus.PASS
            fr_msg = f"Failure rate {failure_rate:.2%} is within limit (limit: {limit_str})."
        rules_evaluated.append(
            SQLEvalGateRuleResult(
                rule_type=SQLEvalGateRuleType.MAX_FAILURE_RATE,
                status=fr_status,
                severity=SQLEvalGateSeverity.HIGH,
                message=fr_msg,
            )
        )

        # 4. BLOCK_FAILURE_CATEGORY
        found_blocked = [cat for cat in config.blocked_categories if category_counts_map.get(cat, 0) > 0]
        found_warn = [cat for cat in config.warn_categories if category_counts_map.get(cat, 0) > 0]

        if found_blocked:
            block_status = SQLEvalGateStatus.FAIL
            details = ", ".join(f"{cat.value} ({category_counts_map[cat]} count)" for cat in found_blocked)
            block_msg = f"Blocked failure categories detected: {details}."
        elif found_warn:
            block_status = SQLEvalGateStatus.WARN
            details = ", ".join(f"{cat.value} ({category_counts_map[cat]} count)" for cat in found_warn)
            block_msg = f"Warning failure categories detected: {details}."
        else:
            block_status = SQLEvalGateStatus.PASS
            block_msg = "No blocked or warning failure categories detected."

        rules_evaluated.append(
            SQLEvalGateRuleResult(
                rule_type=SQLEvalGateRuleType.BLOCK_FAILURE_CATEGORY,
                status=block_status,
                severity=SQLEvalGateSeverity.CRITICAL if found_blocked else (SQLEvalGateSeverity.MEDIUM if found_warn else SQLEvalGateSeverity.LOW),
                message=block_msg,
            )
        )

        # 5. MAX_UNKNOWN_FAILURE_RATE
        unknown_count = category_counts_map.get(SQLFailureCategory.UNKNOWN_FAILURE, 0)
        unknown_rate = (unknown_count / total_cases) if total_cases > 0 else 0.0

        if unknown_rate > config.max_unknown_failure_rate:
            unk_status = config.unknown_failure_rate_status
            unk_msg = f"Unknown failure rate {unknown_rate:.2%} exceeds maximum threshold of {config.max_unknown_failure_rate:.2%}."
        else:
            unk_status = SQLEvalGateStatus.PASS
            unk_msg = f"Unknown failure rate {unknown_rate:.2%} is within maximum threshold of {config.max_unknown_failure_rate:.2%}."

        rules_evaluated.append(
            SQLEvalGateRuleResult(
                rule_type=SQLEvalGateRuleType.MAX_UNKNOWN_FAILURE_RATE,
                status=unk_status,
                severity=SQLEvalGateSeverity.HIGH if unk_status == SQLEvalGateStatus.FAIL else SQLEvalGateSeverity.MEDIUM,
                message=unk_msg,
            )
        )

        # 6. REQUIRE_P0_PASS (bypassed in this sprint)
        rules_evaluated.append(
            SQLEvalGateRuleResult(
                rule_type=SQLEvalGateRuleType.REQUIRE_P0_PASS,
                status=SQLEvalGateStatus.PASS,
                severity=SQLEvalGateSeverity.HIGH,
                message="P0 pass requirement is bypassed (no tier metadata on case results in this sprint).",
            )
        )

        # Sort rules_evaluated by SQLEvalGateRuleType enum order
        rule_type_order = list(SQLEvalGateRuleType)
        rules_evaluated_sorted = tuple(
            sorted(rules_evaluated, key=lambda r: rule_type_order.index(r.rule_type))
        )

        # Deterministic status priority decision:
        # Priority order for status:
        # 1. Empty dataset handling
        # 2. Blocked category exists -> FAIL
        # 3. P0 requirement (out of scope/always passes)
        # 4. Pass rate below threshold -> FAIL
        # 5. Unknown failure rate above threshold -> WARN or FAIL config-driven
        # 6. Warn category exists -> WARN
        # 7. Otherwise PASS
        if total_cases == 0:
            status = config.empty_dataset_status if not config.fail_on_empty_dataset else SQLEvalGateStatus.FAIL
            action_str = "failed" if status == SQLEvalGateStatus.FAIL else ("warned" if status == SQLEvalGateStatus.WARN else "passed")
            decision_reason = f"Gate {action_str}: Evaluation run contains no test cases."
        elif found_blocked:
            status = SQLEvalGateStatus.FAIL
            decision_reason = f"Gate failed: Blocked failure categories detected: {', '.join(cat.value for cat in found_blocked)}."
        elif pass_rate < config.min_pass_rate:
            status = SQLEvalGateStatus.FAIL
            decision_reason = f"Gate failed: Pass rate {pass_rate:.2%} is below minimum threshold of {config.min_pass_rate:.2%}."
        elif config.max_failure_count is not None and failed_cases > config.max_failure_count:
            status = SQLEvalGateStatus.FAIL
            decision_reason = f"Gate failed: Failure count {failed_cases} exceeds maximum limit of {config.max_failure_count}."
        elif config.max_failure_rate is not None and failure_rate > config.max_failure_rate:
            status = SQLEvalGateStatus.FAIL
            decision_reason = f"Gate failed: Failure rate {failure_rate:.2%} exceeds maximum limit of {config.max_failure_rate:.2%}."
        elif unknown_rate > config.max_unknown_failure_rate:
            status = config.unknown_failure_rate_status
            action_str = "failed" if status == SQLEvalGateStatus.FAIL else "warned"
            decision_reason = f"Gate {action_str}: Unknown failure rate {unknown_rate:.2%} exceeds maximum threshold of {config.max_unknown_failure_rate:.2%}."
        elif found_warn:
            status = SQLEvalGateStatus.WARN
            decision_reason = f"Gate warned: Warning failure categories detected: {', '.join(cat.value for cat in found_warn)}."
        else:
            status = SQLEvalGateStatus.PASS
            decision_reason = f"Gate passed: All checks passed (pass rate: {pass_rate:.2%})."

        passed = (status != SQLEvalGateStatus.FAIL)

        failed_rules = tuple(r for r in rules_evaluated_sorted if r.status == SQLEvalGateStatus.FAIL)
        warning_rules = tuple(r for r in rules_evaluated_sorted if r.status == SQLEvalGateStatus.WARN)

        summary = SQLEvalGateRunSummary(
            total_cases=total_cases,
            passed_cases=passed_cases,
            failed_cases=failed_cases,
            pass_rate=pass_rate,
        )

        return SQLEvalGateDecision(
            version=SQL_EVAL_GATE_VERSION,
            status=status,
            passed=passed,
            summary=summary,
            rules_evaluated=rules_evaluated_sorted,
            failed_rules=failed_rules,
            warning_rules=warning_rules,
            total_cases=total_cases,
            passed_cases=passed_cases,
            failed_cases=failed_cases,
            pass_rate=pass_rate,
            category_counts=tuple(run_result.category_counts),
            decision_reason=decision_reason,
        )
