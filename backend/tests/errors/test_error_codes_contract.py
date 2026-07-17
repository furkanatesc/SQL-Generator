"""ErrorCode/ErrorCategory sözleşme testleri (Sprint 27.2 T1)."""
import json
from enum import StrEnum

from app.errors import ErrorCategory, ErrorCode


def test_error_code_is_a_strenum():
    # (str, Enum) DEĞİL: f-string'in "ErrorCode.X" değil "x" üretmesi şart.
    assert issubclass(ErrorCode, StrEnum)
    assert issubclass(ErrorCategory, StrEnum)


def test_error_code_formats_as_its_value():
    assert f"{ErrorCode.MISSING_COLUMN}" == "missing_column"
    assert str(ErrorCode.MISSING_COLUMN) == "missing_column"


def test_error_code_equals_plain_string():
    assert ErrorCode.MISSING_COLUMN == "missing_column"
    assert ErrorCode.MISSING_COLUMN in {"missing_column"}


def test_error_code_is_json_serializable_as_its_value():
    assert json.dumps({"type": ErrorCode.MISSING_COLUMN}) == '{"type": "missing_column"}'


def test_error_code_values_are_unique():
    values = [c.value for c in ErrorCode]
    assert len(values) == len(set(values))


def test_error_code_values_are_snake_case_without_stage_prefix():
    for code in ErrorCode:
        assert "." not in code.value, f"{code.name} kod değerinde stage öneki var"
        assert code.value == code.value.lower()
        assert code.value.replace("_", "").isalnum()


def test_error_code_has_exactly_the_agreed_members():
    # Spec §4.2 — 26 kod. Bu liste bilinçli olarak elle yazıldı: enum'a kaza
    # ile üye eklenmesi/silinmesi bu testi kırmalı.
    assert {c.value for c in ErrorCode} == {
        "input_error", "excel_parse_error",
        "schema_pruning_failed", "schema_pruning_crashed",
        "schema_context_selection_crashed",
        "llm_api_error", "sql_generation_exhausted",
        "empty_sql", "sql_parse_error", "syntax_error",
        "missing_table", "missing_column", "semantic_validation_failed",
        "unsupported_dialect",
        "multiple_statements", "non_select_statement",
        "unsafe_dangerous_function", "unsafe_dml_keyword",
        "unsafe_sandbox_rejected",
        "query_timeout", "row_limit_exceeded", "read_only_violation",
        "permission_denied", "database_not_found", "invalid_result_shape",
        "execution_failed",
    }


def test_dead_v1_strings_are_not_error_codes():
    # Spec §4.2 "ölen string'ler" — kırıcı geçişin ispatı.
    dead = {
        "unsafe_sql", "semantic_validation", "validation_error",
        "schema_pruning_error", "schema_pruning_exception",
        "schema_context_selection_exception", "sql_generation_failed",
        "execution_error",
    }
    assert dead & {c.value for c in ErrorCode} == set()


def test_error_category_has_exactly_the_agreed_members():
    assert {c.value for c in ErrorCategory} == {
        "input", "retrieval", "generation", "validation",
        "security", "execution", "internal",
    }
