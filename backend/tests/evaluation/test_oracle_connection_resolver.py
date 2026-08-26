from app.evaluation.oracle_connection_resolver import resolve_local_docker_connection


def test_resolver_defaults_to_local_docker_connection():
    conn = resolve_local_docker_connection(env={})
    assert conn is not None
    assert conn.host == "localhost"
    assert conn.port == 1521
    assert conn.service_name == "FREEPDB1"
    assert conn.user == "sqlgen"


def test_resolver_reads_env_overrides():
    conn = resolve_local_docker_connection(env={
        "ORACLE_TEST_HOST": "127.0.0.1",
        "ORACLE_TEST_PORT": "1522",
        "ORACLE_TEST_SERVICE": "XEPDB1",
        "ORACLE_TEST_USER": "u",
        "ORACLE_TEST_PASSWORD": "p",
    })
    assert conn is not None
    assert conn.port == 1522
    assert conn.service_name == "XEPDB1"


def test_resolver_returns_none_for_remote_host():
    assert resolve_local_docker_connection(env={"ORACLE_TEST_HOST": "db.prod"}) is None


def test_resolver_returns_none_for_bad_port():
    assert resolve_local_docker_connection(env={"ORACLE_TEST_PORT": "not-an-int"}) is None
