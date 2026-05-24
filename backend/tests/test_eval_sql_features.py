from app.eval.sql_features import extract_sql_features

def test_extracts_join_feature():
    sql = "SELECT * FROM users JOIN orders ON users.id = orders.user_id"
    features = extract_sql_features(sql)
    assert "join" in features

def test_extracts_where_feature():
    sql = "SELECT * FROM users WHERE age > 18"
    features = extract_sql_features(sql)
    assert "where" in features

def test_extracts_group_by_feature():
    sql = "SELECT role, COUNT(*) FROM users GROUP BY role"
    features = extract_sql_features(sql)
    assert "group_by" in features

def test_extracts_order_by_feature():
    sql = "SELECT * FROM users ORDER BY created_at DESC"
    features = extract_sql_features(sql)
    assert "order_by" in features

def test_extracts_limit_feature():
    sql = "SELECT * FROM users LIMIT 10"
    features = extract_sql_features(sql)
    assert "limit" in features

def test_extracts_count_aggregation_feature():
    sql = "SELECT COUNT(id) FROM users"
    features = extract_sql_features(sql)
    assert "aggregation" in features

def test_extracts_sum_aggregation_feature():
    sql = "SELECT SUM(amount) FROM orders"
    features = extract_sql_features(sql)
    assert "aggregation" in features

def test_returns_empty_set_for_invalid_sql():
    sql = "SELECT FROM WHERE JOIN"
    features = extract_sql_features(sql)
    assert features == set()

def test_returns_empty_set_for_empty_sql():
    features = extract_sql_features("")
    assert features == set()
    
    features = extract_sql_features(None)
    assert features == set()
