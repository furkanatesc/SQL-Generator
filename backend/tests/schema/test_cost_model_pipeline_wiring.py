import json
from app.schema.table_selection_cost import from_config


def test_from_config_roundtrip_used_by_pipeline_key(monkeypatch):
    # The pipeline reads config key "table_selection_cost_model" via get_config
    raw = json.dumps({"cost_budget": 42.0})
    model = from_config(raw)
    assert model.cost_budget == 42.0
