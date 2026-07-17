from app.sql_guardrail import SQLGuardrailValidator


def test_guardrail_allows_simple_read_only_cte():
    sql = """
    WITH active_customers AS (
        SELECT id, name FROM customers WHERE active = true
    )
    SELECT id, name FROM active_customers;
    """

    assert SQLGuardrailValidator.validate(sql, dialect="postgres") == []


def test_guardrail_allows_multiple_read_only_ctes():
    sql = """
    WITH customers_base AS (
        SELECT id, name FROM customers
    ),
    orders_base AS (
        SELECT customer_id, total FROM orders
    )
    SELECT c.id, c.name, o.total
    FROM customers_base c
    JOIN orders_base o ON o.customer_id = c.id;
    """

    assert SQLGuardrailValidator.validate(sql, dialect="postgres") == []


def test_guardrail_allows_nested_read_only_cte():
    sql = """
    WITH base AS (
        SELECT id, name FROM customers
    ),
    filtered AS (
        SELECT id, name FROM base WHERE id > 10
    )
    SELECT * FROM filtered;
    """

    assert SQLGuardrailValidator.validate(sql, dialect="postgres") == []


def test_guardrail_rejects_delete_inside_cte():
    sql = """
    WITH deleted AS (
        DELETE FROM customers WHERE id = 1 RETURNING *
    )
    SELECT * FROM deleted;
    """

    errors = SQLGuardrailValidator.validate(sql, dialect="postgres")

    assert len(errors) == 1
    assert errors[0]["type"] == "unsafe_dml_keyword"
    assert errors[0]["stage"] == "sql_guardrail"
    assert errors[0]["details"]["reason"] == "dml_keyword_detected"
    assert errors[0]["details"]["keyword"] == "DELETE"


def test_guardrail_rejects_update_inside_cte():
    sql = """
    WITH updated AS (
        UPDATE customers SET name = 'x' WHERE id = 1 RETURNING *
    )
    SELECT * FROM updated;
    """

    errors = SQLGuardrailValidator.validate(sql, dialect="postgres")

    assert len(errors) == 1
    assert errors[0]["type"] in {"unsafe_dml_keyword", "sql_parse_error", "non_select_statement"}


def test_guardrail_rejects_insert_inside_cte():
    sql = """
    WITH inserted AS (
        INSERT INTO customers (id, name) VALUES (1, 'x') RETURNING *
    )
    SELECT * FROM inserted;
    """

    errors = SQLGuardrailValidator.validate(sql, dialect="postgres")

    assert len(errors) == 1
    assert errors[0]["type"] in {"unsafe_dml_keyword", "sql_parse_error", "non_select_statement"}


def test_guardrail_rejects_create_inside_cte():
    sql = """
    WITH created AS (
        CREATE TABLE temp_customers AS SELECT * FROM customers
    )
    SELECT * FROM created;
    """

    errors = SQLGuardrailValidator.validate(sql, dialect="postgres")

    assert len(errors) == 1
    assert errors[0]["type"] in {"unsafe_dml_keyword", "sql_parse_error", "non_select_statement"}


def test_guardrail_rejects_cte_plus_second_statement():
    sql = """
    WITH safe_cte AS (
        SELECT id FROM customers
    )
    SELECT * FROM safe_cte;
    DROP TABLE customers;
    """

    errors = SQLGuardrailValidator.validate(sql, dialect="postgres")

    assert len(errors) == 1
    assert errors[0]["type"] == "multiple_statements"
    assert errors[0]["stage"] == "sql_guardrail"


def test_guardrail_allows_read_only_cte_with_oracle_dialect():
    sql = """
    WITH active_customers AS (
        SELECT id, name FROM customers
    )
    SELECT id, name FROM active_customers
    """

    assert SQLGuardrailValidator.validate(sql, dialect="oracle") == []
