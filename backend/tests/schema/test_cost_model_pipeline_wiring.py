import json
from unittest.mock import MagicMock

from app.schema.table_selection_cost import from_config
import app.sql_pipeline as pipe
from app.sql_pipeline import SQLGenerationPipeline


def test_from_config_roundtrip_used_by_pipeline_key(monkeypatch):
    # The pipeline reads config key "table_selection_cost_model" via get_config
    raw = json.dumps({"cost_budget": 42.0})
    model = from_config(raw)
    assert model.cost_budget == 42.0


# --- Sprint 28.3.1 Task 5 (TECH-DEBT §12.17): end-to-end pipeline wiring ---
#
# The unit test above only proves from_config parses correctly in isolation.
# It does NOT prove the pipeline actually wires that model into
# select_schema_context and that the override changes the resulting
# selection. This test exercises the real seam: `_stage_retrieval` calls
# `_cost_model_from_config(get_config(TABLE_SELECTION_COST_MODEL_KEY))` and
# passes the result into `select_schema_context`.

def _mocked_pipeline():
    pipeline = SQLGenerationPipeline(
        schema_manager=MagicMock(),
        llm_provider=None,
        trace_store=None,
    )
    pipeline.schema_pruner = MagicMock()
    pipeline.schema_pruner.prune_schema.return_value = {
        "tables": {
            # Tokenizes to {"order", "items"} -> singularized {"order", "item"}.
            "order_items": {
                "columns": [
                    {"name": "id", "type": "int", "primary_key": True},
                    {"name": "order_id", "type": "int"},
                    {"name": "qty", "type": "int"},
                ],
                "foreign_keys": [],
            },
            # Tokenizes to {"invoice", "items"} -> singularized {"invoice", "item"}.
            "invoice_items": {
                "columns": [
                    {"name": "id", "type": "int", "primary_key": True},
                    {"name": "invoice_id", "type": "int"},
                ],
                "foreign_keys": [],
            },
        },
        "estimated_tokens": 10,
    }
    return pipeline


def test_wiring_end_to_end_config_override_changes_selection(monkeypatch):
    # Question "items" singularizes to {"item"}, which intersects BOTH
    # tables' singularized token sets -> both score via
    # singular_plural_table_match (60.0 each), neither is an
    # exact_table_match, so neither is force-included; both go through the
    # budget-gated `rest` path. Costs (w_base=1.0, w_col=1.0, w_fk=0.0):
    #   order_items:   1 + 3 columns = 4.0
    #   invoice_items: 1 + 2 columns = 3.0
    aqr = {"natural_query": "items"}

    # DEFAULT cost model: get_config returns None -> from_config falls back
    # to DEFAULT_COST_MODEL (cost_budget=30.0) -> both tables fit the budget.
    monkeypatch.setattr(pipe, "get_config", lambda key: None)
    pipeline = _mocked_pipeline()
    _, _, trace_default, error_default, _ = pipeline._stage_retrieval(
        aqr=aqr, natural_query="items", dialect="postgres", log_callback=None,
    )
    assert error_default is None
    assert set(trace_default["selected_tables"]) == {"order_items", "invoice_items"}

    # Overridden cost model via the config seam: a tiny cost_budget=3.5
    # excludes the more expensive order_items (cost 4.0) while still
    # affording the cheaper/denser invoice_items (cost 3.0).
    override_json = json.dumps({"cost_budget": 3.5})
    monkeypatch.setattr(
        pipe, "get_config",
        lambda key: override_json if key == pipe.TABLE_SELECTION_COST_MODEL_KEY else None,
    )
    pipeline = _mocked_pipeline()
    _, _, trace_override, error_override, _ = pipeline._stage_retrieval(
        aqr=aqr, natural_query="items", dialect="postgres", log_callback=None,
    )
    assert error_override is None
    assert trace_override["selected_tables"] == ["invoice_items"]

    # The observable, concrete effect of the config override: selection differs.
    assert trace_default["selected_tables"] != trace_override["selected_tables"]
    assert "order_items" in trace_default["selected_tables"]
    assert "order_items" not in trace_override["selected_tables"]
