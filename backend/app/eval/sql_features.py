import sqlglot
from sqlglot import exp

def extract_sql_features(sql: str) -> set[str]:
    if not sql:
        return set()

    try:
        parsed = sqlglot.parse_one(sql)
    except Exception:
        return set()

    features = set()

    if list(parsed.find_all(exp.Join)):
        features.add("join")

    if list(parsed.find_all(exp.Where)):
        features.add("where")

    if list(parsed.find_all(exp.Group)):
        features.add("group_by")

    if list(parsed.find_all(exp.Order)):
        features.add("order_by")

    if list(parsed.find_all(exp.Limit)):
        features.add("limit")

    if any(func.key.upper() in {"COUNT", "SUM", "AVG", "MIN", "MAX"} for func in parsed.find_all(exp.AggFunc)):
        features.add("aggregation")

    return features
