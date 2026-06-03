import os
import sys
import json

# Ensure backend directory is in python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app

def generate_snapshots():
    backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    contracts_dir = os.path.join(backend_root, "tests", "contracts")
    os.makedirs(contracts_dir, exist_ok=True)
    
    # 1. Regenerate openapi_snapshot.json
    openapi_path = os.path.join(contracts_dir, "openapi_snapshot.json")
    openapi_data = app.openapi()
    with open(openapi_path, "w", encoding="utf-8") as f:
        json.dump(openapi_data, f, indent=2, sort_keys=True, ensure_ascii=False)
    print(f"Generated deterministic OpenAPI snapshot at: {openapi_path}")

    # 2. Regenerate schema_contract_snapshot.json
    schema_path = os.path.join(contracts_dir, "schema_contract_snapshot.json")
    schemas = openapi_data.get("components", {}).get("schemas", {})
    schema_snapshot = {}
    for k, v in schemas.items():
        schema_snapshot[k] = {
            "required": sorted(v.get("required", [])),
            "properties": sorted(list(v.get("properties", {}).keys()))
        }
    with open(schema_path, "w", encoding="utf-8") as f:
        json.dump(schema_snapshot, f, indent=2, sort_keys=True, ensure_ascii=False)
    print(f"Generated deterministic Schema contract snapshot at: {schema_path}")

    # 3. Regenerate status_contract_snapshot.json
    status_path = os.path.join(contracts_dir, "status_contract_snapshot.json")
    # Define standard HTTP status semantics contract
    status_snapshot = {
        "missing_api_key": 403,
        "invalid_api_key": 403,
        "missing_resource": 404,
        "validation_error": 422,
        "health": 200
    }
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump(status_snapshot, f, indent=2, sort_keys=True, ensure_ascii=False)
    print(f"Generated deterministic Status contract snapshot at: {status_path}")

if __name__ == "__main__":
    generate_snapshots()
