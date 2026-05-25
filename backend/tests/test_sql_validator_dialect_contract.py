from app.sql_validator import SQLValidator

CUSTOMERS_SCHEMA = {
    "tables": {
        "customers": {
            "columns": [
                {"name": "id", "type": "integer"},
                {"name": "name", "type": "text"},
            ]
        }
    }
}


def test_sql_validator_accepts_supported_postgres_dialect():
    valid, error = SQLValidator.validate(
        "SELECT id FROM customers",
        CUSTOMERS_SCHEMA,
        dialect="postgres",
    )

    assert valid is True
    assert error == ""


def test_sql_validator_accepts_supported_oracle_dialect():
    valid, error = SQLValidator.validate(
        "SELECT id FROM customers",
        CUSTOMERS_SCHEMA,
        dialect="oracle",
    )

    assert valid is True
    assert error == ""


def test_sql_validator_rejects_unsupported_dialect_with_contract_error():
    valid, error = SQLValidator.validate(
        "SELECT id FROM customers",
        CUSTOMERS_SCHEMA,
        dialect="snowflake",
    )

    assert valid is False
    assert error.startswith("DIALECT ERROR:")
    assert "Unsupported SQL dialect" in error


def test_sql_validator_default_dialect_is_postgres_contract():
    valid, error = SQLValidator.validate(
        "SELECT id FROM customers",
        CUSTOMERS_SCHEMA,
    )

    assert valid is True
    assert error == ""
