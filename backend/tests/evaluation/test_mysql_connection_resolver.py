from app.evaluation.mysql_connection_resolver import (
    resolve_local_docker_connection, MYSQL_CONNECTION_RESOLVER_VERSION,
)


def test_version():
    assert MYSQL_CONNECTION_RESOLVER_VERSION == "v1"


def test_defaults_build_local_connection():
    conn = resolve_local_docker_connection(env={})
    assert conn is not None
    assert conn.host == "localhost" and conn.port == 3306
    assert conn.database == "sqlgen_test" and conn.user == "sqlgen"


def test_remote_host_yields_none():
    conn = resolve_local_docker_connection(env={"MYSQL_TEST_HOST": "db.prod.example.com"})
    assert conn is None


def test_bad_port_yields_none():
    conn = resolve_local_docker_connection(env={"MYSQL_TEST_PORT": "not-an-int"})
    assert conn is None


def test_custom_env_values():
    conn = resolve_local_docker_connection(env={
        "MYSQL_TEST_HOST": "127.0.0.1", "MYSQL_TEST_PORT": "3307",
        "MYSQL_TEST_DB": "d", "MYSQL_TEST_USER": "u", "MYSQL_TEST_PASSWORD": "p",
    })
    assert conn is not None and conn.port == 3307 and conn.database == "d"
