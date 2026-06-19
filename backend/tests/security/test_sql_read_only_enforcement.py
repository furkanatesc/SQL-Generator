import json
import pytest
from dataclasses import FrozenInstanceError

from app.security.sql_read_only_enforcement import (
    SQL_READ_ONLY_ENFORCEMENT_CONTRACT_VERSION,
    SQLReadOnlyEnforcementContractError,
    SQLReadOnlyDecision,
    SQLReadOnlyReasonCode,
    SQLReadOnlyEnforcementRequest,
    SQLReadOnlyEnforcementResult,
    SQLReadOnlyEnforcementContract,
)

EXPECTED_RESULT_KEYS = {
    "version", "decision", "reason_code", "reason",
    "sql_sha256", "normalized_prefix", "dialect",
}


def _enforce(sql, dialect="generic"):
    return SQLReadOnlyEnforcementContract().enforce(
        SQLReadOnlyEnforcementRequest(
            version=SQL_READ_ONLY_ENFORCEMENT_CONTRACT_VERSION,
            sql=sql,
            dialect=dialect,
        )
    )


def test_read_only_enforcement_contract_version_is_stable():
    assert SQL_READ_ONLY_ENFORCEMENT_CONTRACT_VERSION == "sql_read_only_enforcement_contract_v1"


def test_read_only_enforcement_request_is_immutable():
    req = SQLReadOnlyEnforcementRequest(
        version=SQL_READ_ONLY_ENFORCEMENT_CONTRACT_VERSION, sql="SELECT 1")
    with pytest.raises((FrozenInstanceError, AttributeError)):
        req.sql = "DROP TABLE t"  # type: ignore


def test_read_only_enforcement_result_is_immutable():
    result = _enforce("SELECT 1")
    with pytest.raises((FrozenInstanceError, AttributeError)):
        result.decision = SQLReadOnlyDecision.DENY  # type: ignore


def test_read_only_enforcement_allows_simple_select():
    result = _enforce("SELECT id, name FROM users WHERE id = 1")
    assert result.decision == SQLReadOnlyDecision.ALLOW
    assert result.reason_code == SQLReadOnlyReasonCode.READ_ONLY_SELECT
    assert result.is_read_only is True
    # A single trailing semicolon is tolerated.
    assert _enforce("SELECT 1;").decision == SQLReadOnlyDecision.ALLOW
    assert _enforce("  select 1  ").decision == SQLReadOnlyDecision.ALLOW


def test_read_only_enforcement_allows_select_with_cte_if_safe():
    sql = "WITH recent AS (SELECT id FROM orders WHERE id > 10) SELECT * FROM recent"
    result = _enforce(sql)
    assert result.decision == SQLReadOnlyDecision.ALLOW
    assert result.reason_code == SQLReadOnlyReasonCode.READ_ONLY_SELECT
    assert result.normalized_prefix == "WITH"


def test_read_only_enforcement_denies_empty_sql():
    for sql in ("", "   ", "\n\t "):
        result = _enforce(sql)
        assert result.decision == SQLReadOnlyDecision.DENY
        assert result.reason_code == SQLReadOnlyReasonCode.EMPTY_SQL
        # Empty (but still a string) is hashed; there is no keyword prefix.
        assert result.sql_sha256 is not None
        assert result.normalized_prefix is None


def test_read_only_enforcement_denies_non_string_sql():
    for bad in (123, None, ["SELECT 1"], {"sql": "SELECT 1"}):
        result = _enforce(bad)
        assert result.decision == SQLReadOnlyDecision.DENY
        assert result.reason_code == SQLReadOnlyReasonCode.INVALID_SQL_TYPE
        # Nothing to hash for a non-string input.
        assert result.sql_sha256 is None
        assert result.normalized_prefix is None


def test_read_only_enforcement_denies_multi_statement():
    # A second statement that is itself a SELECT still trips multi-statement.
    result = _enforce("SELECT 1; SELECT 2")
    assert result.decision == SQLReadOnlyDecision.DENY
    assert result.reason_code == SQLReadOnlyReasonCode.MULTI_STATEMENT
    # The classic injection tail is caught (here as multi-statement).
    assert _enforce("SELECT * FROM t; DROP TABLE t").decision == SQLReadOnlyDecision.DENY


def test_read_only_enforcement_denies_insert():
    result = _enforce("INSERT INTO users (id) VALUES (1)")
    assert result.decision == SQLReadOnlyDecision.DENY
    assert result.reason_code == SQLReadOnlyReasonCode.FORBIDDEN_KEYWORD


def test_read_only_enforcement_denies_update():
    result = _enforce("UPDATE users SET name = 'x' WHERE id = 1")
    assert result.decision == SQLReadOnlyDecision.DENY
    assert result.reason_code == SQLReadOnlyReasonCode.FORBIDDEN_KEYWORD


def test_read_only_enforcement_denies_delete():
    result = _enforce("DELETE FROM users WHERE id = 1")
    assert result.decision == SQLReadOnlyDecision.DENY
    assert result.reason_code == SQLReadOnlyReasonCode.FORBIDDEN_KEYWORD


@pytest.mark.parametrize("sql", [
    "DROP TABLE users",
    "ALTER TABLE users ADD COLUMN x int",
    "CREATE TABLE t (id int)",
    "TRUNCATE TABLE users",
])
def test_read_only_enforcement_denies_drop_alter_create_truncate(sql):
    result = _enforce(sql)
    assert result.decision == SQLReadOnlyDecision.DENY
    assert result.reason_code == SQLReadOnlyReasonCode.FORBIDDEN_KEYWORD


def test_read_only_enforcement_denies_merge():
    result = _enforce("MERGE INTO target USING src ON target.id = src.id "
                      "WHEN MATCHED THEN UPDATE SET target.v = src.v")
    assert result.decision == SQLReadOnlyDecision.DENY
    assert result.reason_code == SQLReadOnlyReasonCode.UNSAFE_DATA_MOVEMENT


@pytest.mark.parametrize("sql", [
    "CALL refresh_stats()",
    "EXEC sp_who",
    "EXECUTE my_proc",
])
def test_read_only_enforcement_denies_call_exec_execute(sql):
    result = _enforce(sql)
    assert result.decision == SQLReadOnlyDecision.DENY
    assert result.reason_code == SQLReadOnlyReasonCode.UNSAFE_PROCEDURE


def test_read_only_enforcement_denies_copy():
    result = _enforce("COPY users TO '/tmp/out.csv'")
    assert result.decision == SQLReadOnlyDecision.DENY
    assert result.reason_code == SQLReadOnlyReasonCode.UNSAFE_DATA_MOVEMENT


def test_read_only_enforcement_denies_select_into():
    # SELECT ... INTO creates/moves data in several dialects -> data movement.
    result = _enforce("SELECT * INTO archived_users FROM users")
    assert result.decision == SQLReadOnlyDecision.DENY
    assert result.reason_code == SQLReadOnlyReasonCode.UNSAFE_DATA_MOVEMENT


def test_read_only_enforcement_result_shape_is_deterministic():
    result = _enforce("SELECT 1", dialect="postgresql")
    serialized = result.to_dict()
    assert set(serialized.keys()) == EXPECTED_RESULT_KEYS
    assert serialized["version"] == SQL_READ_ONLY_ENFORCEMENT_CONTRACT_VERSION
    assert serialized["decision"] == "allow"
    assert serialized["reason_code"] == "read_only_select"
    assert serialized["dialect"] == "postgresql"
    assert serialized["normalized_prefix"] == "SELECT"
    # Hash is deterministic across runs/instances.
    assert _enforce("SELECT 1").sql_sha256 == result.sql_sha256


def test_read_only_enforcement_result_is_json_serializable():
    for sql in ("SELECT 1", "DROP TABLE t", "SELECT 1; SELECT 2", ""):
        json.dumps(_enforce(sql).to_dict())


def test_read_only_enforcement_result_does_not_leak_raw_sql():
    secret = "super-secret-token-value-1234567890"
    sql = f"SELECT * FROM accounts WHERE api_token = '{secret}'"
    result = _enforce(sql)
    serialized = json.dumps(result.to_dict())
    # The raw SQL (and the embedded secret literal) must never appear in the result.
    assert secret not in serialized
    assert "accounts" not in serialized
    assert "api_token" not in serialized
    # Only a hash + the leading keyword are exposed.
    assert result.sql_sha256 is not None and len(result.sql_sha256) == 64
    assert result.normalized_prefix == "SELECT"


@pytest.mark.parametrize("sql", [
    "/* leading hint */ SELECT 1",
    "-- a note\nSELECT id FROM users",
    "  /* x */\n  -- y\n  SELECT 1",
    "SELECT 1 -- trailing comment",
    "SELECT id FROM users /* inline */ WHERE id = 1",
])
def test_read_only_enforcement_allows_select_with_comments(sql):
    # Fix #4: comments are stripped before classification, so a leading/inline
    # comment no longer turns a valid read-only SELECT into a NON_SELECT deny.
    result = _enforce(sql)
    assert result.decision == SQLReadOnlyDecision.ALLOW, result.reason
    assert result.reason_code == SQLReadOnlyReasonCode.READ_ONLY_SELECT


@pytest.mark.parametrize("sql", [
    "SELECT comment FROM tickets",            # bare column named like a keyword
    "SELECT t.begin, t.lock FROM t",          # more keyword-named columns
    'SELECT * FROM "merge"',                  # quoted identifier equal to a keyword
    'SELECT "lock", "copy" FROM "analyze"',   # quoted identifiers
    "SELECT note FROM t WHERE note = 'ship into the drop zone'",  # keywords inside a literal
    "SELECT ';' AS semi",                     # semicolon inside a literal is not a separator
])
def test_read_only_enforcement_allows_keywords_in_literals_and_identifiers(sql):
    # Fix #5: forbidden keywords are matched only in executable code, not inside
    # string literals or quoted identifiers, and non-leading-only keywords no
    # longer reject ordinary column/table names.
    result = _enforce(sql)
    assert result.decision == SQLReadOnlyDecision.ALLOW, result.reason
    assert result.reason_code == SQLReadOnlyReasonCode.READ_ONLY_SELECT


@pytest.mark.parametrize("sql,reason_code", [
    # A real (executable) write must still be denied after sanitization.
    ("WITH x AS (DELETE FROM t RETURNING id) SELECT * FROM x", SQLReadOnlyReasonCode.FORBIDDEN_KEYWORD),
    ("WITH x AS (UPDATE t SET a = 1 RETURNING id) SELECT * FROM x", SQLReadOnlyReasonCode.FORBIDDEN_KEYWORD),
    ("WITH x AS (INSERT INTO t VALUES (1) RETURNING id) SELECT * FROM x", SQLReadOnlyReasonCode.FORBIDDEN_KEYWORD),
    ("SELECT * FROM t FOR UPDATE", SQLReadOnlyReasonCode.FORBIDDEN_KEYWORD),
    # Balanced-quote injection tail: the ; and DROP land in code position.
    ("SELECT * FROM t WHERE name = '' ; DROP TABLE t; --", SQLReadOnlyReasonCode.MULTI_STATEMENT),
    # A real trailing comment that hides a second statement is still caught.
    ("SELECT 1; DELETE FROM t", SQLReadOnlyReasonCode.MULTI_STATEMENT),
])
def test_read_only_enforcement_still_denies_executable_writes(sql, reason_code):
    # Sanitization must not open a bypass: real writes in executable position stay denied.
    result = _enforce(sql)
    assert result.decision == SQLReadOnlyDecision.DENY, result.reason
    assert result.reason_code == reason_code


def test_read_only_enforcement_sql_sha256_is_a_real_digest():
    import hashlib
    sql = "SELECT 1"
    expected = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    assert _enforce(sql).sql_sha256 == expected


def test_read_only_enforcement_rejects_invalid_request_version():
    with pytest.raises(SQLReadOnlyEnforcementContractError, match="version"):
        SQLReadOnlyEnforcementRequest(version="wrong_version", sql="SELECT 1")


def test_read_only_enforcement_rejects_non_request_object():
    contract = SQLReadOnlyEnforcementContract()
    with pytest.raises(SQLReadOnlyEnforcementContractError, match="request must be a SQLReadOnlyEnforcementRequest"):
        contract.enforce("SELECT 1")  # type: ignore


def test_read_only_enforcement_does_not_import_db_adapters_or_drivers():
    import os
    import subprocess
    import sys
    import app.security
    security_dir = os.path.dirname(app.security.__file__)

    code = (
        "import sys\n"
        f"sys.path.insert(0, {repr(security_dir)})\n"
        "import sql_read_only_enforcement\n"
        "forbidden = ['psycopg2', 'psycopg', 'asyncpg', 'cx_Oracle', 'oracledb',\n"
        "             'sqlalchemy', 'sqlparse', 'socket', 'requests', 'urllib', 'http.client']\n"
        "for mod in forbidden:\n"
        "    if mod in sys.modules:\n"
        "        print(f'FORBIDDEN:{mod}')\n"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert "FORBIDDEN" not in res.stdout, f"Importing sql_read_only_enforcement loaded a forbidden module: {res.stdout}"


def test_postgres_adapter_uses_shared_read_only_enforcement_contract():
    # The adapter's read-only gate must agree with the shared contract on every
    # case — i.e. it delegates rather than keeping a divergent copy of the rules.
    from app.evaluation import postgres_adapter

    enforcer = SQLReadOnlyEnforcementContract()
    cases = [
        "SELECT 1",
        "SELECT id FROM users",
        "WITH c AS (SELECT 1) SELECT * FROM c",
        "INSERT INTO users VALUES (1)",
        "UPDATE users SET x = 1",
        "DELETE FROM users",
        "DROP TABLE users",
        "SELECT 1; DROP TABLE users",
        "SELECT * INTO t2 FROM t1",
        "CALL p()",
        "COPY t TO '/tmp/x'",
        "",
    ]
    for sql in cases:
        shared = enforcer.enforce(SQLReadOnlyEnforcementRequest(
            version=SQL_READ_ONLY_ENFORCEMENT_CONTRACT_VERSION, sql=sql, dialect="postgresql"))
        adapter_reason = postgres_adapter.validate_read_only_select(sql)
        allowed_by_adapter = adapter_reason is None
        allowed_by_shared = shared.decision == SQLReadOnlyDecision.ALLOW
        assert allowed_by_adapter == allowed_by_shared, f"divergence on: {sql!r}"
        # When rejected, the adapter surfaces the shared contract's reason verbatim.
        if not allowed_by_shared:
            assert adapter_reason == shared.reason


def test_postgres_and_oracle_adapters_agree_on_read_only_gate():
    # Closes the cross-adapter divergence: both adapters now delegate to the same
    # shared contract, so they must agree on every input (incl. WITH/CTE, which the
    # old per-adapter copies disagreed on).
    from app.evaluation import postgres_adapter, oracle_adapter

    cases = [
        "SELECT 1",
        "WITH c AS (SELECT 1) SELECT * FROM c",   # previously: PG reject, Oracle reject; now both allow
        "SELECT comment FROM t",                   # keyword-named column
        "INSERT INTO t VALUES (1)",
        "DROP TABLE t",
        "CALL p()",
        "SELECT 1; DROP TABLE t",
        "",
    ]
    for sql in cases:
        pg = postgres_adapter.validate_read_only_select(sql)
        ora = oracle_adapter.validate_read_only_select(sql)
        assert (pg is None) == (ora is None), f"adapters diverge on: {sql!r} (pg={pg!r}, oracle={ora!r})"
