import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
import uuid
import time

from app.main import app, verify_api_key
from app.database import create_job, update_job_status, list_jobs

client = TestClient(app)


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[verify_api_key] = lambda: True
    yield
    app.dependency_overrides.clear()


# Helper function strictly validating standard error response contract from PR 11.2
def assert_error_contract(body, *, code):
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message", "details"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str)


# 1. Default sorting response contract test
@patch("app.main.list_jobs", return_value=[])
def test_jobs_list_default_sort_contract(mock_list):
    res = client.get("/api/jobs")

    assert res.status_code == 200
    body = res.json()

    assert set(body.keys()) == {"jobs", "limit", "offset", "count", "status", "sort_by", "sort_order"}
    assert body["sort_by"] == "created_at"
    assert body["sort_order"] == "desc"

    mock_list.assert_called_once_with(
        limit=50,
        offset=0,
        status=None,
        sort_by="created_at",
        sort_order="desc",
    )


# 2. Sort by created_at asc
@patch("app.main.list_jobs", return_value=[])
def test_jobs_list_sorts_by_created_at_asc(mock_list):
    res = client.get("/api/jobs?sort_by=created_at&sort_order=asc")

    assert res.status_code == 200
    body = res.json()

    assert body["sort_by"] == "created_at"
    assert body["sort_order"] == "asc"

    mock_list.assert_called_once_with(
        limit=50,
        offset=0,
        status=None,
        sort_by="created_at",
        sort_order="asc",
    )


# 3. Sort by updated_at desc
@patch("app.main.list_jobs", return_value=[])
def test_jobs_list_sorts_by_updated_at_desc(mock_list):
    res = client.get("/api/jobs?sort_by=updated_at&sort_order=desc")

    assert res.status_code == 200
    body = res.json()

    assert body["sort_by"] == "updated_at"
    assert body["sort_order"] == "desc"

    mock_list.assert_called_once_with(
        limit=50,
        offset=0,
        status=None,
        sort_by="updated_at",
        sort_order="desc",
    )


# 4. Reject invalid sort_by (returns 422 standard error envelope)
def test_jobs_list_rejects_invalid_sort_by():
    res = client.get("/api/jobs?sort_by=invalid_field")

    assert res.status_code == 422
    body = res.json()

    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "sort_by" in str(body["error"]["details"])


# 5. Reject invalid sort_order (returns 422 standard error envelope)
def test_jobs_list_rejects_invalid_sort_order():
    res = client.get("/api/jobs?sort_order=invalid_dir")

    assert res.status_code == 422
    body = res.json()

    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "sort_order" in str(body["error"]["details"])


# 6. OpenAPI verification for jobs sort query parameters
def test_openapi_jobs_sort_query_parameters_contract():
    schema = client.get("/openapi.json").json()
    parameters = schema["paths"]["/api/jobs"]["get"]["parameters"]
    
    sort_by_param = next(p for p in parameters if p["name"] == "sort_by")
    sort_order_param = next(p for p in parameters if p["name"] == "sort_order")
    
    # Assert sort_by parameter contract
    assert sort_by_param["in"] == "query"
    assert sort_by_param["required"] is False
    assert sort_by_param["schema"]["$ref"] == "#/components/schemas/JobSortBy"
    
    # Assert sort_order parameter contract
    assert sort_order_param["in"] == "query"
    assert sort_order_param["required"] is False
    assert sort_order_param["schema"]["$ref"] == "#/components/schemas/SortOrder"


# 7. OpenAPI verification for JobSortBy and SortOrder enum values
def test_openapi_job_sort_enum_values_contract():
    schema = client.get("/openapi.json").json()
    components = schema["components"]["schemas"]
    
    assert "JobSortBy" in components
    assert set(components["JobSortBy"]["enum"]) == {"created_at", "updated_at"}
    
    assert "SortOrder" in components
    assert set(components["SortOrder"]["enum"]) == {"asc", "desc"}


# 8. DB-level test: list_jobs orders by created_at desc correctly
def test_database_list_jobs_orders_by_created_at_desc():
    id1 = f"job-first-{uuid.uuid4()}"
    id2 = f"job-second-{uuid.uuid4()}"

    # We insert two jobs sequentially. In DB, ordering by created_at desc should put id2 first.
    create_job(job_id=id1, natural_query="first", dialect="postgres")
    time.sleep(0.05)
    create_job(job_id=id2, natural_query="second", dialect="postgres")

    rows = list_jobs(limit=1000, offset=0, sort_by="created_at", sort_order="desc")
    row_ids = [row["id"] for row in rows if row["id"] in (id1, id2)]

    # In desc order, the most recent (id2) should be first
    assert row_ids == [id2, id1]


# 9. DB-level test: list_jobs orders by updated_at asc correctly
def test_database_list_jobs_orders_by_updated_at_asc():
    id1 = f"job-u1-{uuid.uuid4()}"
    id2 = f"job-u2-{uuid.uuid4()}"

    create_job(job_id=id1, natural_query="first", dialect="postgres")
    create_job(job_id=id2, natural_query="second", dialect="postgres")

    # Update id1 first, then id2.
    # To test asc ordering, the older update (id1) should be first.
    update_job_status(id1, "processing")
    time.sleep(0.05)
    update_job_status(id2, "processing")

    rows = list_jobs(limit=1000, offset=0, sort_by="updated_at", sort_order="asc")
    row_ids = [row["id"] for row in rows if row["id"] in (id1, id2)]

    # In asc order, the older update (id1) should be first
    assert row_ids == [id1, id2]


# 10. DB whitelist test: list_jobs rejects invalid sort_by (SQL Injection Guard)
def test_database_list_jobs_rejects_invalid_sort_by():
    with pytest.raises(ValueError, match="Invalid sort_by"):
        list_jobs(sort_by="id; DROP TABLE jobs", sort_order="desc")


# 11. DB whitelist test: list_jobs rejects invalid sort_order (SQL Injection Guard)
def test_database_list_jobs_rejects_invalid_sort_order():
    with pytest.raises(ValueError, match="Invalid sort_order"):
        list_jobs(sort_by="created_at", sort_order="desc; DROP TABLE jobs")
