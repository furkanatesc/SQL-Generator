from app.trace.models import NL2SQLTrace
from app.eval.trace_recorder import RecordingTraceStore

FAKE_SQL_BY_CASE_ID = {
    "smoke_list_customers": "SELECT * FROM customers",
    "list_customers": "SELECT * FROM customers",
    "customer_orders_join": """
        SELECT customers.name, orders.id
        FROM customers
        JOIN orders ON customers.id = orders.customer_id
    """,
    "orders_count_by_customer": """
        SELECT customers.id, COUNT(orders.id) AS order_count
        FROM customers
        JOIN orders ON customers.id = orders.customer_id
        GROUP BY customers.id
    """,
    "total_sales": """
        SELECT SUM(amount) AS total_sales
        FROM orders
    """,
    "recent_orders_filter": """
        SELECT *
        FROM orders
        WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
    """,
    "top_products_by_sales": """
        SELECT products.id, SUM(order_items.amount) AS total_sales
        FROM products
        JOIN order_items ON products.id = order_items.product_id
        GROUP BY products.id
        ORDER BY total_sales DESC
        LIMIT 10
    """,
    "active_users": """
        SELECT *
        FROM users
        WHERE active = TRUE
    """,
    "average_order_value": """
        SELECT AVG(amount) AS average_order_value
        FROM orders
    """,
    "customers_without_orders": """
        SELECT customers.*
        FROM customers
        LEFT JOIN orders ON customers.id = orders.customer_id
        WHERE orders.id IS NULL
    """,
    "sales_by_category": """
        SELECT products.category, SUM(order_items.amount) AS total_sales
        FROM products
        JOIN order_items ON products.id = order_items.product_id
        GROUP BY products.category
    """,
}

FAKE_SELECTED_TABLES_BY_CASE_ID = {
    "smoke_list_customers": ["CUSTOMERS"],
    "list_customers": ["CUSTOMERS"],
    "customer_orders_join": ["CUSTOMERS", "ORDERS"],
    "orders_count_by_customer": ["CUSTOMERS", "ORDERS"],
    "total_sales": ["ORDERS"],
    "recent_orders_filter": ["ORDERS"],
    "top_products_by_sales": ["PRODUCTS", "ORDER_ITEMS"],
    "active_users": ["USERS"],
    "average_order_value": ["ORDERS"],
    "customers_without_orders": ["CUSTOMERS", "ORDERS"],
    "sales_by_category": ["PRODUCTS", "ORDER_ITEMS"],
}

class DeterministicFakePipeline:
    def __init__(self, store: RecordingTraceStore):
        self.store = store

    def run_pipeline(self, *, natural_query: str, job_id: str, **kwargs):
        case_id = job_id.removeprefix("eval:")
        
        sql = FAKE_SQL_BY_CASE_ID.get(case_id)
        if sql is None:
            raise KeyError(f"No deterministic fake SQL configured for eval case: {case_id}")
            
        tables = FAKE_SELECTED_TABLES_BY_CASE_ID.get(case_id)
        if tables is None:
            raise KeyError(f"No deterministic fake tables configured for eval case: {case_id}")

        self.store.save(
            NL2SQLTrace(
                raw_query=natural_query,
                sql_valid=True,
                selected_tables=tables,
                generated_sql=sql,
            )
        )
