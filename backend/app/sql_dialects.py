SUPPORTED_SQL_DIALECTS = {
    "postgres",
    "oracle",
}

DEFAULT_SQL_DIALECT = "postgres"


class UnsupportedSQLDialectError(ValueError):
    pass


def normalize_sql_dialect(dialect: str | None) -> str:
    normalized = (dialect or DEFAULT_SQL_DIALECT).strip().lower()

    if normalized not in SUPPORTED_SQL_DIALECTS:
        valid = ", ".join(sorted(SUPPORTED_SQL_DIALECTS))
        raise UnsupportedSQLDialectError(
            f"Unsupported SQL dialect '{dialect}'. Supported dialects: {valid}"
        )

    return normalized
