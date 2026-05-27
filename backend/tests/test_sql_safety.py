import pytest
from app.sql_safety import SqlSafetyValidator

@pytest.fixture
def validator():
    return SqlSafetyValidator()

def test_happy_path_select(validator):
    # Standard query should pass
    validator.ensure_read_only("SELECT * FROM users;")
    validator.ensure_read_only("select id, name from products where price > 100")
    validator.ensure_read_only("   SELECT * FROM users")

def test_happy_path_cte(validator):
    # Queries using WITH/CTE should pass
    validator.ensure_read_only("WITH cte AS (SELECT * FROM users) SELECT * FROM cte;")
    validator.ensure_read_only("WITH test AS (SELECT id FROM accounts) SELECT account_id FROM transactions JOIN test ON transactions.account_id = test.id")

def test_empty_sql_rejected(validator):
    # Empty queries must raise ValueError
    with pytest.raises(ValueError, match="SQL query cannot be empty"):
        validator.ensure_read_only("")
    with pytest.raises(ValueError, match="SQL query cannot be empty"):
        validator.ensure_read_only("   ")
    with pytest.raises(ValueError, match="SQL query cannot be empty"):
        validator.ensure_read_only("\n\t  ")

def test_multiple_statements_rejected(validator):
    # Multiple statements must be blocked
    with pytest.raises(ValueError, match="Only single statements are allowed"):
        validator.ensure_read_only("SELECT * FROM users; SELECT * FROM products;")
    with pytest.raises(ValueError, match="Only single statements are allowed"):
        validator.ensure_read_only("SELECT * FROM users; DROP TABLE products;")

def test_non_select_statements_rejected(validator):
    # DML and DDL commands should be rejected
    with pytest.raises(ValueError):
        validator.ensure_read_only("INSERT INTO users (name) VALUES ('Alice');")
    with pytest.raises(ValueError):
        validator.ensure_read_only("UPDATE users SET name = 'Bob';")
    with pytest.raises(ValueError):
        validator.ensure_read_only("DELETE FROM users;")
    with pytest.raises(ValueError):
        validator.ensure_read_only("DROP TABLE users;")
    with pytest.raises(ValueError):
        validator.ensure_read_only("ALTER TABLE users ADD COLUMN age INTEGER;")
    with pytest.raises(ValueError):
        validator.ensure_read_only("CREATE TABLE logs (id INTEGER);")

def test_case_insensitive_keywords(validator):
    # Validator must be case-insensitive
    with pytest.raises(ValueError):
        validator.ensure_read_only("delete from users")
    with pytest.raises(ValueError):
        validator.ensure_read_only("DeLeTe FROM users")
    with pytest.raises(ValueError):
        validator.ensure_read_only("uPdAtE users SET name = 'X'")

def test_leading_whitespace_bypass_prevented(validator):
    # Leading whitespace before forbidden statement must be blocked
    with pytest.raises(ValueError):
        validator.ensure_read_only("   DELETE FROM users")
    with pytest.raises(ValueError):
        validator.ensure_read_only("\n\t  DROP TABLE products")

def test_comment_bypass_prevented(validator):
    # Inline comments and block comments attempting to mask forbidden commands
    with pytest.raises(ValueError):
        validator.ensure_read_only("-- comment here\nDELETE FROM users")
    with pytest.raises(ValueError):
        validator.ensure_read_only("/* block comment */ DROP TABLE users")
    with pytest.raises(ValueError):
        validator.ensure_read_only("SELECT * FROM users; -- comment\nDELETE FROM products")
    with pytest.raises(ValueError):
        validator.ensure_read_only("SELECT * FROM users; /* comment */ DROP TABLE products")

VALID_WRITE_QUERIES = {
    "insert": "INSERT INTO users VALUES (1);",
    "update": "UPDATE users SET name = 'X';",
    "delete": "DELETE FROM users;",
    "drop": "DROP TABLE users;",
    "alter": "ALTER TABLE users ADD COLUMN age INT;",
    "create": "CREATE TABLE test (id INT);",
    "truncate": "TRUNCATE TABLE users;",
    "replace": "REPLACE INTO users VALUES (1);",
    "merge": "MERGE INTO users USING active ON id=id WHEN MATCHED THEN UPDATE SET name = 'X';",
    "grant": "GRANT SELECT ON users TO public;",
    "revoke": "REVOKE SELECT ON users FROM public;",
    "vacuum": "VACUUM;",
    "analyze": "ANALYZE users;",
    "pragma": "PRAGMA user_version;",
    "attach": "ATTACH DATABASE 'file' AS test;",
    "detach": "DETACH DATABASE test;"
}

@pytest.mark.parametrize("keyword", [
    "insert", "update", "delete", "drop", "alter", "create", 
    "truncate", "replace", "merge", "grant", "revoke", 
    "vacuum", "analyze", "pragma", "attach", "detach"
])
def test_all_denylist_keywords_blocked(validator, keyword):
    query = VALID_WRITE_QUERIES[keyword]
    
    # Test lowercase standalone command keyword in query
    with pytest.raises(ValueError):
        validator.ensure_read_only(query.lower())
    
    # Test uppercase standalone command keyword in query
    with pytest.raises(ValueError):
        validator.ensure_read_only(query.upper())
        
    # Test wrapped inside leading whitespace/comments
    with pytest.raises(ValueError):
        validator.ensure_read_only(f"  /* comment */  \n {query}")

def test_string_literal_false_positives_allowed(validator):
    # Queries selecting or filtering with forbidden keywords as string literals must pass
    validator.ensure_read_only("SELECT 'delete' AS action_name;")
    validator.ensure_read_only("SELECT \"update\" FROM audit_events;")
    validator.ensure_read_only("SELECT status FROM logs WHERE action = 'delete';")
    validator.ensure_read_only("SELECT 'create table' AS test_val, * FROM users WHERE status = 'grant';")
