import sqlglot


def normalize_sql(sql: str, *, dialect: str = "postgres") -> str:
    if not isinstance(sql, str) or not sql.strip():
        return ""

    cleaned = sql.strip().rstrip(";").strip()

    try:
        # Standardize using sqlglot AST normalization
        tree = sqlglot.parse_one(cleaned, read=dialect)
        return tree.sql(dialect=dialect, pretty=False)
    except Exception:
        # Fallback to deterministic whitespace normalization in case of parsing failures
        return " ".join(cleaned.split())


def sql_equivalent(actual_sql: str, expected_sql: str, *, dialect: str = "postgres") -> bool:
    return normalize_sql(actual_sql, dialect=dialect) == normalize_sql(expected_sql, dialect=dialect)
