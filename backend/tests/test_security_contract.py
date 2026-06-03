import re
import json
from fastapi.testclient import TestClient
from app.main import app

def test_public_endpoint_allowlist():
    client = TestClient(app)
    from app.auth import verify_api_key
    
    # Intentionally public endpoints allowlist
    allowlist = {
        ("GET", "/health"),
        ("GET", "/openapi.json"),
        ("HEAD", "/openapi.json"),
        ("GET", "/docs"),
        ("HEAD", "/docs"),
        ("GET", "/redoc"),
        ("HEAD", "/redoc"),
        ("GET", "/docs/oauth2-redirect"),
        ("HEAD", "/docs/oauth2-redirect"),
    }
    
    # Helper to check if a route requires verify_api_key dependency
    def requires_auth(route) -> bool:
        # Check route-level dependencies safely
        dependencies = getattr(route, "dependencies", [])
        for dep in dependencies:
            if dep.dependency == verify_api_key:
                return True
        # Check function-level dependencies recursively safely
        dependant = getattr(route, "dependant", None)
        if dependant:
            def check_dependant(depant):
                if depant.call == verify_api_key:
                    return True
                for sub_dep in depant.dependencies:
                    if check_dependant(sub_dep):
                        return True
                return False
            if check_dependant(dependant):
                return True
        return False

    # Extract all public routes discovered at runtime
    runtime_public_routes = set()
    for route in app.routes:
        if not requires_auth(route):
            methods = getattr(route, "methods", None) or set()
            for method in methods:
                runtime_public_routes.add((method.upper(), route.path))

    # Assert exact match of the allowlist with runtime public routes
    assert runtime_public_routes == allowlist, (
        f"Public Endpoint Allowlist Mismatch!\n"
        f"Unexpected public routes in runtime: {runtime_public_routes - allowlist}\n"
        f"Missing expected public routes in runtime: {allowlist - runtime_public_routes}"
    )

    # Verify allowlisted endpoints are reachable without API key
    for method, path in allowlist:
        response = client.request(method, path)
        # Ensure it does not return a 403 Forbidden due to authentication
        if response.status_code == 403:
            assert "Could not validate credentials" not in response.text

def test_protected_endpoints_require_api_key():
    client = TestClient(app)
    
    # Intentionally public endpoints allowlist
    allowlist = {
        ("GET", "/health"),
        ("GET", "/openapi.json"),
        ("GET", "/docs"),
        ("GET", "/redoc"),
        ("GET", "/docs/oauth2-redirect"),
    }
    
    # Verify all non-allowlisted /api/* endpoints enforce API key protection
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        for method in methods:
            if method.upper() == "HEAD":
                continue
                
            route_key = (method.upper(), route.path)
            if route_key in allowlist:
                continue
                
            # Focus on protected paths
            if route.path.startswith("/api/"):
                # Replace dynamic path params with a dummy test ID
                test_path = re.sub(r"\{[^}]+\}", "test-id", route.path)
                
                response = client.request(method, test_path)
                assert response.status_code == 403, f"Route {route_key} did not return 403 without API Key."
                
                data = response.json()
                assert "error" in data, f"Route {route_key} missing standard ErrorResponse envelope."
                assert data["error"]["code"] == "FORBIDDEN"
                assert "Could not validate credentials" in data["error"]["message"]

def test_debug_trace_endpoints_require_api_key():
    client = TestClient(app)
    
    # Verify GET /api/debug/traces
    res1 = client.get("/api/debug/traces")
    assert res1.status_code == 403
    assert "Could not validate credentials" in res1.json()["error"]["message"]
    
    # Verify GET /api/debug/traces/{trace_id}
    res2 = client.get("/api/debug/traces/dummy-trace-id")
    assert res2.status_code == 403
    assert "Could not validate credentials" in res2.json()["error"]["message"]

def test_missing_api_key_response_contract():
    client = TestClient(app)
    
    res = client.get("/api/jobs")
    assert res.status_code == 403
    
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == "FORBIDDEN"
    assert data["error"]["message"] == "Could not validate credentials. Missing API Key."
    assert data["error"]["details"] is None

def test_invalid_api_key_response_contract():
    client = TestClient(app)
    invalid_token = "invalid_secret_key_123"
    
    # Test via Header X-API-Key
    res_header = client.get("/api/jobs", headers={"X-API-Key": invalid_token})
    assert res_header.status_code == 403
    data_h = res_header.json()
    assert data_h["error"]["code"] == "FORBIDDEN"
    assert data_h["error"]["message"] == "Could not validate credentials. Invalid API Key."
    assert data_h["error"]["details"] is None
    # Ensure raw secret is not echoed back
    assert invalid_token not in json.dumps(data_h)
    
    # Test via query parameter api_key
    res_query = client.get("/api/jobs", params={"api_key": invalid_token})
    assert res_query.status_code == 403
    data_q = res_query.json()
    assert data_q["error"]["code"] == "FORBIDDEN"
    assert data_q["error"]["message"] == "Could not validate credentials. Invalid API Key."
    assert data_q["error"]["details"] is None
    # Ensure raw secret is not echoed back
    assert invalid_token not in json.dumps(data_q)
