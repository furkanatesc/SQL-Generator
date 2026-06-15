from dataclasses import FrozenInstanceError
import pytest

from app.evaluation.multi_database_execution import SQLDatabaseDialect
from app.evaluation.connection_abstraction import (
    SQL_CONNECTION_ABSTRACTION_VERSION,
    SQLConnectionEnvironment,
    SQLConnectionAuthMode,
    SQLConnectionAccessMode,
    SQLConnectionSecretRef,
    SQLConnectionEndpoint,
    SQLConnectionProfile,
    SQLConnectionRegistry,
    SQLConnectionResolver,
    SQLResolvedConnection,
    SQLConnectionPolicy,
    SQLConnectionAbstractionContractError,
)


def test_connection_abstraction_version_is_v1():
    assert SQL_CONNECTION_ABSTRACTION_VERSION == "sql_connection_abstraction_v1"


def test_secret_ref_is_frozen():
    secret_ref = SQLConnectionSecretRef(provider="vault", key="db_pass")
    with pytest.raises(FrozenInstanceError):
        secret_ref.key = "new_key"  # type: ignore


def test_secret_ref_rejects_empty_provider():
    with pytest.raises(SQLConnectionAbstractionContractError):
        SQLConnectionSecretRef(provider="", key="db_pass")
    with pytest.raises(SQLConnectionAbstractionContractError):
        SQLConnectionSecretRef(provider="   ", key="db_pass")


def test_secret_ref_rejects_empty_key():
    with pytest.raises(SQLConnectionAbstractionContractError):
        SQLConnectionSecretRef(provider="vault", key="")
    with pytest.raises(SQLConnectionAbstractionContractError):
        SQLConnectionSecretRef(provider="vault", key="   ")


def test_endpoint_rejects_empty_host():
    with pytest.raises(SQLConnectionAbstractionContractError):
        SQLConnectionEndpoint(host="", port=5432, database="testdb")
    with pytest.raises(SQLConnectionAbstractionContractError):
        SQLConnectionEndpoint(host="  ", port=5432, database="testdb")


def test_endpoint_rejects_invalid_port():
    with pytest.raises(SQLConnectionAbstractionContractError):
        SQLConnectionEndpoint(host="localhost", port=0, database="testdb")
    with pytest.raises(SQLConnectionAbstractionContractError):
        SQLConnectionEndpoint(host="localhost", port=65536, database="testdb")
    with pytest.raises(SQLConnectionAbstractionContractError):
        SQLConnectionEndpoint(host="localhost", port=-1, database="testdb")
    with pytest.raises(SQLConnectionAbstractionContractError):
        SQLConnectionEndpoint(host="localhost", port=True, database="testdb")  # type: ignore
    with pytest.raises(SQLConnectionAbstractionContractError):
        SQLConnectionEndpoint(host="localhost", port="5432", database="testdb")  # type: ignore


def test_endpoint_rejects_empty_database():
    with pytest.raises(SQLConnectionAbstractionContractError):
        SQLConnectionEndpoint(host="localhost", port=5432, database="")
    with pytest.raises(SQLConnectionAbstractionContractError):
        SQLConnectionEndpoint(host="localhost", port=5432, database="  ")


def test_profile_is_frozen():
    endpoint = SQLConnectionEndpoint(host="localhost", port=5432, database="db")
    profile = SQLConnectionProfile(
        connection_ref="ref_01",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        environment=SQLConnectionEnvironment.DEV,
        endpoint=endpoint,
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.NONE,
        secret_ref=None
    )
    with pytest.raises(FrozenInstanceError):
        profile.max_rows = 500  # type: ignore


def test_profile_requires_secret_ref_for_secret_ref_auth():
    endpoint = SQLConnectionEndpoint(host="localhost", port=5432, database="db")
    with pytest.raises(SQLConnectionAbstractionContractError):
        SQLConnectionProfile(
            connection_ref="ref_01",
            dialect=SQLDatabaseDialect.POSTGRESQL,
            environment=SQLConnectionEnvironment.DEV,
            endpoint=endpoint,
            access_mode=SQLConnectionAccessMode.READ_ONLY,
            auth_mode=SQLConnectionAuthMode.SECRET_REF,
            secret_ref=None
        )


def test_profile_rejects_secret_ref_for_none_auth():
    endpoint = SQLConnectionEndpoint(host="localhost", port=5432, database="db")
    secret_ref = SQLConnectionSecretRef(provider="vault", key="key")
    with pytest.raises(SQLConnectionAbstractionContractError):
        SQLConnectionProfile(
            connection_ref="ref_01",
            dialect=SQLDatabaseDialect.POSTGRESQL,
            environment=SQLConnectionEnvironment.DEV,
            endpoint=endpoint,
            access_mode=SQLConnectionAccessMode.READ_ONLY,
            auth_mode=SQLConnectionAuthMode.NONE,
            secret_ref=secret_ref
        )


def test_profile_rejects_non_read_only_access_mode():
    endpoint = SQLConnectionEndpoint(host="localhost", port=5432, database="db")
    with pytest.raises(SQLConnectionAbstractionContractError):
        SQLConnectionProfile(
            connection_ref="ref_01",
            dialect=SQLDatabaseDialect.POSTGRESQL,
            environment=SQLConnectionEnvironment.DEV,
            endpoint=endpoint,
            access_mode="read_write",  # type: ignore
            auth_mode=SQLConnectionAuthMode.NONE,
            secret_ref=None
        )


def test_registry_rejects_duplicate_connection_ref():
    endpoint = SQLConnectionEndpoint(host="localhost", port=5432, database="db")
    p1 = SQLConnectionProfile(
        connection_ref="ref_dup",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        environment=SQLConnectionEnvironment.DEV,
        endpoint=endpoint,
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.NONE,
        secret_ref=None
    )
    p2 = SQLConnectionProfile(
        connection_ref="ref_dup",
        dialect=SQLDatabaseDialect.SQLITE,
        environment=SQLConnectionEnvironment.LOCAL,
        endpoint=endpoint,
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.NONE,
        secret_ref=None
    )
    with pytest.raises(SQLConnectionAbstractionContractError):
        SQLConnectionRegistry(profiles=(p1, p2))


def test_registry_rejects_unknown_connection_ref():
    registry = SQLConnectionRegistry(profiles=())
    with pytest.raises(SQLConnectionAbstractionContractError):
        registry.get_profile("ref_unknown")


def test_policy_rejects_prod_by_default():
    endpoint = SQLConnectionEndpoint(host="prod-db", port=1521, database="proddb")
    p = SQLConnectionProfile(
        connection_ref="prod_ref",
        dialect=SQLDatabaseDialect.ORACLE,
        environment=SQLConnectionEnvironment.PROD,
        endpoint=endpoint,
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.NONE,
        secret_ref=None
    )
    registry = SQLConnectionRegistry(profiles=(p,))
    policy = SQLConnectionPolicy(
        allowed_environments=(SQLConnectionEnvironment.LOCAL, SQLConnectionEnvironment.DEV),
        allowed_dialects=(SQLDatabaseDialect.SQLITE, SQLDatabaseDialect.POSTGRESQL, SQLDatabaseDialect.ORACLE),
        require_read_only=True,
        allow_prod=False  # Rejects prod
    )
    resolver = SQLConnectionResolver(registry=registry, policy=policy)
    
    with pytest.raises(SQLConnectionAbstractionContractError) as exc_info:
        resolver.resolve("prod_ref")
    assert "not allowed" in str(exc_info.value) or "blocked" in str(exc_info.value)


def test_policy_allows_prod_when_configured():
    endpoint = SQLConnectionEndpoint(host="prod-db", port=1521, database="proddb")
    p = SQLConnectionProfile(
        connection_ref="prod_ref",
        dialect=SQLDatabaseDialect.ORACLE,
        environment=SQLConnectionEnvironment.PROD,
        endpoint=endpoint,
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.NONE,
        secret_ref=None
    )
    registry = SQLConnectionRegistry(profiles=(p,))
    policy = SQLConnectionPolicy(
        allowed_environments=(SQLConnectionEnvironment.PROD, SQLConnectionEnvironment.LOCAL),
        allowed_dialects=(SQLDatabaseDialect.ORACLE,),
        require_read_only=True,
        allow_prod=True  # Allows prod
    )
    resolver = SQLConnectionResolver(registry=registry, policy=policy)
    resolved = resolver.resolve("prod_ref")
    assert resolved.connection_ref == "prod_ref"
    assert resolved.environment == SQLConnectionEnvironment.PROD


def test_policy_rejects_disallowed_dialect():
    endpoint = SQLConnectionEndpoint(host="localhost", port=5432, database="db")
    p = SQLConnectionProfile(
        connection_ref="pg_ref",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        environment=SQLConnectionEnvironment.DEV,
        endpoint=endpoint,
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.NONE,
        secret_ref=None
    )
    registry = SQLConnectionRegistry(profiles=(p,))
    # policy only allows SQLITE
    policy = SQLConnectionPolicy(
        allowed_environments=(SQLConnectionEnvironment.DEV,),
        allowed_dialects=(SQLDatabaseDialect.SQLITE,),
        require_read_only=True,
        allow_prod=False
    )
    resolver = SQLConnectionResolver(registry=registry, policy=policy)
    with pytest.raises(SQLConnectionAbstractionContractError) as exc_info:
        resolver.resolve("pg_ref")
    assert "Dialect" in str(exc_info.value) and "not allowed" in str(exc_info.value)


def test_policy_rejects_disallowed_environment():
    endpoint = SQLConnectionEndpoint(host="localhost", port=5432, database="db")
    p = SQLConnectionProfile(
        connection_ref="staging_ref",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        environment=SQLConnectionEnvironment.STAGING,
        endpoint=endpoint,
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.NONE,
        secret_ref=None
    )
    registry = SQLConnectionRegistry(profiles=(p,))
    # policy only allows LOCAL and DEV
    policy = SQLConnectionPolicy(
        allowed_environments=(SQLConnectionEnvironment.LOCAL, SQLConnectionEnvironment.DEV),
        allowed_dialects=(SQLDatabaseDialect.POSTGRESQL,),
        require_read_only=True,
        allow_prod=False
    )
    resolver = SQLConnectionResolver(registry=registry, policy=policy)
    with pytest.raises(SQLConnectionAbstractionContractError) as exc_info:
        resolver.resolve("staging_ref")
    assert "Environment" in str(exc_info.value) and "not allowed" in str(exc_info.value)


def test_resolver_returns_resolved_connection_without_raw_secret():
    endpoint = SQLConnectionEndpoint(host="dev-db", port=5432, database="devdb")
    secret_ref = SQLConnectionSecretRef(provider="gcp-secret-manager", key="pg-readonly-password")
    p = SQLConnectionProfile(
        connection_ref="pg_readonly",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        environment=SQLConnectionEnvironment.DEV,
        endpoint=endpoint,
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.SECRET_REF,
        secret_ref=secret_ref,
        max_rows=500,
        timeout_seconds=5.0
    )
    registry = SQLConnectionRegistry(profiles=(p,))
    policy = SQLConnectionPolicy(
        allowed_environments=(SQLConnectionEnvironment.DEV,),
        allowed_dialects=(SQLDatabaseDialect.POSTGRESQL,),
        require_read_only=True,
        allow_prod=False
    )
    resolver = SQLConnectionResolver(registry=registry, policy=policy)
    resolved = resolver.resolve("pg_readonly")
    
    assert isinstance(resolved, SQLResolvedConnection)
    assert resolved.version == "sql_connection_abstraction_v1"
    assert resolved.connection_ref == "pg_readonly"
    assert resolved.dialect == SQLDatabaseDialect.POSTGRESQL
    assert resolved.environment == SQLConnectionEnvironment.DEV
    assert resolved.endpoint == endpoint
    assert resolved.access_mode == SQLConnectionAccessMode.READ_ONLY
    assert resolved.auth_mode == SQLConnectionAuthMode.SECRET_REF
    assert resolved.secret_ref == secret_ref
    assert resolved.max_rows == 500
    assert resolved.timeout_seconds == 5.0
    
    # Assert that no raw secret fields (like raw values/passwords/tokens/auth_tokens) are present on resolved connection
    for field_name in resolved.__dict__:
        assert field_name not in ["password", "token", "secret", "value", "key_val", "raw_secret"]


def test_resolver_does_not_open_network_connection():
    # Verify that connection_abstraction.py does not contain database driver imports or network libraries
    from app.evaluation import connection_abstraction
    source_file = connection_abstraction.__file__
    with open(source_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    forbidden_modules = ["psycopg", "oracledb", "cx_Oracle", "sqlalchemy", "requests", "urllib", "http.client", "socket"]
    for mod in forbidden_modules:
        assert f"import {mod}" not in content, f"Forbidden import found: {mod}"
        assert f"from {mod}" not in content, f"Forbidden import found: {mod}"


def test_policy_normalizes_allowed_environment_strings():
    policy = SQLConnectionPolicy(
        allowed_environments=("dev", "local"),
        allowed_dialects=(SQLDatabaseDialect.SQLITE,)
    )
    assert SQLConnectionEnvironment.DEV in policy.allowed_environments
    assert SQLConnectionEnvironment.LOCAL in policy.allowed_environments
    for env in policy.allowed_environments:
        assert isinstance(env, SQLConnectionEnvironment)


def test_policy_normalizes_allowed_dialect_strings():
    policy = SQLConnectionPolicy(
        allowed_environments=(SQLConnectionEnvironment.DEV,),
        allowed_dialects=("sqlite", "postgresql")
    )
    assert SQLDatabaseDialect.SQLITE in policy.allowed_dialects
    assert SQLDatabaseDialect.POSTGRESQL in policy.allowed_dialects
    for dialect in policy.allowed_dialects:
        assert isinstance(dialect, SQLDatabaseDialect)


def test_resolver_accepts_normalized_string_policy_values():
    endpoint = SQLConnectionEndpoint(host="localhost", port=5432, database="db")
    p = SQLConnectionProfile(
        connection_ref="pg_ref",
        dialect=SQLDatabaseDialect.POSTGRESQL,
        environment=SQLConnectionEnvironment.DEV,
        endpoint=endpoint,
        access_mode=SQLConnectionAccessMode.READ_ONLY,
        auth_mode=SQLConnectionAuthMode.NONE,
        secret_ref=None
    )
    registry = SQLConnectionRegistry(profiles=(p,))
    policy = SQLConnectionPolicy(
        allowed_environments=("dev", "local"),
        allowed_dialects=("postgresql", "sqlite"),
        require_read_only=True,
        allow_prod=False
    )
    resolver = SQLConnectionResolver(registry=registry, policy=policy)
    resolved = resolver.resolve("pg_ref")
    assert resolved.connection_ref == "pg_ref"


def test_policy_default_rejects_prod():
    policy = SQLConnectionPolicy()
    assert SQLConnectionEnvironment.PROD not in policy.allowed_environments
    assert policy.allow_prod is False
    assert policy.require_read_only is True


def test_secret_ref_rejects_potential_raw_secret_keys():
    # Long key
    with pytest.raises(SQLConnectionAbstractionContractError):
        SQLConnectionSecretRef(provider="vault", key="a" * 101)

    # Whitespace key
    with pytest.raises(SQLConnectionAbstractionContractError):
        SQLConnectionSecretRef(provider="vault", key="my password")

    # URL key/provider
    with pytest.raises(SQLConnectionAbstractionContractError):
        SQLConnectionSecretRef(provider="vault", key="mysql://user:pass@host/db")
    with pytest.raises(SQLConnectionAbstractionContractError):
        SQLConnectionSecretRef(provider="http://vault", key="mykey")

    # Assignment patterns
    with pytest.raises(SQLConnectionAbstractionContractError):
        SQLConnectionSecretRef(provider="vault", key="password=abc")
    with pytest.raises(SQLConnectionAbstractionContractError):
        SQLConnectionSecretRef(provider="vault", key="token=123")
    with pytest.raises(SQLConnectionAbstractionContractError):
        SQLConnectionSecretRef(provider="vault", key="my-secret=xyz")


def test_registry_rejects_empty_connection_ref_lookup():
    registry = SQLConnectionRegistry(profiles=())
    with pytest.raises(SQLConnectionAbstractionContractError):
        registry.get_profile("")
    with pytest.raises(SQLConnectionAbstractionContractError):
        registry.get_profile("   ")

