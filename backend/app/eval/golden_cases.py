from app.eval.models import GoldenCase

GOLDEN_CASES = [
    GoldenCase(
        case_id="list_customers",
        natural_query="List all customers",
        expected_tables=["CUSTOMERS"],
        required_sql_fragments=["SELECT", "FROM"],
        forbidden_sql_fragments=["DELETE", "DROP", "UPDATE", "INSERT"],
    ),
    GoldenCase(
        case_id="customer_orders_join",
        natural_query="Show orders with customer names",
        expected_tables=["CUSTOMERS", "ORDERS"],
        required_sql_features=["join"],
        forbidden_sql_fragments=["DELETE", "DROP", "UPDATE", "INSERT"],
    ),
    GoldenCase(
        case_id="orders_count_by_customer",
        natural_query="Show number of orders per customer",
        expected_tables=["CUSTOMERS", "ORDERS"],
        required_sql_features=["join", "aggregation", "group_by"],
        forbidden_sql_fragments=["DELETE", "DROP", "UPDATE", "INSERT"],
    ),
    GoldenCase(
        case_id="total_sales",
        natural_query="What is the total sales amount?",
        expected_tables=["ORDERS"],
        required_sql_features=["aggregation"],
        forbidden_sql_fragments=["DELETE", "DROP", "UPDATE", "INSERT"],
    ),
    GoldenCase(
        case_id="recent_orders_filter",
        natural_query="Show orders from the last 30 days",
        expected_tables=["ORDERS"],
        required_sql_features=["where"],
        forbidden_sql_fragments=["DELETE", "DROP", "UPDATE", "INSERT"],
    ),
    GoldenCase(
        case_id="top_products_by_sales",
        natural_query="Show top 10 products by sales amount",
        expected_tables=["PRODUCTS", "ORDER_ITEMS"],
        required_sql_features=["join", "aggregation", "group_by", "order_by", "limit"],
        forbidden_sql_fragments=["DELETE", "DROP", "UPDATE", "INSERT"],
    ),
    GoldenCase(
        case_id="active_users",
        natural_query="List users who are active",
        expected_tables=["USERS"],
        required_sql_features=["where"],
        forbidden_sql_fragments=["DELETE", "DROP", "UPDATE", "INSERT"],
    ),
    GoldenCase(
        case_id="average_order_value",
        natural_query="What is the average order value?",
        expected_tables=["ORDERS"],
        required_sql_features=["aggregation"],
        forbidden_sql_fragments=["DELETE", "DROP", "UPDATE", "INSERT"],
    ),
    GoldenCase(
        case_id="customers_without_orders",
        natural_query="Show customers who haven't placed any orders",
        expected_tables=["CUSTOMERS", "ORDERS"],
        required_sql_features=["join", "where"],
        forbidden_sql_fragments=["DELETE", "DROP", "UPDATE", "INSERT"],
    ),
    GoldenCase(
        case_id="sales_by_category",
        natural_query="Show total sales by product category",
        expected_tables=["PRODUCTS", "ORDER_ITEMS"],
        required_sql_features=["join", "aggregation", "group_by"],
        forbidden_sql_fragments=["DELETE", "DROP", "UPDATE", "INSERT"],
    ),
]
