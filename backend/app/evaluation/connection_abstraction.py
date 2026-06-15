from dataclasses import dataclass
from enum import Enum
from typing import Any, Tuple, Optional
from app.evaluation.multi_database_execution import SQLDatabaseDialect

SQL_CONNECTION_ABSTRACTION_VERSION = "sql_connection_abstraction_v1"


class SQLConnectionAbstractionContractError(ValueError):
    """Raised when database connection abstraction constraints or policy checks are violated."""
    pass


class SQLConnectionEnvironment(str, Enum):
    LOCAL = "local"
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class SQLConnectionAuthMode(str, Enum):
    SECRET_REF = "secret_ref"
    IAM = "iam"
    NONE = "none"


class SQLConnectionAccessMode(str, Enum):
    READ_ONLY = "read_only"


@dataclass(frozen=True)
class SQLConnectionSecretRef:
    provider: str
    key: str

    def __post_init__(self):
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise SQLConnectionAbstractionContractError("provider cannot be empty")
        if not isinstance(self.key, str) or not self.key.strip():
            raise SQLConnectionAbstractionContractError("key cannot be empty")


@dataclass(frozen=True)
class SQLConnectionEndpoint:
    host: str
    port: int
    database: str

    def __post_init__(self):
        if not isinstance(self.host, str) or not self.host.strip():
            raise SQLConnectionAbstractionContractError("host cannot be empty")
        if not isinstance(self.database, str) or not self.database.strip():
            raise SQLConnectionAbstractionContractError("database cannot be empty")

        if not isinstance(self.port, int) or isinstance(self.port, bool):
            raise SQLConnectionAbstractionContractError("port must be an integer")
        if not (1 <= self.port <= 65535):
            raise SQLConnectionAbstractionContractError("port must be between 1 and 65535")


def _validate_positive_number(val: Any, name: str, force_int: bool = False):
    if not isinstance(val, (int, float)) or isinstance(val, bool):
        raise SQLConnectionAbstractionContractError(f"{name} must be a number")
    if force_int and not isinstance(val, int):
        raise SQLConnectionAbstractionContractError(f"{name} must be an integer")
    if val <= 0:
        raise SQLConnectionAbstractionContractError(f"{name} must be greater than 0")


@dataclass(frozen=True)
class SQLConnectionProfile:
    connection_ref: str
    dialect: SQLDatabaseDialect
    environment: SQLConnectionEnvironment
    endpoint: SQLConnectionEndpoint
    access_mode: SQLConnectionAccessMode
    auth_mode: SQLConnectionAuthMode
    secret_ref: Optional[SQLConnectionSecretRef]
    max_rows: int = 1000
    timeout_seconds: float = 2.0

    def __post_init__(self):
        if not isinstance(self.connection_ref, str) or not self.connection_ref.strip():
            raise SQLConnectionAbstractionContractError("connection_ref cannot be empty")

        if not isinstance(self.dialect, SQLDatabaseDialect):
            try:
                object.__setattr__(self, "dialect", SQLDatabaseDialect(self.dialect))
            except ValueError:
                raise SQLConnectionAbstractionContractError(f"Invalid dialect: {self.dialect}")

        if not isinstance(self.environment, SQLConnectionEnvironment):
            try:
                object.__setattr__(self, "environment", SQLConnectionEnvironment(self.environment))
            except ValueError:
                raise SQLConnectionAbstractionContractError(f"Invalid environment: {self.environment}")

        if not isinstance(self.endpoint, SQLConnectionEndpoint):
            raise SQLConnectionAbstractionContractError("endpoint must be a SQLConnectionEndpoint instance")

        if not isinstance(self.access_mode, SQLConnectionAccessMode):
            try:
                object.__setattr__(self, "access_mode", SQLConnectionAccessMode(self.access_mode))
            except ValueError:
                raise SQLConnectionAbstractionContractError(f"Invalid access_mode: {self.access_mode}")

        if self.access_mode != SQLConnectionAccessMode.READ_ONLY:
            raise SQLConnectionAbstractionContractError("Access mode must be READ_ONLY")

        if not isinstance(self.auth_mode, SQLConnectionAuthMode):
            try:
                object.__setattr__(self, "auth_mode", SQLConnectionAuthMode(self.auth_mode))
            except ValueError:
                raise SQLConnectionAbstractionContractError(f"Invalid auth_mode: {self.auth_mode}")

        # Auth mode rules:
        if self.auth_mode == SQLConnectionAuthMode.SECRET_REF:
            if self.secret_ref is None:
                raise SQLConnectionAbstractionContractError("secret_ref is required when auth_mode is SECRET_REF")
            if not isinstance(self.secret_ref, SQLConnectionSecretRef):
                raise SQLConnectionAbstractionContractError("secret_ref must be a SQLConnectionSecretRef instance")
        elif self.auth_mode == SQLConnectionAuthMode.NONE:
            if self.secret_ref is not None:
                raise SQLConnectionAbstractionContractError("secret_ref must be None when auth_mode is NONE")
        elif self.auth_mode == SQLConnectionAuthMode.IAM:
            if self.secret_ref is not None and not isinstance(self.secret_ref, SQLConnectionSecretRef):
                raise SQLConnectionAbstractionContractError("secret_ref must be a SQLConnectionSecretRef instance or None")

        _validate_positive_number(self.max_rows, "max_rows", force_int=True)
        _validate_positive_number(self.timeout_seconds, "timeout_seconds")


@dataclass(frozen=True)
class SQLConnectionRegistry:
    profiles: Tuple[SQLConnectionProfile, ...]

    def __post_init__(self):
        if not isinstance(self.profiles, tuple):
            try:
                object.__setattr__(self, "profiles", tuple(self.profiles))
            except TypeError:
                raise SQLConnectionAbstractionContractError("profiles must be a tuple")

        seen = set()
        for p in self.profiles:
            if not isinstance(p, SQLConnectionProfile):
                raise SQLConnectionAbstractionContractError("Registry profiles must be instances of SQLConnectionProfile")
            if p.connection_ref in seen:
                raise SQLConnectionAbstractionContractError(f"Duplicate connection_ref: {p.connection_ref}")
            seen.add(p.connection_ref)

    def get_profile(self, connection_ref: str) -> SQLConnectionProfile:
        if not isinstance(connection_ref, str):
            raise SQLConnectionAbstractionContractError("connection_ref must be a string")

        for p in self.profiles:
            if p.connection_ref == connection_ref:
                return p

        raise SQLConnectionAbstractionContractError(f"Unknown connection_ref: '{connection_ref}'")


@dataclass(frozen=True)
class SQLConnectionPolicy:
    allowed_environments: Tuple[SQLConnectionEnvironment, ...]
    allowed_dialects: Tuple[SQLDatabaseDialect, ...]
    require_read_only: bool = True
    allow_prod: bool = False

    def __post_init__(self):
        if not isinstance(self.allowed_environments, tuple):
            try:
                object.__setattr__(self, "allowed_environments", tuple(self.allowed_environments))
            except TypeError:
                raise SQLConnectionAbstractionContractError("allowed_environments must be a tuple")

        # Validate allowed_environments items are enums
        for env in self.allowed_environments:
            if not isinstance(env, SQLConnectionEnvironment):
                try:
                    SQLConnectionEnvironment(env)
                except ValueError:
                    raise SQLConnectionAbstractionContractError(f"Invalid allowed environment: {env}")

        if not isinstance(self.allowed_dialects, tuple):
            try:
                object.__setattr__(self, "allowed_dialects", tuple(self.allowed_dialects))
            except TypeError:
                raise SQLConnectionAbstractionContractError("allowed_dialects must be a tuple")

        # Validate allowed_dialects items are enums
        for d in self.allowed_dialects:
            if not isinstance(d, SQLDatabaseDialect):
                try:
                    SQLDatabaseDialect(d)
                except ValueError:
                    raise SQLConnectionAbstractionContractError(f"Invalid allowed dialect: {d}")

        if not isinstance(self.require_read_only, bool):
            raise SQLConnectionAbstractionContractError("require_read_only must be a boolean")

        if not isinstance(self.allow_prod, bool):
            raise SQLConnectionAbstractionContractError("allow_prod must be a boolean")


@dataclass(frozen=True)
class SQLResolvedConnection:
    version: str
    connection_ref: str
    dialect: SQLDatabaseDialect
    environment: SQLConnectionEnvironment
    endpoint: SQLConnectionEndpoint
    access_mode: SQLConnectionAccessMode
    auth_mode: SQLConnectionAuthMode
    secret_ref: Optional[SQLConnectionSecretRef]
    max_rows: int
    timeout_seconds: float

    def __post_init__(self):
        if self.version != SQL_CONNECTION_ABSTRACTION_VERSION:
            raise SQLConnectionAbstractionContractError(f"Invalid connection abstraction version: {self.version}")

        if not isinstance(self.connection_ref, str) or not self.connection_ref.strip():
            raise SQLConnectionAbstractionContractError("connection_ref cannot be empty")

        if not isinstance(self.dialect, SQLDatabaseDialect):
            raise SQLConnectionAbstractionContractError("dialect must be a SQLDatabaseDialect")

        if not isinstance(self.environment, SQLConnectionEnvironment):
            raise SQLConnectionAbstractionContractError("environment must be a SQLConnectionEnvironment")

        if not isinstance(self.endpoint, SQLConnectionEndpoint):
            raise SQLConnectionAbstractionContractError("endpoint must be a SQLConnectionEndpoint")

        if not isinstance(self.access_mode, SQLConnectionAccessMode):
            raise SQLConnectionAbstractionContractError("access_mode must be a SQLConnectionAccessMode")

        if self.access_mode != SQLConnectionAccessMode.READ_ONLY:
            raise SQLConnectionAbstractionContractError("Access mode must be READ_ONLY")

        if not isinstance(self.auth_mode, SQLConnectionAuthMode):
            raise SQLConnectionAbstractionContractError("auth_mode must be a SQLConnectionAuthMode")

        if self.auth_mode == SQLConnectionAuthMode.SECRET_REF:
            if self.secret_ref is None:
                raise SQLConnectionAbstractionContractError("secret_ref is required when auth_mode is SECRET_REF")
            if not isinstance(self.secret_ref, SQLConnectionSecretRef):
                raise SQLConnectionAbstractionContractError("secret_ref must be a SQLConnectionSecretRef instance")
        elif self.auth_mode == SQLConnectionAuthMode.NONE:
            if self.secret_ref is not None:
                raise SQLConnectionAbstractionContractError("secret_ref must be None when auth_mode is NONE")
        elif self.auth_mode == SQLConnectionAuthMode.IAM:
            if self.secret_ref is not None and not isinstance(self.secret_ref, SQLConnectionSecretRef):
                raise SQLConnectionAbstractionContractError("secret_ref must be a SQLConnectionSecretRef instance or None")

        _validate_positive_number(self.max_rows, "max_rows", force_int=True)
        _validate_positive_number(self.timeout_seconds, "timeout_seconds")


@dataclass(frozen=True)
class SQLConnectionResolver:
    registry: SQLConnectionRegistry
    policy: SQLConnectionPolicy

    def __post_init__(self):
        if not isinstance(self.registry, SQLConnectionRegistry):
            raise SQLConnectionAbstractionContractError("registry must be a SQLConnectionRegistry instance")
        if not isinstance(self.policy, SQLConnectionPolicy):
            raise SQLConnectionAbstractionContractError("policy must be a SQLConnectionPolicy instance")

    def resolve(self, connection_ref: str) -> SQLResolvedConnection:
        profile = self.registry.get_profile(connection_ref)

        # Policy checks
        if profile.environment not in self.policy.allowed_environments:
            raise SQLConnectionAbstractionContractError(
                f"Environment '{profile.environment.value}' is not allowed by connection policy"
            )

        if profile.environment == SQLConnectionEnvironment.PROD and not self.policy.allow_prod:
            raise SQLConnectionAbstractionContractError(
                "Production environment database access is blocked by policy settings"
            )

        if profile.dialect not in self.policy.allowed_dialects:
            raise SQLConnectionAbstractionContractError(
                f"Dialect '{profile.dialect.value}' is not allowed by connection policy"
            )

        if self.policy.require_read_only and profile.access_mode != SQLConnectionAccessMode.READ_ONLY:
            raise SQLConnectionAbstractionContractError(
                "Read-only access is strictly required by policy settings"
            )

        return SQLResolvedConnection(
            version=SQL_CONNECTION_ABSTRACTION_VERSION,
            connection_ref=profile.connection_ref,
            dialect=profile.dialect,
            environment=profile.environment,
            endpoint=profile.endpoint,
            access_mode=profile.access_mode,
            auth_mode=profile.auth_mode,
            secret_ref=profile.secret_ref,
            max_rows=profile.max_rows,
            timeout_seconds=profile.timeout_seconds
        )
