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
EXPECTED_V1_ROUTES = {("GET", "/api/v1")}


def _v1_routes():
    found = set()
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith(API_V1_PREFIX):
            for method in route.methods - {"HEAD", "OPTIONS"}:
                found.add((method, route.path))
    return found


def test_v1_route_set_matches_known_conforming_allowlist():
    assert _v1_routes() == EXPECTED_V1_ROUTES


def test_every_v1_route_success_uses_canonical_envelope():
    schema = app.openapi()
    for route in app.routes:
        if not (isinstance(route, APIRoute) and route.path.startswith(API_V1_PREFIX)):
            continue
        for method in route.methods - {"HEAD", "OPTIONS"}:
            op = schema["paths"][route.path][method.lower()]
            ok = op["responses"]["200"]["content"]["application/json"]["schema"]
            ref = ok.get("$ref", "")
            comp = schema["components"]["schemas"][ref.split("/")[-1]]
            # canonical envelope: exactly status/data/meta, status const "success"
            assert set(comp["properties"].keys()) == {"status", "data", "meta"}
            assert comp["properties"]["status"].get("const") == "success" \
                or comp["properties"]["status"].get("default") == "success"


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
