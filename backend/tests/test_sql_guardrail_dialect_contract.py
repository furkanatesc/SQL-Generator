from app.sql_guardrail import SQLGuardrailValidator


def test_sql_guardrail_accepts_supported_postgres_dialect():
    errors = SQLGuardrailValidator.validate(
        "SELECT * FROM customers",
        dialect="postgres",
    )

    assert errors == []


def test_sql_guardrail_accepts_supported_oracle_dialect():
    errors = SQLGuardrailValidator.validate(
        "SELECT * FROM customers",
        dialect="oracle",
    )

    assert errors == []


def test_sql_guardrail_rejects_unsupported_dialect_with_contract_error():
    errors = SQLGuardrailValidator.validate(
        "SELECT * FROM customers",
        dialect="snowflake",
    )

    assert len(errors) == 1
    assert errors[0]["type"] == "unsupported_dialect"
    assert errors[0]["stage"] == "sql_guardrail"
    assert "Unsupported SQL dialect" in errors[0]["message"]


def test_sql_guardrail_default_dialect_is_postgres_contract():
    errors = SQLGuardrailValidator.validate("SELECT * FROM customers")

    assert errors == []
