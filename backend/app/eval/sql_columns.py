import sqlglot
from sqlglot import exp

def extract_sql_columns(sql: str, *, dialect: str = "postgres") -> set[str]:
    """
    Extracts column references from the given SQL query using sqlglot.
    Normalizes column references to upper-case simple names and qualified names.
    If parsing fails, returns an empty set.
    """
    if not sql or not sql.strip():
        return set()

    try:
        parsed = sqlglot.parse_one(sql, read=dialect)
    except Exception:
        return set()

    columns = set()
    for col in parsed.find_all(exp.Column):
        col_name = col.name.upper()
        # Clean any quotes from the identifier if present
        col_name = col_name.replace('"', '').replace("'", "").replace("`", "")
        columns.add(col_name)
        if col.table:
            table_name = col.table.upper().replace('"', '').replace("'", "").replace("`", "")
            columns.add(f"{table_name}.{col_name}")

    return columns
