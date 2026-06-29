"""Sprint 26.11 — gate aggregator over the security eval run + coverage.

Mirrors the shape of SQLEvalGateDecision. Case mismatch => FAIL (deterministic
golden suite, no pass-rate tolerance). Coverage gap => WARN by default
(configurable to FAIL). status = worst rule outcome; passed = status != FAIL.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple

from app.evaluation.security_policy_eval import (
    SECURITY_POLICY_EVAL_CONTRACT_VERSION, SecurityEvalRunResult,
)
from app.evaluation.security_policy_eval_coverage import CoverageReport


class SecurityEvalGateStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


_RANK = {SecurityEvalGateStatus.PASS: 0, SecurityEvalGateStatus.WARN: 1,
         SecurityEvalGateStatus.FAIL: 2}


@dataclass(frozen=True)
class SecurityEvalGateConfig:
    case_mismatch_status: SecurityEvalGateStatus = SecurityEvalGateStatus.FAIL
    coverage_gap_status: SecurityEvalGateStatus = SecurityEvalGateStatus.WARN
    fail_on_empty: bool = True


@dataclass(frozen=True)
class SecurityEvalGateDecision:
    version: str
    status: SecurityEvalGateStatus
    passed: bool
    summary: str
    rules_evaluated: Tuple[str, ...]
    failed_rules: Tuple[str, ...]
    warning_rules: Tuple[str, ...]
    decision_reason: str


class SecurityEvalGateAggregator:
    def aggregate(
        self,
        run_result: SecurityEvalRunResult,
        coverage_report: CoverageReport,
        config: SecurityEvalGateConfig = SecurityEvalGateConfig(),
    ) -> SecurityEvalGateDecision:
        rules_evaluated = ["EMPTY_DATASET", "CASE_MISMATCH", "COVERAGE_GAP"]
        failed, warned = [], []
        statuses = [SecurityEvalGateStatus.PASS]
        reasons = []

        def _apply(rule: str, status: SecurityEvalGateStatus) -> None:
            statuses.append(status)
            if status == SecurityEvalGateStatus.FAIL:
                failed.append(rule)
            elif status == SecurityEvalGateStatus.WARN:
                warned.append(rule)

        if run_result.total == 0 and config.fail_on_empty:
            _apply("EMPTY_DATASET", SecurityEvalGateStatus.FAIL)
            reasons.append("dataset is empty")

        if run_result.failed > 0:
            _apply("CASE_MISMATCH", config.case_mismatch_status)
            reasons.append(f"{run_result.failed} case(s) mismatched")

        if coverage_report.gaps:
            _apply("COVERAGE_GAP", config.coverage_gap_status)
            reasons.append(f"{len(coverage_report.gaps)} reachable symbol(s) uncovered")

        status = max(statuses, key=lambda s: _RANK[s])
        passed = status != SecurityEvalGateStatus.FAIL
        summary = (f"{run_result.passed}/{run_result.total} cases passed; "
                   f"{len(coverage_report.gaps)} coverage gap(s)")
        decision_reason = "; ".join(reasons) if reasons else "all rules passed"
        return SecurityEvalGateDecision(
            version=SECURITY_POLICY_EVAL_CONTRACT_VERSION, status=status, passed=passed,
            summary=summary, rules_evaluated=tuple(rules_evaluated),
            failed_rules=tuple(failed), warning_rules=tuple(warned),
            decision_reason=decision_reason)
