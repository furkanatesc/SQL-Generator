from app.evaluation.mssql_connection_resolver import (
    resolve_local_docker_connection, MSSQL_CONNECTION_RESOLVER_VERSION,
)


def test_version():
    assert MSSQL_CONNECTION_RESOLVER_VERSION == "v1"


def test_defaults_build_local_readonly_connection():
    conn = resolve_local_docker_connection(env={})
    assert conn is not None
    assert conn.host == "localhost" and conn.port == 1433
    assert conn.database == "sqlgen_test" and conn.user == "sqlgen_ro"


def test_remote_host_yields_none():
    conn = resolve_local_docker_connection(env={"MSSQL_TEST_HOST": "db.prod.example.com"})
    assert conn is None


def test_bad_port_yields_none():
    conn = resolve_local_docker_connection(env={"MSSQL_TEST_PORT": "not-an-int"})
    assert conn is None


def test_custom_env_values():
    conn = resolve_local_docker_connection(env={
        "MSSQL_TEST_HOST": "127.0.0.1", "MSSQL_TEST_PORT": "14330",
        "MSSQL_TEST_DB": "d", "MSSQL_TEST_USER": "u", "MSSQL_TEST_PASSWORD": "p",
    })
    assert conn is not None and conn.port == 14330 and conn.database == "d"
