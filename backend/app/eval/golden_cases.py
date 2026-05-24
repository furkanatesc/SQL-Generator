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
        case_id="customer_orders",
        natural_query="Show orders with customer names",
        expected_tables=["CUSTOMERS", "ORDERS"],
        required_sql_fragments=["JOIN"],
        forbidden_sql_fragments=["DELETE", "DROP", "UPDATE", "INSERT"],
    ),
    GoldenCase(
        case_id="count_products",
        natural_query="How many products are there?",
        expected_tables=["PRODUCTS"],
        required_sql_fragments=["COUNT"],
        forbidden_sql_fragments=["DELETE", "DROP", "UPDATE", "INSERT"],
    ),
    GoldenCase(
        case_id="total_sales",
        natural_query="What is the total sales amount?",
        expected_tables=["ORDERS"],
        required_sql_fragments=["SUM"],
        forbidden_sql_fragments=["DELETE", "DROP", "UPDATE", "INSERT"],
    ),
    GoldenCase(
        case_id="recent_orders",
        natural_query="Show orders from the last 30 days",
        expected_tables=["ORDERS"],
        required_sql_fragments=["WHERE"],
        forbidden_sql_fragments=["DELETE", "DROP", "UPDATE", "INSERT"],
    ),
]
