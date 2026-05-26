from app.eval.models import GoldenCase

GOLDEN_CASES = [
    GoldenCase(
        case_id="golden_count_orders",
        natural_query="How many orders are there?",
        expected_tables=["ORDERS"],
        required_sql_features=["aggregation"],
        expected_type="success",
        expected_sql="SELECT COUNT(*) FROM orders"
    ),
    GoldenCase(
        case_id="golden_group_orders_by_status",
        natural_query="Count orders by status",
        expected_tables=["ORDERS"],
        required_sql_features=["aggregation", "group_by"],
        expected_type="success",
        expected_sql="SELECT status, COUNT(*) FROM orders GROUP BY status"
    ),
    GoldenCase(
        case_id="golden_join_orders_customers",
        natural_query="List orders with customer names",
        expected_tables=["ORDERS", "CUSTOMERS"],
        required_sql_features=["join"],
        expected_type="success",
        expected_sql="SELECT orders.id, customers.name FROM orders JOIN customers ON orders.customer_id = customers.id"
    ),
    GoldenCase(
        case_id="golden_select_active_users",
        natural_query="List active users",
        expected_tables=["USERS"],
        required_sql_features=["where"],
        expected_type="success",
        expected_sql="SELECT id, name FROM users WHERE status = 'active'"
    ),
    GoldenCase(
        case_id="golden_select_user_names",
        natural_query="List all user names",
        expected_tables=["USERS"],
        required_sql_features=[],
        expected_type="success",
        expected_sql="SELECT name FROM users"
    ),
    GoldenCase(
        case_id="golden_top_customers_by_created_at",
        natural_query="Show the 10 newest customers",
        expected_tables=["CUSTOMERS"],
        required_sql_features=["order_by", "limit"],
        expected_type="success",
        expected_sql="SELECT id, name FROM customers ORDER BY created_at DESC LIMIT 10"
    ),
]
