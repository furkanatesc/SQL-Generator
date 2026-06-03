import os
import json
from app.main import app

def test_response_schema_contract():
    # Resolve the path to the schema contract snapshot
    snapshot_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "contracts",
        "schema_contract_snapshot.json"
    )
    
    assert os.path.exists(snapshot_path), f"Schema contract snapshot file not found at: {snapshot_path}"
    
    with open(snapshot_path, "r", encoding="utf-8") as f:
        snapshot_schemas = json.load(f)
        
    runtime_openapi = app.openapi()
    runtime_schemas = runtime_openapi.get("components", {}).get("schemas", {})
    
    # 1. Verify critical error and success models are defined
    critical_models = [
        "ErrorResponse",
        "ValidationError",
        "HTTPValidationError",
        "JobEnvelopeResponse",
        "JobDetailResponse",
        "HealthResponse",
        "ConfigResponse"
    ]
    for model_name in critical_models:
        assert model_name in snapshot_schemas, f"Critical model '{model_name}' is missing from the contract snapshot."
        assert model_name in runtime_schemas, f"Critical model '{model_name}' is missing from the runtime OpenAPI schema."

    # 2. Verify all snapshot schemas exist and match in required fields and property names
    for schema_name, snapshot_data in snapshot_schemas.items():
        assert schema_name in runtime_schemas, f"Schema '{schema_name}' has been removed in runtime OpenAPI definition."
        
        runtime_data = runtime_schemas[schema_name]
        
        snapshot_required = set(snapshot_data.get("required", []))
        runtime_required = set(runtime_data.get("required", []))
        
        snapshot_properties = set(snapshot_data.get("properties", []))
        runtime_properties = set(runtime_data.get("properties", {}).keys())
        
        # Verify required fields
        assert runtime_required == snapshot_required, (
            f"Schema '{schema_name}' required fields drift detected!\n"
            f"Expected: {snapshot_required}\n"
            f"Got: {runtime_required}"
        )
        
        # Verify properties
        assert runtime_properties == snapshot_properties, (
            f"Schema '{schema_name}' properties drift detected!\n"
            f"Expected: {snapshot_properties}\n"
            f"Got: {runtime_properties}"
        )
