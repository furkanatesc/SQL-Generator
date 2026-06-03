import json
import logging
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app.auth import verify_api_key

client = TestClient(app)

def test_http_exception_logging(caplog):
    app.dependency_overrides.clear()
    with caplog.at_level(logging.INFO, logger="app.request_logging"):
        # Make a request that yields an HTTPException (403 missing credentials)
        response = client.get("/api/jobs")
        assert response.status_code == 403
        
        # Verify response structure has no traceback
        body = response.json()
        assert "error" in body
        assert "traceback" not in str(body)
        assert "Exception" not in str(body)
        
        # Verify request id propagation
        assert "X-Request-ID" in response.headers
        request_id = response.headers["X-Request-ID"]
        assert request_id != ""

        # Check logs
        records = [json.loads(r.message) for r in caplog.records if r.name == "app.request_logging"]
        
        # We expect a request log AND an error log
        error_logs = [log for log in records if log.get("event") == "http_error"]
        request_logs = [log for log in records if log.get("event") == "http_request"]
        
        assert len(error_logs) == 1
        assert len(request_logs) == 1
        
        # Verify error log details
        err_log = error_logs[0]
        assert err_log["request_id"] == request_id
        assert err_log["method"] == "GET"
        assert err_log["path"] == "/api/jobs"
        assert err_log["error_type"] == "HTTPException"
        assert err_log["status_code"] == 403
        
        # Verify Correlation (matching request_id)
        assert request_logs[0]["request_id"] == request_id
        assert err_log["request_id"] == request_logs[0]["request_id"]

def test_validation_error_logging(caplog):
    # Override auth to bypass check
    app.dependency_overrides[verify_api_key] = lambda: True
    try:
        with caplog.at_level(logging.INFO, logger="app.request_logging"):
            # Post invalid body to trigger RequestValidationError
            response = client.post("/api/jobs/without-file", json={})
            assert response.status_code == 422
            
            body = response.json()
            assert "error" in body
            assert "traceback" not in str(body)
            
            # Verify request id propagation
            assert "X-Request-ID" in response.headers
            request_id = response.headers["X-Request-ID"]
            assert request_id != ""

            # Check logs
            records = [json.loads(r.message) for r in caplog.records if r.name == "app.request_logging"]
            error_logs = [log for log in records if log.get("event") == "validation_error"]
            request_logs = [log for log in records if log.get("event") == "http_request"]
            
            assert len(error_logs) == 1
            assert len(request_logs) == 1
            
            # Verify error log details
            err_log = error_logs[0]
            assert err_log["request_id"] == request_id
            assert err_log["method"] == "POST"
            assert err_log["path"] == "/api/jobs/without-file"
            assert err_log["error_type"] == "RequestValidationError"
            assert err_log["status_code"] == 422
            
            # Verify Correlation (matching request_id)
            assert err_log["request_id"] == request_logs[0]["request_id"]
    finally:
        app.dependency_overrides.clear()

def test_unhandled_exception_logging(caplog):
    # Mock verify_api_key to throw an unhandled RuntimeError
    def mock_internal_error():
        raise RuntimeError("Unexpected DB connection dropout")
        
    app.dependency_overrides[verify_api_key] = mock_internal_error
    
    # We must use raise_server_exceptions=False to test unhandled exceptions in the client response
    local_client = TestClient(app, raise_server_exceptions=False)
    
    try:
        with caplog.at_level(logging.INFO, logger="app.request_logging"):
            response = local_client.get("/api/jobs", headers={"X-API-Key": "dummy_key"})
            assert response.status_code == 500
            
            # Verify response shape has absolutely no traceback leakage
            body = response.json()
            assert "error" in body
            assert "Unexpected DB connection dropout" not in str(body)
            assert "traceback" not in str(body)
            
            # Verify request id propagation
            assert "X-Request-ID" in response.headers
            request_id = response.headers["X-Request-ID"]
            assert request_id != ""

            # Check logs
            records = [json.loads(r.message) for r in caplog.records if r.name == "app.request_logging"]
            error_logs = [log for log in records if log.get("event") == "unhandled_exception"]
            request_logs = [log for log in records if log.get("event") == "http_request"]
            
            assert len(error_logs) == 1
            assert len(request_logs) == 1
            
            # Verify error log details
            err_log = error_logs[0]
            assert err_log["request_id"] == request_id
            assert err_log["method"] == "GET"
            assert err_log["path"] == "/api/jobs"
            assert err_log["error_type"] == "RuntimeError"
            assert err_log["status_code"] == 500
            
            # Verify Correlation (matching request_id)
            assert err_log["request_id"] == request_logs[0]["request_id"]
    finally:
        app.dependency_overrides.clear()
