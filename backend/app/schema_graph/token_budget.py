from typing import Dict, Any

class TokenBudgetEstimator:
    def estimate_table_cost(self, table_name: str, table_meta: Dict[str, Any]) -> int:
        base = 8
        columns = len(table_meta.get("columns", [])) * 3
        fks = len(table_meta.get("foreign_keys", [])) * 4
        return base + columns + fks

    def can_add(self, current_cost: int, table_cost: int, budget: int) -> bool:
        return current_cost + table_cost <= budget
