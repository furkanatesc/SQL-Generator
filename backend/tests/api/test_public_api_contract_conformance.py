"""Public API contract conformance guard (Sprint 30.0).

Deterministic, Docker-free, marker-less -> runs in `backend-tests` every CI
run. Holds every /api/v1 route to the canonical contract. Legacy /api/* is
grandfathered (the existing tests/test_api_surface.py + openapi_snapshot.json
is the route-addition tripwire).
"""
from fastapi.testclient import TestClient
from fastapi.routing import APIRoute

from app.main import app
from app.api.contract import (
    API_V1_PREFIX, ApiResponse, contract_descriptor, REQUEST_ID_HEADER,
)

client = TestClient(app)

# The known-conforming public v1 surface. A new /api/v1 route MUST be added
# here (and made to conform) or this guard fails -> forces conformance review.
EXPECTED_V1_ROUTES = {
    ("GET", "/api/v1"),
    ("POST", "/api/v1/workspaces"),
    ("GET", "/api/v1/workspaces"),
    ("GET", "/api/v1/workspaces/{workspace_id}"),
    ("PATCH", "/api/v1/workspaces/{workspace_id}"),
    ("DELETE", "/api/v1/workspaces/{workspace_id}"),
    ("POST", "/api/v1/connections"),
    ("GET", "/api/v1/connections"),
    ("GET", "/api/v1/connections/{connection_id}"),
    ("PATCH", "/api/v1/connections/{connection_id}"),
    ("DELETE", "/api/v1/connections/{connection_id}"),
    ("POST", "/api/v1/schema-syncs"),
    ("GET", "/api/v1/schema-syncs"),
    ("GET", "/api/v1/schema-syncs/{sync_id}"),
    ("DELETE", "/api/v1/schema-syncs/{sync_id}"),
    ("POST", "/api/v1/query-runs"),
    ("GET", "/api/v1/query-runs"),
    ("GET", "/api/v1/query-runs/{run_id}"),
    ("DELETE", "/api/v1/query-runs/{run_id}"),
    ("GET", "/api/v1/query-history"),
    ("GET", "/api/v1/query-history/summary"),
    ("POST", "/api/v1/feedback"),
    ("GET", "/api/v1/feedback"),
    ("GET", "/api/v1/feedback/{feedback_id}"),
    ("DELETE", "/api/v1/feedback/{feedback_id}"),
    ("GET", "/api/v1/admin/overview"),
    ("GET", "/api/v1/admin/config"),
    ("POST", "/api/v1/api-keys"),
    ("GET", "/api/v1/api-keys"),
    ("GET", "/api/v1/api-keys/{key_id}"),
    ("POST", "/api/v1/api-keys/{key_id}/revoke"),
}


def _is_v1_path(path: str) -> bool:
    # Segment-boundary match so /api/v1beta and /api/v10 are NOT treated as v1.
    return path == API_V1_PREFIX or path.startswith(API_V1_PREFIX + "/")


def _v1_routes():
    found = set()
    for route in app.routes:
        if isinstance(route, APIRoute) and _is_v1_path(route.path):
            for method in route.methods - {"HEAD", "OPTIONS"}:
                found.add((method, route.path))
    return found


def test_v1_route_set_matches_known_conforming_allowlist():
    assert _v1_routes() == EXPECTED_V1_ROUTES


def _resolve_success_envelope_component(op, components, where):
    """Resolve a route operation's success (2xx) JSON response to its component
    schema, turning malformed/undeclared responses into clean assertion
    failures instead of KeyErrors."""
    responses = op.get("responses", {})
    success_codes = sorted(c for c in responses if c.startswith("2"))
    assert success_codes, f"{where}: no 2xx response declared"
    code = "200" if "200" in success_codes else success_codes[0]
    content = responses[code].get("content", {}).get("application/json", {})
    schema = content.get("schema")
    assert schema, f"{where}: 2xx response has no application/json schema (missing response_model?)"
    ref = schema.get("$ref")
    assert ref, f"{where}: 2xx schema is not a $ref to a canonical envelope model (got {schema!r})"
    name = ref.split("/")[-1]
    assert name in components, f"{where}: schema ref {ref} not found in components"
    return components[name]


def test_every_v1_route_success_uses_canonical_envelope():
    schema = app.openapi()
    components = schema.get("components", {}).get("schemas", {})
    for route in app.routes:
        if not (isinstance(route, APIRoute) and _is_v1_path(route.path)):
            continue
        for method in route.methods - {"HEAD", "OPTIONS"}:
            where = f"{method} {route.path}"
            op = schema["paths"][route.path][method.lower()]
            comp = _resolve_success_envelope_component(op, components, where)
            # canonical envelope: exactly status/data/meta, status const "success"
            assert set(comp["properties"].keys()) == {"status", "data", "meta"}, \
                f"{where}: success body is not the canonical {{status,data,meta}} envelope"
            status_prop = comp["properties"]["status"]
            assert status_prop.get("const") == "success" \
                or status_prop.get("default") == "success", \
                f"{where}: envelope status is not const/default 'success'"


def test_v1_meta_success_matches_descriptor_and_envelope():
    resp = client.get("/api/v1")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"status", "data", "meta"}
    assert body["status"] == "success"
    assert body["data"] == contract_descriptor()


def test_v1_route_emits_request_id_header():
    resp = client.get("/api/v1")
    assert resp.headers.get(REQUEST_ID_HEADER)


def test_canonical_error_handlers_are_registered():
    # the three canonical handlers must be wired so raised errors render the
    # {error:{code,message,details}} shape (app/api/errors.py).
    from fastapi import HTTPException
    from fastapi.exceptions import RequestValidationError
    registered = app.exception_handlers
    assert HTTPException in registered
    assert RequestValidationError in registered
    assert Exception in registered


def test_raised_http_error_uses_canonical_shape_and_request_id():
    # a protected route hit WITHOUT an API key raises HTTPException(403), which
    # flows through http_exception_handler -> canonical error shape + X-Request-ID.
    # (Route-not-found 404s are served by Starlette's default handler and keep
    # the {"detail": ...} shape -- a known gap tracked in TECH-DEBT §26.)
    resp = client.get("/api/jobs")
    assert resp.status_code in (401, 403)
    body = resp.json()
    assert set(body["error"].keys()) == {"code", "message", "details"}
    assert resp.headers.get(REQUEST_ID_HEADER)


def test_descriptor_error_envelope_matches_schemas_error():
    from app.api.schemas import ErrorBody
    d = contract_descriptor()
    assert d["error_envelope"]["error"] == list(ErrorBody.model_fields.keys())


def test_required_error_codes_match_http_handler_mapping():
    # The descriptor's advertised error-code vocabulary must stay in sync with
    # the codes the HTTP exception handlers actually emit (app/api/errors.py).
    from app.api.errors import STATUS_TO_CODE
    d = contract_descriptor()
    assert set(d["required_error_codes"]) == set(STATUS_TO_CODE.values())


def test_contract_descriptor_model_covers_all_descriptor_keys():
    # The ContractDescriptor response model must expose exactly the keys
    # contract_descriptor() emits, so no descriptor key is silently dropped
    # from (or invented in) the served /api/v1 body.
    from app.api.v1_meta import ContractDescriptor
    assert set(ContractDescriptor.model_fields.keys()) == set(contract_descriptor().keys())
