"""Guardrail komut/fonksiyon sözleşmesi.

Not (Sprint 27.2): reddedilen komut/fonksiyon girdileri (CALL, EXECUTE, COPY,
VACUUM, ANALYZE ...) statement-tipi / parse katmanında elenir — DML taraması ve
tehlikeli-fonksiyon taraması ÇALIŞMADAN önce. Bu yüzden bu testler yalnız
{"non_select_statement", "sql_parse_error"} bekler; hiçbir `unsafe_*` kodu
üretilmez. `unsafe_sql` bölünürken (T2) bu setlerden kod ikame edilmedi, çıkarıldı
— eksik kod değil, o dallar bu girdilerle ulaşılamaz olduğundan.
"""
from app.sql_guardrail import SQLGuardrailValidator


def test_guardrail_allows_safe_aggregate_functions():
    errors = SQLGuardrailValidator.validate(
        "SELECT COUNT(*), MAX(total), MIN(total) FROM orders;",
        dialect="postgres",
    )

    assert errors == []


def test_guardrail_allows_safe_scalar_functions():
    errors = SQLGuardrailValidator.validate(
        "SELECT LOWER(name), COALESCE(email, 'unknown') FROM customers;",
        dialect="postgres",
    )

    assert errors == []


def test_guardrail_allows_safe_date_functions():
    errors = SQLGuardrailValidator.validate(
        "SELECT DATE_TRUNC('day', created_at) AS day FROM orders;",
        dialect="postgres",
    )

    assert errors == []


def test_guardrail_rejects_call_statement():
    errors = SQLGuardrailValidator.validate(
        "CALL refresh_customer_stats();",
        dialect="postgres",
    )

    assert len(errors) == 1
    assert errors[0]["type"] in {"non_select_statement", "sql_parse_error"}
    assert errors[0]["stage"] == "sql_guardrail"


def test_guardrail_rejects_execute_statement():
    errors = SQLGuardrailValidator.validate(
        "EXECUTE refresh_customer_stats;",
        dialect="postgres",
    )

    assert len(errors) == 1
    assert errors[0]["type"] in {"non_select_statement", "sql_parse_error"}
    assert errors[0]["stage"] == "sql_guardrail"


def test_guardrail_rejects_copy_statement():
    errors = SQLGuardrailValidator.validate(
        "COPY customers TO STDOUT;",
        dialect="postgres",
    )

    assert len(errors) == 1
    assert errors[0]["type"] in {"non_select_statement", "sql_parse_error"}
    assert errors[0]["stage"] == "sql_guardrail"


def test_guardrail_rejects_vacuum_statement():
    errors = SQLGuardrailValidator.validate(
        "VACUUM customers;",
        dialect="postgres",
    )

    assert len(errors) == 1
    assert errors[0]["type"] in {"non_select_statement", "sql_parse_error"}
    assert errors[0]["stage"] == "sql_guardrail"


def test_guardrail_rejects_analyze_statement():
    errors = SQLGuardrailValidator.validate(
        "ANALYZE customers;",
        dialect="postgres",
    )

    assert len(errors) == 1
    assert errors[0]["type"] in {"non_select_statement", "sql_parse_error"}
    assert errors[0]["stage"] == "sql_guardrail"


def test_guardrail_rejects_pg_sleep_function():
    errors = SQLGuardrailValidator.validate(
        "SELECT pg_sleep(10);",
        dialect="postgres",
    )

    assert len(errors) == 1
    assert errors[0]["type"] == "unsafe_dangerous_function"
    assert errors[0]["stage"] == "sql_guardrail"
    assert errors[0]["details"]["reason"] == "dangerous_function_detected"
    assert errors[0]["details"]["function"] == "PG_SLEEP"


def test_guardrail_rejects_pg_read_file_function():
    errors = SQLGuardrailValidator.validate(
        "SELECT pg_read_file('/etc/passwd');",
        dialect="postgres",
    )

    assert len(errors) == 1
    assert errors[0]["type"] == "unsafe_dangerous_function"
    assert errors[0]["stage"] == "sql_guardrail"
    assert errors[0]["details"]["reason"] == "dangerous_function_detected"
    assert errors[0]["details"]["function"] == "PG_READ_FILE"


def test_guardrail_rejects_dblink_function():
    errors = SQLGuardrailValidator.validate(
        "SELECT dblink('dbname=prod', 'SELECT 1');",
        dialect="postgres",
    )

    assert len(errors) == 1
    assert errors[0]["type"] == "unsafe_dangerous_function"
    assert errors[0]["stage"] == "sql_guardrail"
    assert errors[0]["details"]["reason"] == "dangerous_function_detected"
    assert errors[0]["details"]["function"] == "DBLINK"


def test_guardrail_rejects_dangerous_function_inside_cte():
    sql = """
    WITH delayed AS (
        SELECT pg_sleep(10)
    )
    SELECT * FROM delayed;
    """

    errors = SQLGuardrailValidator.validate(sql, dialect="postgres")

    assert len(errors) == 1
    assert errors[0]["type"] == "unsafe_dangerous_function"
    assert errors[0]["details"]["reason"] == "dangerous_function_detected"
    assert errors[0]["details"]["function"] == "PG_SLEEP"


def test_guardrail_rejects_oracle_execute_immediate():
    errors = SQLGuardrailValidator.validate(
        "EXECUTE IMMEDIATE 'DROP TABLE customers'",
        dialect="oracle",
    )

    assert len(errors) == 1
    assert errors[0]["type"] in {"non_select_statement", "sql_parse_error"}
    assert errors[0]["stage"] == "sql_guardrail"
