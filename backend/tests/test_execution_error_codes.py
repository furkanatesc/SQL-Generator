"""Execution taksonomisi tek registry'de (Sprint 27.2 T4)."""
import sqlite3

import pytest
import sqlglot.errors

from app.errors import ErrorCategory, ErrorCode, category_of
from app.result_shape_validator import validate_result_shape
from app.sql_execution_errors import (
    QueryTimeoutError, RowLimitExceededError, SqlExecutionError,
    classify_execution_error,
)


def test_timeout_error_uses_enum_code():
    assert QueryTimeoutError().code is ErrorCode.QUERY_TIMEOUT


def test_row_limit_error_uses_enum_code():
    assert RowLimitExceededError("çok satır").code is ErrorCode.ROW_LIMIT_EXCEEDED


@pytest.mark.parametrize("msg,expected", [
    ("no such table: users", ErrorCode.MISSING_TABLE),
    ("no such column: foo", ErrorCode.MISSING_COLUMN),
    ("near \"FROM\": syntax error", ErrorCode.SYNTAX_ERROR),
    ("attempt to write a readonly database", ErrorCode.READ_ONLY_VIOLATION),
    ("permission denied for relation users", ErrorCode.PERMISSION_DENIED),
    ("unable to open database file", ErrorCode.DATABASE_NOT_FOUND),
    ("some unmapped operational problem", ErrorCode.EXECUTION_FAILED),
])
def test_sqlite_operational_errors_map_to_enum_codes(msg, expected):
    assert classify_execution_error(sqlite3.OperationalError(msg)).code is expected


def test_sqlglot_parse_error_maps_to_syntax_error():
    exc = sqlglot.errors.ParseError("bozuk")
    assert classify_execution_error(exc).code is ErrorCode.SYNTAX_ERROR


def test_generic_exception_falls_back_to_execution_failed():
    assert classify_execution_error(RuntimeError("bilinmeyen")).code is ErrorCode.EXECUTION_FAILED


def test_execution_error_v1_string_is_dead():
    assert classify_execution_error(RuntimeError("x")).code != "execution_error"


def test_already_structured_error_propagates_unchanged():
    original = SqlExecutionError(code=ErrorCode.QUERY_TIMEOUT, message="m")
    assert classify_execution_error(original) is original


def test_invalid_result_shape_uses_enum_code():
    with pytest.raises(SqlExecutionError) as exc_info:
        validate_result_shape("bir liste değil")
    assert exc_info.value.code is ErrorCode.INVALID_RESULT_SHAPE


def test_all_execution_codes_are_execution_category():
    for exc in (QueryTimeoutError(), RowLimitExceededError("x"),
                classify_execution_error(RuntimeError("y"))):
        assert category_of(exc.code) is ErrorCategory.EXECUTION


def test_shared_codes_are_validation_category_even_from_execution_stage():
    # missing_column execution'da da doğar; DOĞASI validation'dır,
    # yakalandığı STAGE execution'dır (spec §3.3).
    err = classify_execution_error(sqlite3.OperationalError("no such column: x"))
    assert err.code is ErrorCode.MISSING_COLUMN
    assert category_of(err.code) is ErrorCategory.VALIDATION
    assert err.stage == "sql_execution"


def test_execution_error_code_is_json_safe():
    import json
    err = classify_execution_error(RuntimeError("x"))
    assert json.dumps({"code": err.code}) == '{"code": "execution_failed"}'
