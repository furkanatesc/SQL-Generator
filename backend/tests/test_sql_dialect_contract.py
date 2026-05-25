import pytest

from app.sql_dialects import (
    DEFAULT_SQL_DIALECT,
    UnsupportedSQLDialectError,
    normalize_sql_dialect,
)


def test_default_sql_dialect_is_postgres():
    assert DEFAULT_SQL_DIALECT == "postgres"


def test_normalize_sql_dialect_accepts_supported_dialects():
    assert normalize_sql_dialect("postgres") == "postgres"
    assert normalize_sql_dialect("Postgres") == "postgres"
    assert normalize_sql_dialect(" oracle ") == "oracle"


def test_normalize_sql_dialect_uses_default_for_none():
    assert normalize_sql_dialect(None) == "postgres"


def test_normalize_sql_dialect_rejects_unsupported_dialect():
    with pytest.raises(UnsupportedSQLDialectError):
        normalize_sql_dialect("snowflake")
