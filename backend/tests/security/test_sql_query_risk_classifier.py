import json
import pytest
from dataclasses import FrozenInstanceError

from app.security.sql_query_risk_classifier import (
    SQL_QUERY_RISK_CLASSIFIER_CONTRACT_VERSION,
    SQLQueryRiskClassifierContractError,
    SQLQueryRiskLevel,
    SQLQueryRiskSignal,
    SQLQueryRiskRequest,
    SQLQueryRiskResult,
    SQLQueryRiskClassifier,
)

EXPECTED_RESULT_KEYS = {
    "version", "risk_level", "signals", "reason",
    "sql_sha256", "normalized_prefix", "dialect",
}


def _classify(sql, dialect="generic"):
    return SQLQueryRiskClassifier().classify(
        SQLQueryRiskRequest(
            version=SQL_QUERY_RISK_CLASSIFIER_CONTRACT_VERSION,
            sql=sql,
            dialect=dialect,
        )
    )


def test_query_risk_contract_version_is_stable():
    assert SQL_QUERY_RISK_CLASSIFIER_CONTRACT_VERSION == "sql_query_risk_classifier_contract_v1"


def test_query_risk_request_is_immutable():
    req = SQLQueryRiskRequest(version=SQL_QUERY_RISK_CLASSIFIER_CONTRACT_VERSION, sql="SELECT 1")
    with pytest.raises((FrozenInstanceError, AttributeError)):
        req.sql = "SELECT 2"  # type: ignore


def test_query_risk_result_is_immutable():
    result = _classify("SELECT 1")
    with pytest.raises((FrozenInstanceError, AttributeError)):
        result.risk_level = SQLQueryRiskLevel.CRITICAL  # type: ignore


def test_query_risk_low_for_clean_filtered_limited_select():
    result = _classify("SELECT id, name FROM users WHERE tenant_id = 1 LIMIT 100")
    assert result.risk_level == SQLQueryRiskLevel.LOW
    assert result.signals == ()
    # A trivial constant SELECT (no FROM) is also low.
    assert _classify("SELECT 1").risk_level == SQLQueryRiskLevel.LOW


def test_query_risk_medium_for_select_star():
    result = _classify("SELECT * FROM users WHERE id = 1 LIMIT 10")
    assert result.risk_level == SQLQueryRiskLevel.MEDIUM
    assert SQLQueryRiskSignal.SELECT_STAR in result.signals
    # t.* form also counts.
    assert SQLQueryRiskSignal.SELECT_STAR in _classify(
        "SELECT u.* FROM users u WHERE u.id = 1 LIMIT 1").signals


def test_query_risk_medium_for_missing_where():
    result = _classify("SELECT id FROM users LIMIT 50")
    assert result.risk_level == SQLQueryRiskLevel.MEDIUM
    assert SQLQueryRiskSignal.NO_WHERE_FILTER in result.signals


def test_query_risk_high_for_many_joins():
    sql = ("SELECT a.id FROM a "
           "JOIN b ON a.id = b.a_id "
           "JOIN c ON b.id = c.b_id "
           "JOIN d ON c.id = d.c_id "
           "JOIN e ON d.id = e.d_id "
           "WHERE a.id = 1 LIMIT 10")
    result = _classify(sql)
    assert result.risk_level == SQLQueryRiskLevel.HIGH
    assert SQLQueryRiskSignal.HIGH_JOIN_COUNT in result.signals


@pytest.mark.parametrize("sql", [
    "SELECT * FROM a, b",                      # comma-join, no WHERE
    "SELECT a.id FROM a CROSS JOIN b",         # explicit cross join
])
def test_query_risk_critical_for_cartesian_join(sql):
    result = _classify(sql)
    assert result.risk_level == SQLQueryRiskLevel.CRITICAL
    assert SQLQueryRiskSignal.CARTESIAN_JOIN in result.signals


@pytest.mark.parametrize("sql", [
    "SELECT setval('my_seq', 1)",
    "SELECT nextval('my_seq')",
    "SELECT lo_export(1234, '/tmp/out.txt')",
    "SELECT pg_terminate_backend(123)",
    "SELECT pg_sleep(10)",
    "WITH x AS (SELECT lo_unlink(1)) SELECT 1",
])
def test_query_risk_critical_for_side_effecting_function(sql):
    result = _classify(sql)
    assert result.risk_level == SQLQueryRiskLevel.CRITICAL
    assert SQLQueryRiskSignal.SIDE_EFFECTING_FUNCTION in result.signals


@pytest.mark.parametrize("sql", ["", "   ", None, 123, "-- just a comment", "DROP TABLE users"])
def test_query_risk_critical_for_empty_or_non_string_or_non_read(sql):
    result = _classify(sql)
    assert result.risk_level == SQLQueryRiskLevel.CRITICAL
    assert result.signals == (SQLQueryRiskSignal.INVALID_OR_UNPARSEABLE,)


def test_query_risk_non_string_has_no_hash_or_prefix():
    result = _classify(123)
    assert result.sql_sha256 is None
    assert result.normalized_prefix is None


def test_query_risk_signals_are_deduped_and_deterministic():
    # SELECT * with no WHERE and no LIMIT triggers several signals; order is the
    # canonical enum order and there are no duplicates.
    result = _classify("SELECT * FROM big_table")
    assert len(set(result.signals)) == len(result.signals)
    order = list(SQLQueryRiskSignal)
    positions = [order.index(s) for s in result.signals]
    assert positions == sorted(positions)
    # Deterministic across calls.
    assert _classify("SELECT * FROM big_table").signals == result.signals


def test_query_risk_level_is_max_severity_of_signals():
    # A query that is both SELECT * (medium) and side-effecting (critical) -> critical.
    result = _classify("SELECT *, pg_terminate_backend(1) FROM sessions")
    assert result.risk_level == SQLQueryRiskLevel.CRITICAL
    assert SQLQueryRiskSignal.SELECT_STAR in result.signals
    assert SQLQueryRiskSignal.SIDE_EFFECTING_FUNCTION in result.signals


def test_query_risk_result_shape_is_deterministic():
    result = _classify("SELECT * FROM users WHERE id = 1 LIMIT 10", dialect="postgresql")
    serialized = result.to_dict()
    assert set(serialized.keys()) == EXPECTED_RESULT_KEYS
    assert serialized["version"] == SQL_QUERY_RISK_CLASSIFIER_CONTRACT_VERSION
    assert serialized["risk_level"] == "medium"
    assert serialized["signals"] == ["select_star"]
    assert serialized["dialect"] == "postgresql"
    assert serialized["normalized_prefix"] == "SELECT"


def test_query_risk_result_is_json_serializable():
    for sql in ("SELECT 1", "SELECT * FROM a, b", "SELECT setval('s',1)", "", "DROP TABLE t"):
        json.dumps(_classify(sql).to_dict())


def test_query_risk_result_does_not_leak_raw_sql():
    secret = "super-secret-token-9999"
    sql = f"SELECT * FROM accounts WHERE api_token = '{secret}' AND note = 'drop into pg_sleep'"
    result = _classify(sql)
    serialized = json.dumps(result.to_dict())
    # Keywords/functions inside the string literal must NOT leak or trigger signals.
    assert secret not in serialized
    assert "accounts" not in serialized
    assert "api_token" not in serialized
    assert SQLQueryRiskSignal.SIDE_EFFECTING_FUNCTION not in result.signals  # pg_sleep was in a literal
    assert result.sql_sha256 is not None and len(result.sql_sha256) == 64
    assert result.normalized_prefix == "SELECT"


def test_query_risk_keywords_in_literals_do_not_trigger_signals():
    # 'CROSS JOIN' text inside a literal must not raise CARTESIAN_JOIN.
    result = _classify("SELECT note FROM t WHERE note = 'a CROSS JOIN b' AND id = 1 LIMIT 1")
    assert SQLQueryRiskSignal.CARTESIAN_JOIN not in result.signals
    assert result.risk_level == SQLQueryRiskLevel.LOW


def test_query_risk_does_not_allow_or_deny():
    # This is a classifier, not a gate: no decision field, no allow/deny value.
    result = _classify("SELECT 1")
    assert not hasattr(result, "decision")
    d = result.to_dict()
    assert "decision" not in d
    serialized = json.dumps(d)
    assert "allow" not in serialized and "deny" not in serialized


def test_query_risk_rejects_invalid_request_version():
    with pytest.raises(SQLQueryRiskClassifierContractError, match="version"):
        SQLQueryRiskRequest(version="wrong_version", sql="SELECT 1")


def test_query_risk_rejects_non_request_object():
    classifier = SQLQueryRiskClassifier()
    with pytest.raises(SQLQueryRiskClassifierContractError, match="request must be a SQLQueryRiskRequest"):
        classifier.classify("SELECT 1")  # type: ignore


def test_query_risk_does_not_import_db_adapters_or_drivers():
    import os
    import subprocess
    import sys
    import app.security
    security_dir = os.path.dirname(app.security.__file__)

    code = (
        "import sys\n"
        f"sys.path.insert(0, {repr(security_dir)})\n"
        "import app.security.sql_query_risk_classifier\n"
        "forbidden = ['psycopg2', 'psycopg', 'asyncpg', 'cx_Oracle', 'oracledb',\n"
        "             'sqlalchemy', 'sqlparse', 'socket', 'requests', 'urllib', 'http.client']\n"
        "for mod in forbidden:\n"
        "    if mod in sys.modules:\n"
        "        print(f'FORBIDDEN:{mod}')\n"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert "FORBIDDEN" not in res.stdout, f"Importing sql_query_risk_classifier loaded a forbidden module: {res.stdout}"
