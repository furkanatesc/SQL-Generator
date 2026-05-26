import json
import pytest
from evals.eval_runner import run_eval_cases


class FakePipeline:
    def __init__(self, result: dict):
        self.result = result

    def run_pipeline(self, **kwargs):
        return self.result


@pytest.fixture
def sample_cases():
    return [
        {
            "id": "case_b",
            "natural_query": "q2",
            "dialect": "postgres",
            "schema": {},
            "expected": {"type": "success", "sql_contains": ["SELECT", "orders"]}
        },
        {
            "id": "case_a",
            "natural_query": "q1",
            "dialect": "postgres",
            "schema": {},
            "expected": {"type": "success", "sql_contains": ["SELECT", "users"]}
        }
    ]


@pytest.fixture
def pipeline_results():
    return {
        "case_a": {"success": True, "generated_sql": "SELECT id FROM users"},
        "case_b": {"success": True, "generated_sql": "SELECT id FROM customers"}  # Fails orders fragment check
    }


# 1. Report has stable top-level schema (exact dict checks)
def test_eval_runner_report_has_stable_top_level_schema(sample_cases, pipeline_results):
    def factory(case):
        return FakePipeline(pipeline_results[case["id"]])

    result = run_eval_cases(sample_cases, pipeline_factory=factory)
    
    # Assert exact top-level keys
    expected_keys = {"total", "passed", "failed", "pass_rate", "results", "failed_cases"}
    assert set(result.keys()) == expected_keys, f"Report contains unexpected keys: {result.keys()}"
    
    # Assert exact types
    assert isinstance(result["total"], int)
    assert isinstance(result["passed"], int)
    assert isinstance(result["failed"], int)
    assert isinstance(result["pass_rate"], float)
    assert isinstance(result["results"], list)
    assert isinstance(result["failed_cases"], list)


# 2. Report includes exact pass_rate float calculations
def test_eval_runner_report_includes_pass_rate(sample_cases, pipeline_results):
    def factory(case):
        return FakePipeline(pipeline_results[case["id"]])

    result = run_eval_cases(sample_cases, pipeline_factory=factory)
    assert result["pass_rate"] == 0.5


# 3. Pass rate is exactly zero for empty case lists
def test_eval_runner_report_pass_rate_is_zero_for_empty_case_list():
    result = run_eval_cases([], pipeline_factory=lambda c: FakePipeline({}))
    expected_empty_report = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "pass_rate": 0.0,
        "results": [],
        "failed_cases": []
    }
    assert result == expected_empty_report


# 4. Results are ordered consistently by case ID
def test_eval_runner_report_results_are_ordered_by_case_id(sample_cases, pipeline_results):
    def factory(case):
        return FakePipeline(pipeline_results[case["id"]])

    result = run_eval_cases(sample_cases, pipeline_factory=factory)
    # Even though sample_cases was case_b then case_a, results must be case_a then case_b
    assert [r["id"] for r in result["results"]] == ["case_a", "case_b"]


# 5. failed_cases contains only failed cases
def test_eval_runner_report_failed_cases_contains_only_failures(sample_cases, pipeline_results):
    def factory(case):
        return FakePipeline(pipeline_results[case["id"]])

    result = run_eval_cases(sample_cases, pipeline_factory=factory)
    
    # Assert only case_b is in failed_cases
    assert len(result["failed_cases"]) == 1
    assert result["failed_cases"][0]["id"] == "case_b"


# 6. failed_cases are ordered deterministically by case ID
def test_eval_runner_report_failed_cases_are_ordered_by_case_id():
    cases = [
        {"id": "case_z", "natural_query": "q", "dialect": "postgres", "schema": {}, "expected": {"type": "success", "sql_contains": ["X"]}},
        {"id": "case_x", "natural_query": "q", "dialect": "postgres", "schema": {}, "expected": {"type": "success", "sql_contains": ["X"]}}
    ]
    # Both fail
    result = run_eval_cases(cases, pipeline_factory=lambda c: FakePipeline({"success": True, "generated_sql": "SELECT 1"}))
    assert [f["id"] for f in result["failed_cases"]] == ["case_x", "case_z"]


# 7. failed_case entries are minimal and machine-readable
def test_eval_runner_report_failed_case_entries_are_minimal_and_machine_readable(sample_cases, pipeline_results):
    def factory(case):
        return FakePipeline(pipeline_results[case["id"]])

    result = run_eval_cases(sample_cases, pipeline_factory=factory)
    
    failed_entry = result["failed_cases"][0]
    expected_failed_schema = {
        "id": "case_b",
        "expected_type": "success",
        "reason": "Missing SQL fragment: orders"
    }
    assert failed_entry == expected_failed_schema


# 8. Report is fully JSON-serializable
def test_eval_runner_report_is_json_serializable(sample_cases, pipeline_results):
    def factory(case):
        return FakePipeline(pipeline_results[case["id"]])

    result = run_eval_cases(sample_cases, pipeline_factory=factory)
    
    # json.dumps must complete without error
    serialized = json.dumps(result, sort_keys=True)
    parsed = json.loads(serialized)
    assert parsed == result


# 9. Report is 100% deterministic across repeated runs
def test_eval_runner_report_is_deterministic_across_repeated_runs(sample_cases, pipeline_results):
    def factory(case):
        return FakePipeline(pipeline_results[case["id"]])

    first = run_eval_cases(sample_cases, pipeline_factory=factory)
    second = run_eval_cases(sample_cases, pipeline_factory=factory)
    assert first == second


# 10. Report excludes any nondeterministic metadata (timestamps, latency, hostname, etc.)
def test_eval_runner_report_does_not_include_nondeterministic_metadata(sample_cases, pipeline_results):
    def factory(case):
        return FakePipeline(pipeline_results[case["id"]])

    result = run_eval_cases(sample_cases, pipeline_factory=factory)
    
    # Check for absence of typical non-deterministic fields
    volatile_keywords = {"timestamp", "duration", "latency", "time", "uuid", "hostname", "path", "run_id"}
    serialized = json.dumps(result).lower()
    for keyword in volatile_keywords:
        assert keyword not in serialized, f"Volatile keyword '{keyword}' found inside report!"
