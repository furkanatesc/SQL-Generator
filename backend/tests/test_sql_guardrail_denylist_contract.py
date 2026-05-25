from app.sql_guardrail import SQLGuardrailValidator


def test_guardrail_dangerous_function_denylist_contains_required_minimum_set():
    required_functions = {
        "pg_sleep",
        "pg_read_file",
        "pg_ls_dir",
        "dblink",
        "lo_import",
        "lo_export",
    }

    assert required_functions.issubset(SQLGuardrailValidator.DANGEROUS_FUNCTION_NAMES)


def test_guardrail_forbidden_keywords_contain_required_dml_ddl_minimum_set():
    required_keywords = {
        "delete",
        "update",
        "insert",
        "drop",
        "alter",
        "truncate",
        "create",
        "grant",
        "revoke",
        "commit",
        "rollback",
        "command",
    }

    assert required_keywords.issubset(SQLGuardrailValidator.FORBIDDEN_KEYS)


def test_guardrail_forbidden_node_types_are_not_empty():
    assert SQLGuardrailValidator.FORBIDDEN_NODE_TYPES


def test_guardrail_rejects_required_dangerous_functions_behaviorally():
    cases = [
        ("SELECT pg_sleep(1);", "PG_SLEEP"),
        ("SELECT pg_read_file('/etc/passwd');", "PG_READ_FILE"),
        ("SELECT dblink('dbname=prod', 'SELECT 1');", "DBLINK"),
    ]

    for sql, expected_function in cases:
        errors = SQLGuardrailValidator.validate(sql, dialect="postgres")

        assert len(errors) == 1
        assert errors[0]["type"] == "unsafe_sql"
        assert errors[0]["stage"] == "sql_guardrail"
        assert errors[0]["details"]["reason"] == "dangerous_function_detected"
        assert errors[0]["details"]["function"] == expected_function


def test_guardrail_denylist_does_not_block_common_safe_functions():
    safe_queries = [
        "SELECT COUNT(*) FROM orders;",
        "SELECT MAX(total) FROM orders;",
        "SELECT LOWER(name) FROM customers;",
        "SELECT COALESCE(email, 'unknown') FROM customers;",
    ]

    for sql in safe_queries:
        assert SQLGuardrailValidator.validate(sql, dialect="postgres") == []
