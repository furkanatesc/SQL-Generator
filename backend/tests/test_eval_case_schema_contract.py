import json
import os
import re
from pathlib import Path

# Resolve the absolute path of the backend directory
BACKEND_DIR = Path(__file__).resolve().parent.parent
FIXTURE_DIR = BACKEND_DIR / "evals" / "fixtures"


def load_all_eval_cases():
    fixture_files = list(FIXTURE_DIR.glob("*.json"))
    cases = []
    for filepath in fixture_files:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                cases.extend(data)
            elif isinstance(data, dict):
                cases.append(data)
    return fixture_files, cases


# 1. Eval fixture files are discoverable and non-empty
def test_eval_fixture_files_exist_and_are_non_empty():
    fixture_files, cases = load_all_eval_cases()
    assert len(fixture_files) > 0, "No evaluation fixture JSON files discovered!"
    for filepath in fixture_files:
        assert filepath.stat().st_size > 0, f"Fixture file {filepath.name} is empty!"
    assert len(cases) > 0, "No evaluation cases loaded from fixtures!"


# 2. Every eval case has required top-level fields (enforcing non-empty strings/dicts/lists)
def test_eval_cases_have_required_fields():
    _, cases = load_all_eval_cases()
    REQUIRED_FIELDS = {"id", "natural_query", "dialect", "schema", "expected"}
    for case in cases:
        for field in REQUIRED_FIELDS:
            assert field in case, f"Case {case.get('id', 'unknown')} is missing required field: {field}"
            assert case[field] is not None, f"Case {case['id']} has null value for required field: {field}"
        
        # Enforce strongly non-empty fields
        assert isinstance(case["id"], str) and case["id"].strip(), f"Case {case['id']} 'id' must be a non-empty string!"
        assert isinstance(case["natural_query"], str) and case["natural_query"].strip(), f"Case {case['id']} 'natural_query' must be a non-empty string!"
        assert isinstance(case["dialect"], str) and case["dialect"].strip(), f"Case {case['id']} 'dialect' must be a non-empty string!"
        assert isinstance(case["schema"], dict) and case["schema"], f"Case {case['id']} 'schema' must be a non-empty dictionary!"
        assert isinstance(case["expected"], dict) and case["expected"], f"Case {case['id']} 'expected' must be a non-empty dictionary!"


# 3. Eval case IDs are unique and stable-looking
def test_eval_case_ids_are_unique_and_formatted():
    _, cases = load_all_eval_cases()
    ids = []
    for case in cases:
        case_id = case["id"]
        # Enforce unique IDs
        assert case_id not in ids, f"Duplicate evaluation case ID found: {case_id}"
        ids.append(case_id)
        # Enforce snake_case stable format
        assert re.match(r"^[a-z0-9_]+$", case_id), f"Case ID {case_id} has invalid format! Must match ^[a-z0-9_]+$"


# 4. Dialect values are supported
def test_eval_case_dialects_are_supported():
    _, cases = load_all_eval_cases()
    SUPPORTED_DIALECTS = {"postgres", "oracle"}
    for case in cases:
        assert case["dialect"] in SUPPORTED_DIALECTS, f"Case {case['id']} has unsupported dialect: {case['dialect']}"


# 5. Expected block has valid type
def test_eval_case_expected_type_is_known():
    _, cases = load_all_eval_cases()
    EXPECTED_TYPES = {
        "success",
        "guardrail_failure",
        "semantic_failure",
        "parse_failure",
        "llm_failure"
    }
    for case in cases:
        expected = case["expected"]
        assert expected["type"] in EXPECTED_TYPES, f"Case {case['id']} has unknown expected type: {expected['type']}"


# 6. Success cases define SQL expectations
def test_success_eval_cases_define_sql_expectations():
    _, cases = load_all_eval_cases()
    for case in cases:
        expected = case["expected"]
        if expected["type"] == "success":
            # Ensure it defines either sql_contains or expected_sql
            assert "sql_contains" in expected or "expected_sql" in expected, \
                f"Success case {case['id']} must define either 'sql_contains' or 'expected_sql' expectations!"
            
            if "sql_contains" in expected:
                sql_contains = expected["sql_contains"]
                assert isinstance(sql_contains, list), f"Case {case['id']} 'sql_contains' must be a list!"
                assert len(sql_contains) > 0, f"Case {case['id']} 'sql_contains' list is empty!"
                for fragment in sql_contains:
                    assert isinstance(fragment, str) and fragment.strip(), \
                        f"Case {case['id']} contains an invalid/empty SQL fragment expectation!"

            if "expected_sql" in expected:
                expected_sql = expected["expected_sql"]
                assert isinstance(expected_sql, str) and expected_sql.strip(), \
                    f"Case {case['id']} 'expected_sql' must be a non-empty string!"


# 7. Failure cases define error type/stage expectations and match allowlist
def test_failure_eval_cases_define_error_type_and_stage():
    _, cases = load_all_eval_cases()
    EXPECTED_ERROR_TYPES = {
        "llm_api_error",
        "sql_parse_error",
        "syntax_error",
        "semantic_validation",
        "validation_error",
        "missing_table",
        "missing_column",
        "unsupported_dialect",
        "empty_sql",
        "multiple_statements",
        "non_select_statement",
        "unsafe_sql",
    }

    EXPECTED_STAGES = {
        "llm_generation",
        "sql_guardrail",
        "ast_parse",
        "semantic_validation",
    }

    for case in cases:
        expected = case["expected"]
        if expected["type"] != "success":
            # Ensure it defines error_type and stage
            assert "error_type" in expected and isinstance(expected["error_type"], str) and expected["error_type"].strip(), \
                f"Failure case {case['id']} is missing a non-empty 'error_type' in expected block!"
            assert "stage" in expected and isinstance(expected["stage"], str) and expected["stage"].strip(), \
                f"Failure case {case['id']} is missing a non-empty 'stage' in expected block!"
            
            # Enforce allowlist checking
            assert expected["error_type"] in EXPECTED_ERROR_TYPES, \
                f"Failure case {case['id']} 'error_type' '{expected['error_type']}' not in allowlist!"
            assert expected["stage"] in EXPECTED_STAGES, \
                f"Failure case {case['id']} 'stage' '{expected['stage']}' not in allowlist!"
            
            # Guardrail failure must explicitly enforce empty public SQL
            if expected["type"] == "guardrail_failure":
                assert expected.get("public_generated_sql") == "", \
                    f"Guardrail failure case {case['id']} must define 'public_generated_sql' as an empty string!"


# 8. Eval cases do not contain secrets
def test_eval_cases_do_not_contain_secret_like_values():
    _, cases = load_all_eval_cases()
    SECRET_PATTERNS = [
        "sk-",
        "nvapi-",
        "api_key=",
        "password=",
        "token=",
        "secret=",
    ]
    for case in cases:
        serialized = json.dumps(case, default=str).lower()
        for pattern in SECRET_PATTERNS:
            assert pattern not in serialized, \
                f"Case {case['id']} contains a secret-like pattern: '{pattern}'"


# 9. Schema structure is fully validated
def test_eval_case_schema_structure_is_valid():
    _, cases = load_all_eval_cases()
    for case in cases:
        schema = case["schema"]
        assert isinstance(schema.get("tables"), dict) and schema["tables"], \
            f"Case {case['id']} schema must contain a non-empty 'tables' dictionary!"
        
        for table_name, table_meta in schema["tables"].items():
            assert isinstance(table_name, str) and table_name.strip(), \
                f"Case {case['id']} has table name that is not a valid string!"
            assert isinstance(table_meta, dict), \
                f"Case {case['id']} table '{table_name}' meta must be a dictionary!"
            assert isinstance(table_meta.get("columns"), list) and table_meta["columns"], \
                f"Case {case['id']} table '{table_name}' must contain a non-empty 'columns' list!"
            
            for col in table_meta["columns"]:
                assert isinstance(col, dict), \
                    f"Case {case['id']} table '{table_name}' column meta must be a dictionary!"
                assert isinstance(col.get("name"), str) and col["name"].strip(), \
                    f"Case {case['id']} table '{table_name}' contains a column without a valid non-empty 'name'!"
