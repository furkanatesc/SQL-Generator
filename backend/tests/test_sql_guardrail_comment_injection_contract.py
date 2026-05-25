from app.sql_guardrail import SQLGuardrailValidator


def test_guardrail_allows_single_select_with_trailing_semicolon():
    errors = SQLGuardrailValidator.validate(
        "SELECT id, name FROM customers;",
        dialect="postgres",
    )

    assert errors == []


def test_guardrail_rejects_two_select_statements():
    errors = SQLGuardrailValidator.validate(
        "SELECT * FROM customers; SELECT * FROM orders;",
        dialect="postgres",
    )

    assert len(errors) == 1
    assert errors[0]["type"] == "multiple_statements"
    assert errors[0]["stage"] == "sql_guardrail"


def test_guardrail_rejects_select_then_drop_statement():
    errors = SQLGuardrailValidator.validate(
        "SELECT * FROM customers; DROP TABLE customers;",
        dialect="postgres",
    )

    assert len(errors) == 1
    assert errors[0]["type"] == "multiple_statements"
    assert errors[0]["stage"] == "sql_guardrail"


def test_guardrail_rejects_select_then_delete_statement():
    errors = SQLGuardrailValidator.validate(
        "SELECT * FROM customers; DELETE FROM customers WHERE id = 1;",
        dialect="postgres",
    )

    assert len(errors) == 1
    assert errors[0]["type"] == "multiple_statements"
    assert errors[0]["stage"] == "sql_guardrail"


def test_guardrail_rejects_inline_comment_statement_smuggling():
    errors = SQLGuardrailValidator.validate(
        "SELECT * FROM customers; -- harmless comment\nDROP TABLE customers;",
        dialect="postgres",
    )

    assert len(errors) == 1
    assert errors[0]["type"] == "multiple_statements"
    assert errors[0]["stage"] == "sql_guardrail"


def test_guardrail_rejects_block_comment_statement_smuggling():
    errors = SQLGuardrailValidator.validate(
        "SELECT * FROM customers /* comment */; DROP TABLE customers;",
        dialect="postgres",
    )

    assert len(errors) == 1
    assert errors[0]["type"] == "multiple_statements"
    assert errors[0]["stage"] == "sql_guardrail"


def test_guardrail_allows_single_select_with_inline_comment_inside_statement():
    errors = SQLGuardrailValidator.validate(
        "SELECT id, name FROM customers -- filter active customers\nWHERE active = true;",
        dialect="postgres",
    )

    assert errors == []


def test_guardrail_allows_single_select_with_block_comment_inside_statement():
    errors = SQLGuardrailValidator.validate(
        "SELECT id, name FROM customers /* active customer query */ WHERE active = true;",
        dialect="postgres",
    )

    assert errors == []


def test_guardrail_rejects_only_inline_comment_as_empty_sql():
    errors = SQLGuardrailValidator.validate(
        "-- just a comment",
        dialect="postgres",
    )

    assert len(errors) == 1
    assert errors[0]["type"] in {"empty_sql", "sql_parse_error"}
    assert errors[0]["stage"] == "sql_guardrail"


def test_guardrail_rejects_only_block_comment_as_empty_sql():
    errors = SQLGuardrailValidator.validate(
        "/* just a comment */",
        dialect="postgres",
    )

    assert len(errors) == 1
    assert errors[0]["type"] in {"empty_sql", "sql_parse_error"}
    assert errors[0]["stage"] == "sql_guardrail"


def test_guardrail_rejects_leading_comment_then_delete():
    errors = SQLGuardrailValidator.validate(
        "/* leading comment */ DELETE FROM customers WHERE id = 1;",
        dialect="postgres",
    )

    assert len(errors) == 1
    assert errors[0]["type"] in {"non_select_statement", "unsafe_sql"}
    assert errors[0]["stage"] == "sql_guardrail"


def test_guardrail_rejects_comment_wrapped_drop_statement():
    errors = SQLGuardrailValidator.validate(
        "/* before */ DROP TABLE customers; /* after */",
        dialect="postgres",
    )

    assert len(errors) == 1
    assert errors[0]["type"] in {"non_select_statement", "unsafe_sql", "multiple_statements"}
    assert errors[0]["stage"] == "sql_guardrail"


def test_guardrail_rejects_multi_statement_smuggling_with_oracle_dialect():
    errors = SQLGuardrailValidator.validate(
        "SELECT * FROM customers; DROP TABLE customers;",
        dialect="oracle",
    )

    assert len(errors) == 1
    assert errors[0]["type"] == "multiple_statements"
    assert errors[0]["stage"] == "sql_guardrail"
