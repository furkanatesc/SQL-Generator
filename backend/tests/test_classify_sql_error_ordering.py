"""classify_sql_error sıra bug'ı (Sprint 27.2 T3).

v1 sırası: column -> table -> parse/syntax. İçinde "column" geçen HER mesaj
missing_column oluyordu; syntax_error pratikte ulaşılamazdı.
v2 sırası: parse/syntax -> column -> table -> fallback.
"""
from app.errors import ErrorCode
from app.sql_pipeline import classify_sql_error


def test_parse_error_mentioning_a_column_is_a_syntax_error_not_missing_column():
    # v1'de bu missing_column dönerdi — bug buydu.
    msg = "SQLGLOT AST Parse Error: Invalid expression near column foo"
    assert classify_sql_error(msg, stage="ast_parse")["type"] is ErrorCode.SYNTAX_ERROR


def test_parse_error_mentioning_a_table_is_a_syntax_error_not_missing_table():
    msg = "SQLGLOT AST Parse Error: unexpected token near table users"
    assert classify_sql_error(msg, stage="ast_parse")["type"] is ErrorCode.SYNTAX_ERROR


def test_missing_column_still_classifies_as_missing_column():
    msg = "Missing column 'foo' in table 'users'"
    assert classify_sql_error(msg, stage="semantic_validation")["type"] is ErrorCode.MISSING_COLUMN


def test_missing_table_classifies_as_missing_table():
    msg = "Missing table 'orders'"
    assert classify_sql_error(msg, stage="semantic_validation")["type"] is ErrorCode.MISSING_TABLE


def test_unrecognized_message_falls_back_to_semantic_validation_failed():
    msg = "Beklenmedik bir sorun"
    result = classify_sql_error(msg, stage="semantic_validation")
    assert result["type"] is ErrorCode.SEMANTIC_VALIDATION_FAILED
    # validation_error öldü:
    assert result["type"] != "validation_error"


def test_stage_and_message_are_passed_through_untouched():
    result = classify_sql_error("Missing column x", stage="semantic_validation")
    assert result["stage"] == "semantic_validation"
    assert result["message"] == "Missing column x"


def test_stage_is_not_a_code():
    # v1'de "semantic_validation" hem stage hem type'tı. Artık yalnız stage.
    result = classify_sql_error("Missing column x", stage="semantic_validation")
    assert result["type"] != "semantic_validation"
