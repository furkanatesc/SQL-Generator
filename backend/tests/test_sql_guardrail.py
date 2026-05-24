import pytest
from app.sql_guardrail import SQLGuardrailValidator

def test_allows_simple_select():
    sql = "SELECT id, name FROM users;"
    errors = SQLGuardrailValidator.validate(sql)
    assert errors == []

def test_allows_with_select_cte():
    sql = """
    WITH monthly_sales AS (
        SELECT id, amount FROM orders WHERE amount > 100
    )
    SELECT * FROM monthly_sales;
    """
    errors = SQLGuardrailValidator.validate(sql)
    assert errors == []

def test_rejects_delete():
    sql = "DELETE FROM users WHERE id = 1;"
    errors = SQLGuardrailValidator.validate(sql)
    assert len(errors) == 1
    assert errors[0]["type"] == "non_select_statement"
    assert errors[0]["stage"] == "sql_guardrail"

def test_rejects_update():
    sql = "UPDATE users SET name = 'John' WHERE id = 1;"
    errors = SQLGuardrailValidator.validate(sql)
    assert len(errors) == 1
    assert errors[0]["type"] == "non_select_statement"

def test_rejects_insert():
    sql = "INSERT INTO users (id, name) VALUES (1, 'John');"
    errors = SQLGuardrailValidator.validate(sql)
    assert len(errors) == 1
    assert errors[0]["type"] == "non_select_statement"

def test_rejects_drop():
    sql = "DROP TABLE users;"
    errors = SQLGuardrailValidator.validate(sql)
    assert len(errors) == 1
    assert errors[0]["type"] == "non_select_statement"

def test_rejects_alter():
    sql = "ALTER TABLE users ADD COLUMN age INT;"
    errors = SQLGuardrailValidator.validate(sql)
    assert len(errors) == 1
    assert errors[0]["type"] == "non_select_statement"

def test_rejects_truncate():
    sql = "TRUNCATE TABLE users;"
    errors = SQLGuardrailValidator.validate(sql)
    assert len(errors) == 1
    assert errors[0]["type"] == "non_select_statement"

def test_rejects_create():
    sql = "CREATE TABLE new_users (id INT);"
    errors = SQLGuardrailValidator.validate(sql)
    assert len(errors) == 1
    assert errors[0]["type"] == "non_select_statement"

def test_rejects_multiple_statements():
    sql = "SELECT * FROM users; DROP TABLE users;"
    errors = SQLGuardrailValidator.validate(sql)
    assert len(errors) == 1
    assert errors[0]["type"] == "multiple_statements"
    assert errors[0]["stage"] == "sql_guardrail"

def test_rejects_empty_sql():
    sql = "   "
    errors = SQLGuardrailValidator.validate(sql)
    assert len(errors) == 1
    assert errors[0]["type"] == "empty_sql"
    assert errors[0]["stage"] == "sql_guardrail"

def test_rejects_comment_injection():
    sql = "SELECT * FROM users; -- DROP TABLE users;"
    errors = SQLGuardrailValidator.validate(sql)
    assert len(errors) == 1
    assert errors[0]["type"] == "multiple_statements"

def test_rejects_cte_with_dml():
    sql = """
    WITH deleted AS (
        DELETE FROM users RETURNING *
    )
    SELECT * FROM deleted;
    """
    errors = SQLGuardrailValidator.validate(sql)
    assert len(errors) == 1
    assert errors[0]["type"] == "unsafe_sql"
    assert errors[0]["details"]["reason"] == "dml_keyword_detected"
    assert errors[0]["details"]["keyword"] == "DELETE"

def test_rejects_unparseable_sql():
    sql = "SELECT FROM * WHERE id = 'unclosed string"
    errors = SQLGuardrailValidator.validate(sql)
    assert len(errors) == 1
    assert errors[0]["type"] == "sql_parse_error"
    assert errors[0]["stage"] == "sql_guardrail"
