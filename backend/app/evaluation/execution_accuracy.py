import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.sql_sandbox import ReadOnlySqlSandbox
from app.evaluation.golden_dataset_contract import (
    SQLGoldenDatasetCase,
    SQLResultComparePolicy,
)


class SQLExecutionAccuracyContractError(ValueError):
    """Raised when execution harness contract constraints or arguments are violated."""
    pass


@dataclass(frozen=True)
class SQLExecutionAccuracyConfig:
    fixtures_dir: str
    timeout_seconds: float = 2.0
    max_rows: int = 1000

    def __post_init__(self):
        if not self.fixtures_dir or not self.fixtures_dir.strip():
            raise SQLExecutionAccuracyContractError("fixtures_dir cannot be empty in config")
        if self.timeout_seconds <= 0:
            raise SQLExecutionAccuracyContractError("timeout_seconds must be greater than 0")
        if self.max_rows <= 0:
            raise SQLExecutionAccuracyContractError("max_rows must be greater than 0")


@dataclass(frozen=True)
class SQLExecutionAccuracyCaseResult:
    case_id: str
    dialect: str
    fixture_ref: str
    predicted_sql: str
    predicted_sql_sha256: str
    gold_sql_sha256: str
    passed: bool
    comparison_policy: str
    expected_row_count: Optional[int]
    actual_row_count: Optional[int]
    normalized_expected_result: Any
    normalized_actual_result: Any
    execution_error: Optional[str]
    duration_ms: float
    warnings: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SQLExecutionAccuracyRunResult:
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    case_results: Tuple[SQLExecutionAccuracyCaseResult, ...]
    duration_ms: float


def canonicalize_value(val: Any) -> Any:
    """Canonicalize a single query result value."""
    if val is None:
        return None
    if isinstance(val, str):
        return val
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val
    return str(val)


def is_numeric(val: Any) -> bool:
    """Check if value is numeric (int or float, excluding bool)."""
    return isinstance(val, (int, float)) and not isinstance(val, bool)


def compare_numeric(val1: Any, val2: Any, tolerance_policy: Optional[Dict[str, Any]]) -> bool:
    """Compare two numeric values within configured epsilon tolerance."""
    policy = tolerance_policy or {}
    epsilon = policy.get("epsilon", 1e-6)
    relative = policy.get("relative", False)
    
    if relative:
        denominator = max(abs(val1), abs(val2))
        if denominator == 0:
            return True
        return abs(val1 - val2) / denominator <= epsilon
    else:
        return abs(val1 - val2) <= epsilon


def compare_rows_exact(row1: Dict[str, Any], row2: Dict[str, Any]) -> bool:
    """Key-order independent exact value comparison between two rows."""
    if set(row1.keys()) != set(row2.keys()):
        return False
    for k in row1:
        if row1[k] != row2[k]:
            return False
    return True


def compare_rows_with_tolerance(row1: Dict[str, Any], row2: Dict[str, Any], tolerance_policy: Optional[Dict[str, Any]]) -> bool:
    """Compare two rows with numeric tolerance where applicable."""
    if set(row1.keys()) != set(row2.keys()):
        return False
    for k in row1:
        v1 = row1[k]
        v2 = row2[k]
        if is_numeric(v1) and is_numeric(v2):
            if not compare_numeric(v1, v2, tolerance_policy):
                return False
        else:
            if v1 != v2:
                return False
    return True


def match_rows_with_tolerance(
    actual_rows: List[Dict[str, Any]],
    expected_rows: List[Dict[str, Any]],
    tolerance_policy: Optional[Dict[str, Any]]
) -> bool:
    """Bipartite greedy matching of rows using numeric tolerance."""
    if len(actual_rows) != len(expected_rows):
        return False
    matched_indices = set()
    for exp_row in expected_rows:
        found_match = False
        for idx, act_row in enumerate(actual_rows):
            if idx in matched_indices:
                continue
            if compare_rows_with_tolerance(act_row, exp_row, tolerance_policy):
                matched_indices.add(idx)
                found_match = True
                break
        if not found_match:
            return False
    return True


def compare_subset(
    actual_rows: List[Dict[str, Any]],
    expected_rows: List[Dict[str, Any]],
    order_sensitive: bool,
    tolerance_policy: Optional[Dict[str, Any]]
) -> bool:
    """Check if expected_rows is a subset of actual_rows (either as a subsequence or unordered)."""
    if not expected_rows:
        return True
        
    if order_sensitive:
        act_idx = 0
        for exp_row in expected_rows:
            matched = False
            while act_idx < len(actual_rows):
                if compare_rows_with_tolerance(actual_rows[act_idx], exp_row, tolerance_policy):
                    matched = True
                    act_idx += 1
                    break
                act_idx += 1
            if not matched:
                return False
        return True
    else:
        matched_indices = set()
        for exp_row in expected_rows:
            found = False
            for idx, act_row in enumerate(actual_rows):
                if idx in matched_indices:
                    continue
                if compare_rows_with_tolerance(act_row, exp_row, tolerance_policy):
                    matched_indices.add(idx)
                    found = True
                    break
            if not found:
                return False
        return True


def row_to_json_stable(row: Dict[str, Any]) -> str:
    """Serialize row dictionary to sorted-key JSON string for stable comparisons."""
    return json.dumps(row, sort_keys=True, default=str, separators=(",", ":"))


class SQLExecutionResultComparator:
    @classmethod
    def canonicalize_result(cls, rows: Any) -> List[Dict[str, Any]]:
        """Convert any query result list of dicts to key-sorted canonical form."""
        if rows is None:
            return []
            
        # If input is a single dict, wrap in a list
        if isinstance(rows, dict):
            rows = [rows]
            
        if not isinstance(rows, (list, tuple)):
            raise SQLExecutionAccuracyContractError("Execution result must be a list of dictionaries")
            
        canonicalized = []
        for r in rows:
            if not isinstance(r, dict):
                raise SQLExecutionAccuracyContractError("Each row in execution result must be a dictionary")
            sorted_row = {}
            for k in sorted(r.keys()):
                sorted_row[k] = canonicalize_value(r[k])
            canonicalized.append(sorted_row)
            
        return canonicalized

    @classmethod
    def compare(
        cls,
        actual: List[Dict[str, Any]],
        expected: List[Dict[str, Any]],
        policy: SQLResultComparePolicy | str,
        order_sensitive: bool,
        tolerance_policy: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Compares actual and expected results under specified policy."""
        if isinstance(policy, str):
            try:
                policy = SQLResultComparePolicy(policy)
            except ValueError:
                raise SQLExecutionAccuracyContractError(f"Invalid result comparison policy: {policy}")

        # Input results should be canonicalized before calling this
        act_canonical = cls.canonicalize_result(actual)
        exp_canonical = cls.canonicalize_result(expected)

        if policy == SQLResultComparePolicy.EXACT_ORDERED:
            if len(act_canonical) != len(exp_canonical):
                return False
            for act_row, exp_row in zip(act_canonical, exp_canonical):
                if not compare_rows_exact(act_row, exp_row):
                    return False
            return True

        elif policy == SQLResultComparePolicy.EXACT_UNORDERED:
            if len(act_canonical) != len(exp_canonical):
                return False
            # Stable json sorting handles mixed-value types gracefully
            act_jsons = sorted(row_to_json_stable(r) for r in act_canonical)
            exp_jsons = sorted(row_to_json_stable(r) for r in exp_canonical)
            return act_jsons == exp_jsons

        elif policy == SQLResultComparePolicy.NUMERIC_TOLERANCE:
            if len(act_canonical) != len(exp_canonical):
                return False
            if order_sensitive:
                for act_row, exp_row in zip(act_canonical, exp_canonical):
                    if not compare_rows_with_tolerance(act_row, exp_row, tolerance_policy):
                        return False
                return True
            else:
                return match_rows_with_tolerance(act_canonical, exp_canonical, tolerance_policy)

        elif policy == SQLResultComparePolicy.SUBSET_ALLOWED:
            return compare_subset(act_canonical, exp_canonical, order_sensitive, tolerance_policy)

        elif policy == SQLResultComparePolicy.CUSTOM:
            # Fall back to order-sensitive exact check if order_sensitive is True, else exact_unordered
            if order_sensitive:
                if len(act_canonical) != len(exp_canonical):
                    return False
                for act_row, exp_row in zip(act_canonical, exp_canonical):
                    if not compare_rows_exact(act_row, exp_row):
                        return False
                return True
            else:
                act_jsons = sorted(row_to_json_stable(r) for r in act_canonical)
                exp_jsons = sorted(row_to_json_stable(r) for r in exp_canonical)
                return act_jsons == exp_jsons

        return False


def calculate_sha256(sql: Optional[str]) -> str:
    """Return SHA256 hex digest of a string, or empty string if None/empty."""
    if not sql:
        return ""
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


class SQLExecutionAccuracyHarness:
    def __init__(self, config: SQLExecutionAccuracyConfig):
        self.config = config

    def _resolve_db_path(self, fixture_ref: str) -> str:
        """Find and validate local sqlite database file under configured fixtures directory."""
        if not fixture_ref or not fixture_ref.strip():
            raise SQLExecutionAccuracyContractError("fixture_ref cannot be empty")

        if os.path.isabs(fixture_ref):
            raise SQLExecutionAccuracyContractError("fixture_ref must be relative to fixtures_dir")

        fixtures_root = os.path.abspath(self.config.fixtures_dir)

        candidate_names = (f"{fixture_ref}.db", fixture_ref)
        for name in candidate_names:
            candidate = os.path.abspath(os.path.join(fixtures_root, name))
            if not candidate.startswith(fixtures_root + os.sep):
                raise SQLExecutionAccuracyContractError("fixture_ref cannot escape fixtures_dir")
            if os.path.exists(candidate):
                return candidate

        raise SQLExecutionAccuracyContractError(f"Fixture database not found: '{fixture_ref}'")

    def run_case(self, case: SQLGoldenDatasetCase, predicted_sql: str) -> SQLExecutionAccuracyCaseResult:
        """Executes a single predicted SQL query against DB fixture and compares result."""
        # 1. Validate empty predicted SQL
        if not predicted_sql or not predicted_sql.strip():
            raise SQLExecutionAccuracyContractError("predicted_sql cannot be empty")

        start_time = time.monotonic()
        warnings_list = []
        db_path = None
        db_resolve_error = None

        # 2. Resolve database path
        try:
            db_path = self._resolve_db_path(case.fixture_ref)
        except Exception as e:
            db_resolve_error = str(e)

        actual_row_count = None
        normalized_actual_result = None
        predicted_error = None
        duration_ms = 0.0

        # Dialect mismatch warning
        if case.dialect != "sqlite":
            warnings_list.append(
                f"Harness executing SQL of dialect '{case.dialect}' in a SQLite sandbox fixture."
            )

        # 3. Execute Predicted SQL
        if db_resolve_error:
            predicted_error = db_resolve_error
        else:
            try:
                sandbox = ReadOnlySqlSandbox(
                    db_path,
                    timeout_seconds=self.config.timeout_seconds,
                    max_rows=self.config.max_rows,
                )
                actual_result = sandbox.execute(predicted_sql)
                actual_row_count = len(actual_result)
                normalized_actual_result = SQLExecutionResultComparator.canonicalize_result(actual_result)
            except Exception as e:
                predicted_error = str(e)
                actual_row_count = 0
                normalized_actual_result = None

        duration_ms = (time.monotonic() - start_time) * 1000.0

        # 4. Resolve expected result (either from case.expected_result or gold_sql)
        normalized_expected_result = None
        expected_row_count = None
        gold_error = None

        if case.expected_result is not None:
            try:
                normalized_expected_result = SQLExecutionResultComparator.canonicalize_result(case.expected_result)
                expected_row_count = len(normalized_expected_result)
            except Exception as e:
                gold_error = f"Expected result canonicalization failed: {e}"
                expected_row_count = 0
        elif case.gold_sql:
            if db_resolve_error:
                gold_error = db_resolve_error
            else:
                try:
                    gold_sandbox = ReadOnlySqlSandbox(
                        db_path,
                        timeout_seconds=self.config.timeout_seconds,
                        max_rows=self.config.max_rows,
                    )
                    gold_result = gold_sandbox.execute(case.gold_sql)
                    normalized_expected_result = SQLExecutionResultComparator.canonicalize_result(gold_result)
                    expected_row_count = len(normalized_expected_result)
                except Exception as e:
                    gold_error = f"Gold SQL execution failed: {e}"
                    expected_row_count = 0
        else:
            gold_error = "No expected_result or gold_sql available for case verification"
            expected_row_count = 0

        # 5. Evaluate pass/fail logic
        passed = False
        execution_error = None

        if predicted_error:
            passed = False
            execution_error = predicted_error
        elif gold_error:
            passed = False
            execution_error = gold_error
        else:
            # Custom policy fallback warning
            if case.result_compare_policy == SQLResultComparePolicy.CUSTOM:
                warnings_list.append(
                    "Custom compare policy mapped to default (exact_ordered or exact_unordered)."
                )

            try:
                passed = SQLExecutionResultComparator.compare(
                    actual=normalized_actual_result,
                    expected=normalized_expected_result,
                    policy=case.result_compare_policy,
                    order_sensitive=case.order_sensitive,
                    tolerance_policy=case.tolerance_policy,
                )
                execution_error = None
            except Exception as e:
                passed = False
                execution_error = f"Comparison execution failed: {e}"

        return SQLExecutionAccuracyCaseResult(
            case_id=case.case_id,
            dialect=case.dialect,
            fixture_ref=case.fixture_ref,
            predicted_sql=predicted_sql,
            predicted_sql_sha256=calculate_sha256(predicted_sql),
            gold_sql_sha256=calculate_sha256(case.gold_sql),
            passed=passed,
            comparison_policy=str(case.result_compare_policy),
            expected_row_count=expected_row_count,
            actual_row_count=actual_row_count,
            normalized_expected_result=normalized_expected_result,
            normalized_actual_result=normalized_actual_result,
            execution_error=execution_error,
            duration_ms=duration_ms,
            warnings=tuple(warnings_list),
        )

    def run_harness(self, cases: List[SQLGoldenDatasetCase], predicted_sqls: Dict[str, str]) -> SQLExecutionAccuracyRunResult:
        """Runs the harness on a batch of evaluation cases and aggregates results."""
        start_time = time.monotonic()
        results = []
        passed_count = 0
        
        for case in cases:
            # Get corresponding predicted SQL
            pred_sql = predicted_sqls.get(case.case_id, "")
            
            # If predicted_sql is missing, record failed result directly rather than crashing batch
            if not pred_sql or not pred_sql.strip():
                res = SQLExecutionAccuracyCaseResult(
                    case_id=case.case_id,
                    dialect=case.dialect,
                    fixture_ref=case.fixture_ref,
                    predicted_sql="",
                    predicted_sql_sha256="",
                    gold_sql_sha256=calculate_sha256(case.gold_sql),
                    passed=False,
                    comparison_policy=str(case.result_compare_policy),
                    expected_row_count=0,
                    actual_row_count=0,
                    normalized_expected_result=None,
                    normalized_actual_result=None,
                    execution_error="predicted_sql cannot be empty",
                    duration_ms=0.0,
                    warnings=(),
                )
            else:
                try:
                    res = self.run_case(case, pred_sql)
                except Exception as e:
                    # In case of any validation crash, capture it deterministically
                    res = SQLExecutionAccuracyCaseResult(
                        case_id=case.case_id,
                        dialect=case.dialect,
                        fixture_ref=case.fixture_ref,
                        predicted_sql=pred_sql,
                        predicted_sql_sha256=calculate_sha256(pred_sql),
                        gold_sql_sha256=calculate_sha256(case.gold_sql),
                        passed=False,
                        comparison_policy=str(case.result_compare_policy),
                        expected_row_count=0,
                        actual_row_count=0,
                        normalized_expected_result=None,
                        normalized_actual_result=None,
                        execution_error=f"Harness internal execution error: {e}",
                        duration_ms=0.0,
                        warnings=(),
                    )
            
            results.append(res)
            if res.passed:
                passed_count += 1

        # Sort the results deterministically by case_id
        sorted_results = tuple(sorted(results, key=lambda r: r.case_id))

        total = len(cases)
        failed = total - passed_count
        pass_rate = (passed_count / total) if total > 0 else 0.0
        duration_ms = (time.monotonic() - start_time) * 1000.0
        
        return SQLExecutionAccuracyRunResult(
            total_cases=total,
            passed_cases=passed_count,
            failed_cases=failed,
            pass_rate=pass_rate,
            case_results=sorted_results,
            duration_ms=duration_ms,
        )
