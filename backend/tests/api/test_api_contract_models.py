from pydantic import BaseModel
from app.api.contract import (
    API_VERSION, API_V1_PREFIX, REQUEST_ID_HEADER,
    ApiResponse, PageMeta, ResponseMeta,
    API_CONTRACT, contract_descriptor, ErrorResponse,
)


class _Widget(BaseModel):
    id: str


def test_constants():
    assert API_VERSION == "v1"
    assert API_V1_PREFIX == "/api/v1"
    assert REQUEST_ID_HEADER == "X-Request-ID"


def test_api_response_single_data_key_no_meta():
    resp = ApiResponse[_Widget](data=_Widget(id="w1"))
    dumped = resp.model_dump()
    assert dumped == {"status": "success", "data": {"id": "w1"}, "meta": None}
    # single canonical payload key, never a resource-named key
    assert set(dumped.keys()) == {"status", "data", "meta"}


def test_api_response_status_is_const_success():
    resp = ApiResponse[_Widget](data=_Widget(id="w1"))
    assert resp.status == "success"


def test_api_response_list_data():
    resp = ApiResponse[list[_Widget]](data=[_Widget(id="a"), _Widget(id="b")])
    dumped = resp.model_dump()
    assert dumped["data"] == [{"id": "a"}, {"id": "b"}]


def test_api_response_with_pagination_meta():
    resp = ApiResponse[list[_Widget]](
        data=[_Widget(id="a")],
        meta=ResponseMeta(pagination=PageMeta(limit=10, offset=0, count=1)),
    )
    dumped = resp.model_dump()
    assert dumped["meta"] == {"pagination": {"limit": 10, "offset": 0, "count": 1}}


def test_page_meta_fields():
    pm = PageMeta(limit=25, offset=50, count=25)
    assert pm.model_dump() == {"limit": 25, "offset": 50, "count": 25}


def test_error_reexport_is_the_schemas_one():
    import app.api.schemas as schemas
    assert ErrorResponse is schemas.ErrorResponse


def test_api_contract_descriptor_shape():
    d = contract_descriptor()
    assert d["version"] == "v1"
    assert d["prefix"] == "/api/v1"
    assert d["request_id_header"] == "X-Request-ID"
    assert d["success_envelope_fields"] == ["status", "data", "meta"]
    assert d["pagination_fields"] == ["limit", "offset", "count"]
    assert d["error_envelope"] == {"error": ["code", "message", "details"]}
    # required error codes cover the HTTP status->code vocabulary
    for code in ("BAD_REQUEST", "UNAUTHORIZED", "FORBIDDEN",
                 "NOT_FOUND", "VALIDATION_ERROR", "INTERNAL_SERVER_ERROR"):
        assert code in d["required_error_codes"]


def test_api_contract_fields_are_derived_from_models():
    # envelope + pagination field tuples must match the actual pydantic models,
    # so the descriptor cannot silently drift from the models it documents.
    assert API_CONTRACT.success_envelope_fields == tuple(ApiResponse.model_fields.keys())
    assert API_CONTRACT.pagination_fields == tuple(PageMeta.model_fields.keys())
