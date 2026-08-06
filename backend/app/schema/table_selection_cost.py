"""Table selection cost model — PURE (Sprint 28.3).

Named relevance weights + a per-table cost function for benefit-vs-cost
budget selection. Injected into select_schema_context (no I/O here).
from_config tolerantly parses the configs 'table_selection_cost_model' JSON
(27.8 llm_pricing pattern): invalid/missing -> DEFAULT_COST_MODEL.
"""
import json
from pydantic import BaseModel, ConfigDict

_KNOWN_FIELDS = {
    "exact_table", "singular_plural_table", "table_token_overlap",
    "exact_column", "column_token_overlap", "explicit_neighbor", "implicit_neighbor",
    "w_base", "w_col", "w_fk", "cost_budget",
}


class TableSelectionCostModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    exact_table: float = 100.0
    singular_plural_table: float = 60.0
    table_token_overlap: float = 40.0
    exact_column: float = 80.0
    column_token_overlap: float = 30.0
    explicit_neighbor: float = 20.0
    implicit_neighbor: float = 10.0
    w_base: float = 1.0
    w_col: float = 1.0
    w_fk: float = 0.0
    # Calibrated on the golden schema (Sprint 28.3 Task 4): measured max total_cost
    # across all golden cases = 25.0 (unknown_question_uses_bounded_fallback, the
    # widest case). 30.0 = ~1.2x that max, rounded to a clean number — comfortably
    # above so the budget never binds on golden (all cases: budget_exhausted=False).
    # max_tables remains the effective cap for selection size; this budget is a
    # conservative backstop, not the primary limiter.
    cost_budget: float = 30.0


DEFAULT_COST_MODEL = TableSelectionCostModel()


def table_cost(n_columns: int, n_fks: int, model: TableSelectionCostModel) -> float:
    return model.w_base + model.w_col * n_columns + model.w_fk * n_fks


def fk_counts(schema) -> dict:
    """FK-owner (source_table) relationship count per table — deterministic."""
    counts: dict = {}
    for rel in schema.relationships:
        counts[rel.source_table] = counts.get(rel.source_table, 0) + 1
    return counts


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def from_config(raw) -> TableSelectionCostModel:
    if not raw:
        return DEFAULT_COST_MODEL
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return DEFAULT_COST_MODEL
    if not isinstance(data, dict):
        return DEFAULT_COST_MODEL
    overrides = {k: float(v) for k, v in data.items()
                 if k in _KNOWN_FIELDS and _is_number(v)}
    return TableSelectionCostModel(**overrides)
