import os
import json
from pathlib import Path
from app.main import app

_CONTRACTS_DIR = Path(__file__).resolve().parent / "contracts"
_HTTP_VERBS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}


def _snapshot_api_routes() -> set:
    """OpenAPI snapshot'indaki (METHOD_UPPER, path) ciftleri — tek kaynak."""
    snap = json.loads((_CONTRACTS_DIR / "openapi_snapshot.json").read_text(encoding="utf-8"))
    return {(method.upper(), path)
            for path, item in snap["paths"].items()
            for method in item if method in _HTTP_VERBS}


# OpenAPI paths'te yer almayan framework/doc route'lari (Starlette/FastAPI otomatik).
# Yeni bir uygulama endpoint'i BURAYA girmez; yalnizca framework route'lari.
FRAMEWORK_ROUTES = {
    ("GET", "/openapi.json"), ("HEAD", "/openapi.json"),
    ("GET", "/docs"), ("HEAD", "/docs"),
    ("GET", "/docs/oauth2-redirect"), ("HEAD", "/docs/oauth2-redirect"),
    ("GET", "/redoc"), ("HEAD", "/redoc"),
}

def test_public_api_surface():
    # Discover routes at runtime including HTTP methods
    discovered_routes = set()
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        for method in methods:
            discovered_routes.add((method.upper(), route.path))

    # Expected routes: OpenAPI snapshot'indan turetilir + framework route'lari (tek kaynak)
    expected_routes = _snapshot_api_routes() | FRAMEWORK_ROUTES

    # Verify exact match (no endpoints/methods added or removed)
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
