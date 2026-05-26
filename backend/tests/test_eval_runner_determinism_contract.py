import pytest
from evals.eval_runner import run_eval_cases


class FakePipeline:
    def __init__(self, result: dict, run_recorder: dict = None):
        self.result = result
        self.run_recorder = run_recorder

    def run_pipeline(self, *, job_id: str, natural_query: str, dialect: str, max_attempts: int):
        if self.run_recorder is not None:
            self.run_recorder["job_id"] = job_id
            self.run_recorder["natural_query"] = natural_query
            self.run_recorder["dialect"] = dialect
            self.run_recorder["max_attempts"] = max_attempts
        return self.result


# 1. Output is fully deterministic across repeated runs
def test_eval_runner_output_is_deterministic_across_repeated_runs():
    cases = [
        {
            "id": "case_a",
            "natural_query": "list users",
            "dialect": "postgres",
            "schema": {"tables": {}},
            "expected": {
                "type": "success",
                "sql_contains": ["SELECT", "users"]
            }
        },
        {
            "id": "case_b",
            "natural_query": "drop orders table",
            "dialect": "postgres",
            "schema": {"tables": {}},
            "expected": {
                "type": "guardrail_failure",
                "error_type": "non_select_statement",
                "stage": "sql_guardrail",
                "public_generated_sql": ""
            }
        }
    ]

    pipeline_results = {
        "case_a": {
            "success": True,
            "generated_sql": "SELECT id FROM users",
            "attempts": []
        },
        "case_b": {
            "success": False,
            "generated_sql": "",
            "attempts": [
                {
                    "validation_errors": [
                        {"type": "non_select_statement", "stage": "sql_guardrail"}
                    ]
                }
            ]
        }
    }

    def factory(case):
        return FakePipeline(pipeline_results[case["id"]])

    # Run twice and assert exact dictionary equality
    first = run_eval_cases(cases, pipeline_factory=factory)
    second = run_eval_cases(cases, pipeline_factory=factory)
    assert first == second


# 2. Cases are ordered deterministically by ID
def test_eval_runner_orders_cases_deterministically():
    case_a = {
        "id": "case_a",
        "natural_query": "list users",
        "dialect": "postgres",
        "schema": {"tables": {}},
        "expected": {"type": "success", "sql_contains": ["SELECT"]}
    }
    case_b = {
        "id": "case_b",
        "natural_query": "list orders",
        "dialect": "postgres",
        "schema": {"tables": {}},
        "expected": {"type": "success", "sql_contains": ["SELECT"]}
    }

    pipeline_results = {
        "case_a": {"success": True, "generated_sql": "SELECT * FROM users"},
        "case_b": {"success": True, "generated_sql": "SELECT * FROM orders"}
    }

    def factory(case):
        return FakePipeline(pipeline_results[case["id"]])

    # Shuffled input order
    shuffled_cases = [case_b, case_a]
    result = run_eval_cases(shuffled_cases, pipeline_factory=factory)

    # Output list must still be ordered deterministically: case_a first, then case_b
    assert [r["id"] for r in result["results"]] == ["case_a", "case_b"]


# 3. Returns stable and correct summary counts
def test_eval_runner_returns_stable_summary_counts():
    cases = [
        {
            "id": "case_a",
            "natural_query": "q1",
            "dialect": "postgres",
            "schema": {},
            "expected": {"type": "success", "sql_contains": ["SELECT"]}
        },
        {
            "id": "case_b",
            "natural_query": "q2",
            "dialect": "postgres",
            "schema": {},
            "expected": {"type": "success", "sql_contains": ["SELECT"]}
        },
        {
            "id": "case_c",
            "natural_query": "q3",
            "dialect": "postgres",
            "schema": {},
            "expected": {"type": "success", "sql_contains": ["SELECT"]}
        }
    ]

    pipeline_results = {
        "case_a": {"success": True, "generated_sql": "SELECT * FROM users"},
        "case_b": {"success": True, "generated_sql": "SELECT * FROM orders"},
        # Case C fails due to missing fragment expectation
        "case_c": {"success": True, "generated_sql": "SHOW TABLES"}
    }

    def factory(case):
        return FakePipeline(pipeline_results[case["id"]])

    result = run_eval_cases(cases, pipeline_factory=factory)
    assert result["total"] == 3
    assert result["passed"] == 2
    assert result["failed"] == 1
    assert result["passed"] + result["failed"] == result["total"]


# 4. Success sql_contains matched (positive & negative checks)
def test_eval_runner_evaluates_success_sql_contains_expectations():
    case = {
        "id": "success_test",
        "natural_query": "q1",
        "dialect": "postgres",
        "schema": {},
        "expected": {"type": "success", "sql_contains": ["SELECT", "USERS"]}
    }

    # Positive Check: passes when all fragments are present (case-insensitive)
    res_pos = {"success": True, "generated_sql": "select id from users"}
    result = run_eval_cases([case], pipeline_factory=lambda c: FakePipeline(res_pos))
    assert result["results"][0]["passed"] is True
    assert result["results"][0]["reason"] is None

    # Negative Check 1: fails when pipeline returns success=False
    res_neg_fail = {"success": False, "generated_sql": ""}
    result = run_eval_cases([case], pipeline_factory=lambda c: FakePipeline(res_neg_fail))
    assert result["results"][0]["passed"] is False
    assert "Expected success but pipeline failed" in result["results"][0]["reason"]

    # Negative Check 2: fails when SQL is missing required fragments
    res_neg_missing = {"success": True, "generated_sql": "SELECT id FROM orders"}
    result = run_eval_cases([case], pipeline_factory=lambda c: FakePipeline(res_neg_missing))
    assert result["results"][0]["passed"] is False
    assert "Missing SQL fragment: USERS" in result["results"][0]["reason"]


# 5. Error type and stage matched (positive & negative checks)
def test_eval_runner_evaluates_failure_error_type_and_stage_expectations():
    case = {
        "id": "failure_test",
        "natural_query": "q1",
        "dialect": "postgres",
        "schema": {},
        "expected": {
            "type": "semantic_failure",
            "error_type": "missing_column",
            "stage": "semantic_validation"
        }
    }

    # Positive Check: passes when error type and stage match
    res_pos = {
        "success": False,
        "generated_sql": "SELECT invalid FROM users",
        "attempts": [
            {
                "validation_errors": [
                    {"type": "missing_column", "stage": "semantic_validation"}
                ]
            }
        ]
    }
    result = run_eval_cases([case], pipeline_factory=lambda c: FakePipeline(res_pos))
    assert result["results"][0]["passed"] is True
    assert result["results"][0]["reason"] is None

    # Negative Check 1: fails when pipeline succeeded instead of failing
    res_neg_success = {"success": True, "generated_sql": "SELECT * FROM users"}
    result = run_eval_cases([case], pipeline_factory=lambda c: FakePipeline(res_neg_success))
    assert result["results"][0]["passed"] is False
    assert "Expected failure but pipeline succeeded" in result["results"][0]["reason"]

    # Negative Check 2: fails when error_type mismatches
    res_neg_err = {
        "success": False,
        "generated_sql": "SELECT invalid FROM users",
        "attempts": [
            {
                "validation_errors": [
                    {"type": "missing_table", "stage": "semantic_validation"}
                ]
            }
        ]
    }
    result = run_eval_cases([case], pipeline_factory=lambda c: FakePipeline(res_neg_err))
    assert result["results"][0]["passed"] is False
    assert "Expected error_type=missing_column got missing_table" in result["results"][0]["reason"]

    # Negative Check 3: fails when stage mismatches
    res_neg_stage = {
        "success": False,
        "generated_sql": "SELECT invalid FROM users",
        "attempts": [
            {
                "validation_errors": [
                    {"type": "missing_column", "stage": "sql_guardrail"}
                ]
            }
        ]
    }
    result = run_eval_cases([case], pipeline_factory=lambda c: FakePipeline(res_neg_stage))
    assert result["results"][0]["passed"] is False
    assert "Expected stage=semantic_validation got sql_guardrail" in result["results"][0]["reason"]


# 6. Enforces guardrail empty public generated SQL policy (positive & negative checks)
def test_eval_runner_enforces_guardrail_public_generated_sql_policy():
    case = {
        "id": "guardrail_test",
        "natural_query": "q1",
        "dialect": "postgres",
        "schema": {},
        "expected": {
            "type": "guardrail_failure",
            "error_type": "unsafe_sql",
            "stage": "sql_guardrail",
            "public_generated_sql": ""
        }
    }

    # Positive Check: passes when expected empty public SQL and actual is empty
    res_pos = {
        "success": False,
        "generated_sql": "",
        "attempts": [
            {
                "validation_errors": [
                    {"type": "unsafe_sql", "stage": "sql_guardrail"}
                ]
            }
        ]
    }
    result = run_eval_cases([case], pipeline_factory=lambda c: FakePipeline(res_pos))
    assert result["results"][0]["passed"] is True
    assert result["results"][0]["reason"] is None

    # Negative Check: fails when actual generated SQL leaks unsafe string instead of empty
    res_neg_leak = {
        "success": False,
        "generated_sql": "DROP TABLE users;",
        "attempts": [
            {
                "validation_errors": [
                    {"type": "unsafe_sql", "stage": "sql_guardrail"}
                ]
            }
        ]
    }
    result = run_eval_cases([case], pipeline_factory=lambda c: FakePipeline(res_neg_leak))
    assert result["results"][0]["passed"] is False
    assert "Guardrail public generated_sql policy mismatch" in result["results"][0]["reason"]


# 7. Uses factory injection with zero real LLM/network dependencies
def test_eval_runner_uses_pipeline_factory_injection():
    case = {
        "id": "injection_test",
        "natural_query": "test query",
        "dialect": "oracle",
        "max_attempts": 3,
        "schema": {},
        "expected": {"type": "success", "sql_contains": ["SELECT"]}
    }

    pipeline_result = {"success": True, "generated_sql": "SELECT 1 FROM DUAL"}
    run_recorder = {}

    def factory(c):
        return FakePipeline(pipeline_result, run_recorder=run_recorder)

    result = run_eval_cases([case], pipeline_factory=factory)
    assert result["results"][0]["passed"] is True

    # Assert correct parameters were propagated to run_pipeline
    assert run_recorder["job_id"] == "injection_test"
    assert run_recorder["natural_query"] == "test query"
    assert run_recorder["dialect"] == "oracle"
    assert run_recorder["max_attempts"] == 3
