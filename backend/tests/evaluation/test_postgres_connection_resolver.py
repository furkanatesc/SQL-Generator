from app.evaluation.postgres_connection_resolver import (
    POSTGRES_CONNECTION_RESOLVER_VERSION,
    resolve_local_docker_connection,
)
from app.evaluation.postgres_adapter import SQLPostgresLocalDockerConnection


def test_version_constant():
    assert POSTGRES_CONNECTION_RESOLVER_VERSION == "v1"


def test_resolves_valid_local_docker_env():
    env = {
        "POSTGRES_TEST_HOST": "localhost",
        "POSTGRES_TEST_PORT": "5432",
        "POSTGRES_TEST_DB": "sqlgen_test",
        "POSTGRES_TEST_USER": "sqlgen",
        "POSTGRES_TEST_PASSWORD": "sqlgen",
    }
    conn = resolve_local_docker_connection(env)
    assert isinstance(conn, SQLPostgresLocalDockerConnection)
    assert conn.host == "localhost"
    assert conn.port == 5432
    assert conn.dbname == "sqlgen_test"
    assert conn.user == "sqlgen"


def test_empty_env_uses_local_defaults():
    conn = resolve_local_docker_connection({})
    assert isinstance(conn, SQLPostgresLocalDockerConnection)
    assert conn.host == "localhost"
    assert conn.port == 5432


def test_remote_host_returns_none():
    conn = resolve_local_docker_connection({"POSTGRES_TEST_HOST": "db.prod.example.com"})
    assert conn is None


def test_invalid_port_returns_none_not_raise():
    for bad in ("abc", "0", "70000", ""):
        assert resolve_local_docker_connection({"POSTGRES_TEST_PORT": bad}) is None


def test_blank_required_field_returns_none():
    assert resolve_local_docker_connection({"POSTGRES_TEST_DB": "   "}) is None
    assert resolve_local_docker_connection({"POSTGRES_TEST_USER": ""}) is None


def test_none_env_does_not_raise():
    # Uses os.environ; must return a value or None, never raise.
    result = resolve_local_docker_connection(None)
    assert result is None or isinstance(result, SQLPostgresLocalDockerConnection)


def test_source_has_no_db_driver_import():
    # Purity guard: the resolver never imports a DB driver or opens a socket.
    import app.evaluation.postgres_connection_resolver as mod
    import inspect
    src = inspect.getsource(mod)
    assert "psycopg2" not in src
    assert "import socket" not in src
    assert ".connect(" not in src
