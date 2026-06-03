import os
import json
from app.main import app

def test_public_api_surface():
    # Discover routes at runtime
    discovered_routes = {route.path for route in app.routes}
    
    # Expected routes snapshot (source of truth inventory)
    expected_routes = {
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
        "/api/debug/traces",
        "/api/debug/traces/{trace_id}",
        "/health",
        "/api/configs/{key}",
        "/api/files/upload",
        "/api/jobs/without-file",
        "/api/jobs",
        "/api/jobs/{job_id}",
        "/api/jobs/{job_id}/stream",
        "/api/jobs/{job_id}/cancel",
        "/api/schema/raw",
        "/api/schema",
        "/api/schema/refresh",
        "/api/schema/custom-relations",
        "/api/schema/disabled-relations",
        "/api/schema/filters",
        "/api/rag/stats",
        "/api/rag/search",
        "/api/rag/index/business-rule",
        "/api/rag/index/sql-history"
    }
    
    # Verify exact match (no endpoints added or removed)
    assert discovered_routes == expected_routes, (
        f"API Surface Mismatch!\n"
        f"Unexpected routes in runtime: {discovered_routes - expected_routes}\n"
        f"Missing expected routes in runtime: {expected_routes - discovered_routes}"
    )

def test_openapi_snapshot_matches_contract():
    # Resolve the path to the OpenAPI snapshot
    snapshot_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "contracts",
        "openapi_snapshot.json"
    )
    
    assert os.path.exists(snapshot_path), f"OpenAPI snapshot file not found at: {snapshot_path}"
    
    with open(snapshot_path, "r", encoding="utf-8") as f:
        snapshot_schema = json.load(f)
        
    runtime_schema = app.openapi()
    
    # Helper to extract (path, method) -> operation_id mappings
    def extract_inventory(schema: dict) -> dict:
        inventory = {}
        paths = schema.get("paths", {})
        for path, path_item in paths.items():
            for method, operation in path_item.items():
                if method.lower() not in {"get", "post", "put", "delete", "options", "head", "patch", "trace"}:
                    continue
                operation_id = operation.get("operationId")
                inventory[(path, method.lower())] = operation_id
        return inventory

    snapshot_inventory = extract_inventory(snapshot_schema)
    runtime_inventory = extract_inventory(runtime_schema)
    
    # Assert exact match of paths, methods, and operation IDs
    assert runtime_inventory == snapshot_inventory, (
        f"API OpenAPI contract mismatch!\n"
        f"Added in runtime: {runtime_inventory.keys() - snapshot_inventory.keys()}\n"
        f"Removed in runtime: {snapshot_inventory.keys() - runtime_inventory.keys()}\n"
        f"Mismatched operationIds: "
        f"{ {k: (runtime_inventory[k], snapshot_inventory[k]) for k in runtime_inventory.keys() & snapshot_inventory.keys() if runtime_inventory[k] != snapshot_inventory[k]} }"
    )
