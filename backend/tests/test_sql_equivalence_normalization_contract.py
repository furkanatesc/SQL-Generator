import pytest
from evals.sql_normalizer import normalize_sql, sql_equivalent
from evals.eval_runner import run_eval_cases


class FakePipeline:
    def __init__(self, result: dict):
        self.result = result

    def run_pipeline(self, **kwargs):
        return self.result


# 1. Normalization ignores keyword casing
def test_normalize_sql_ignores_keyword_casing():
    assert normalize_sql("select id from users") == normalize_sql("SELECT id FROM users")
    assert normalize_sql("SeLeCt id FrOm users") == normalize_sql("SELECT id FROM users")


# 2. Normalization ignores whitespace and newlines
def test_normalize_sql_ignores_whitespace_and_newlines():
    assert normalize_sql("SELECT\n  id\nFROM users") == normalize_sql("SELECT id FROM users")
    assert normalize_sql("SELECT    id    FROM    users") == normalize_sql("SELECT id FROM users")


# 3. Normalization ignores trailing semicolon
def test_normalize_sql_ignores_trailing_semicolon():
    assert normalize_sql("SELECT id FROM users;") == normalize_sql("SELECT id FROM users")
    assert normalize_sql("SELECT id FROM users;;;") == normalize_sql("SELECT id FROM users")


# 4. SQL equivalent returns true for formatting-only differences
def test_sql_equivalent_accepts_formatting_only_differences():
    assert sql_equivalent(
        "select id from users",
        "SELECT\n  id\nFROM users;",
        dialect="postgres",
    )


# 5. SQL equivalent returns false for different selected columns (negative test)
def test_sql_equivalent_rejects_different_selected_columns():
    assert not sql_equivalent(
        "SELECT id FROM users",
        "SELECT name FROM users",
        dialect="postgres",
    )


# 6. SQL equivalent returns false for different source tables (negative test)
def test_sql_equivalent_rejects_different_tables():
    assert not sql_equivalent(
        "SELECT id FROM users",
        "SELECT id FROM orders",
        dialect="postgres",
    )


# 7. Normalizer is deterministic across repeated calls
def test_normalize_sql_is_deterministic_across_repeated_calls():
    sql = "select id\nfrom users;"
    outputs = {normalize_sql(sql) for _ in range(5)}
    assert len(outputs) == 1
    assert list(outputs)[0] == normalize_sql(sql)


# 8. Parse failure fallback is deterministic
def test_normalize_sql_parse_failure_fallback_is_deterministic():
    sql = "SELECT   *   FROM"
    # AST parsing fails on incomplete syntax, falling back to deterministic whitespace reduction
    assert normalize_sql(sql) == "SELECT * FROM"
    assert normalize_sql(sql) == normalize_sql("SELECT * FROM")


# 9. Eval runner uses expected_sql equivalence for success cases
def test_eval_runner_uses_expected_sql_equivalence_for_success_cases():
    case = {
        "id": "basic_equivalence",
        "natural_query": "list users",
        "dialect": "postgres",
        "expected": {
            "type": "success",
            "expected_sql": "SELECT id FROM users"
        }
    }

    # Pipeline output has different casing and formatting, but semantically equivalent
    pipeline_result = {
        "success": True,
        "generated_sql": "select\n  id\nfrom users;"
    }

    result = run_eval_cases([case], pipeline_factory=lambda c: FakePipeline(pipeline_result))
    assert result["results"][0]["passed"] is True
    assert result["results"][0]["reason"] is None


# 10. Eval runner fails when expected_sql is not equivalent (negative test)
def test_eval_runner_fails_when_expected_sql_is_not_equivalent():
    case = {
        "id": "basic_equivalence_fail",
        "natural_query": "list users",
        "dialect": "postgres",
        "expected": {
            "type": "success",
            "expected_sql": "SELECT id FROM users"
        }
    }

    # Pipeline output returns name column instead of id
    pipeline_result = {
        "success": True,
        "generated_sql": "SELECT name FROM users"
    }

    result = run_eval_cases([case], pipeline_factory=lambda c: FakePipeline(pipeline_result))
    assert result["results"][0]["passed"] is False
    assert "SQL equivalence mismatch" in result["results"][0]["reason"]


# 11. Eval runner keeps sql_contains fallback for backward compatibility
def test_eval_runner_keeps_sql_contains_fallback():
    case = {
        "id": "contains_fallback",
        "natural_query": "list users",
        "dialect": "postgres",
        "expected": {
            "type": "success",
            "sql_contains": ["SELECT", "users"]
        }
    }

    # Case has no expected_sql but defines sql_contains. Normal runner evaluation applies.
    pipeline_result = {
        "success": True,
        "generated_sql": "SELECT id FROM users"
    }

    result = run_eval_cases([case], pipeline_factory=lambda c: FakePipeline(pipeline_result))
    assert result["results"][0]["passed"] is True
    assert result["results"][0]["reason"] is None
