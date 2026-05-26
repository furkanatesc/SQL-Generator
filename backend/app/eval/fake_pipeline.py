from app.trace.models import NL2SQLTrace
from app.eval.trace_recorder import RecordingTraceStore

FAKE_SQL_BY_CASE_ID = {
    "smoke_list_customers": "SELECT * FROM customers",
    "golden_select_user_names": "SELECT name FROM users",
    "golden_select_active_users": "SELECT id, name FROM users WHERE status = 'active'",
    "golden_count_orders": "SELECT COUNT(*) FROM orders",
    "golden_join_orders_customers": "SELECT orders.id, customers.name FROM orders JOIN customers ON orders.customer_id = customers.id",
    "golden_group_orders_by_status": "SELECT status, COUNT(*) FROM orders GROUP BY status",
    "golden_top_customers_by_created_at": "SELECT id, name FROM customers ORDER BY created_at DESC LIMIT 10",
}

FAKE_SELECTED_TABLES_BY_CASE_ID = {
    "smoke_list_customers": ["CUSTOMERS"],
    "golden_select_user_names": ["USERS"],
    "golden_select_active_users": ["USERS"],
    "golden_count_orders": ["ORDERS"],
    "golden_join_orders_customers": ["ORDERS", "CUSTOMERS"],
    "golden_group_orders_by_status": ["ORDERS"],
    "golden_top_customers_by_created_at": ["CUSTOMERS"],
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
