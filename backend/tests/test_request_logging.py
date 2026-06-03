import json
import logging
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.auth import verify_api_key

client = TestClient(app)

def test_health_request_logging(caplog):
    # Enable capturing of logs at INFO level for app.request_logging
    with caplog.at_level(logging.INFO, logger="app.request_logging"):
        response = client.get("/health")
        
        assert response.status_code == 200
        
        # Verify Request ID is in response headers
        assert "X-Request-ID" in response.headers
        request_id = response.headers["X-Request-ID"]
        assert request_id != ""

        # Filter logs for our middleware
        logging_records = [r for r in caplog.records if r.name == "app.request_logging"]
        assert len(logging_records) == 1
        
        record = logging_records[0]
        # Check that the log is valid JSON and parseable
        try:
            log_data = json.loads(record.message)
        except json.JSONDecodeError:
            pytest.fail("Log message is not a valid JSON string")
            
        # Verify required log fields
        assert log_data["event"] == "http_request"
        assert log_data["request_id"] == request_id
        assert log_data["method"] == "GET"
        assert log_data["path"] == "/health"
        assert log_data["status_code"] == 200
        
        # Verify duration_ms is present, numeric, and >= 0 (non-deterministic safe)
        assert isinstance(log_data["duration_ms"], (int, float))
        assert log_data["duration_ms"] >= 0

def test_invalid_api_key_query_param_masked_in_logs(caplog):
    with caplog.at_level(logging.INFO, logger="app.request_logging"):
        # Make a request with api_key in query params
        client.get("/api/jobs", params={"api_key": "secret_invalid_key_12345"})
        
        logging_records = [r for r in caplog.records if r.name == "app.request_logging"]
        assert len(logging_records) >= 1
        
        log_data = json.loads(logging_records[-1].message)
        
        # The query parameter api_key should be masked
        assert "api_key=******" in log_data["path"]
        assert "secret_invalid_key_12345" not in log_data["path"]
        # The raw log message itself should not contain the secret
        assert "secret_invalid_key_12345" not in logging_records[-1].message

def test_invalid_api_key_header_not_in_logs(caplog):
    with caplog.at_level(logging.INFO, logger="app.request_logging"):
        # Make a request with X-API-Key in headers
        client.get("/api/jobs", headers={"X-API-Key": "secret_invalid_key_99999"})
        
        logging_records = [r for r in caplog.records if r.name == "app.request_logging"]
        assert len(logging_records) >= 1
        
        raw_log_msg = logging_records[-1].message
        # Check that the header secret is not leaked in log metadata
        assert "secret_invalid_key_99999" not in raw_log_msg

def test_exception_during_request_still_logged(caplog):
    # Simulate an internal server failure by mocking verify_api_key dependency to throw an unhandled exception
    def mock_db_failure():
        raise RuntimeError("Simulated database failure")
        
    app.dependency_overrides[verify_api_key] = mock_db_failure
    
    local_client = TestClient(app, raise_server_exceptions=False)
    try:
        with caplog.at_level(logging.INFO, logger="app.request_logging"):
            # Call /api/jobs with an API key, which triggers the mocked verify_api_key dependency
            response = local_client.get("/api/jobs", headers={"X-API-Key": "dummy_key"})
            
            # Unhandled RuntimeError results in 500 Internal Server Error
            assert response.status_code == 500
            
            logging_records = [r for r in caplog.records if r.name == "app.request_logging"]
            assert len(logging_records) == 1
            
            log_data = json.loads(logging_records[0].message)
            assert log_data["event"] == "http_request"
            assert log_data["method"] == "GET"
            assert log_data["path"] == "/api/jobs"
            assert log_data["status_code"] == 500
            assert isinstance(log_data["duration_ms"], (int, float))
            assert log_data["duration_ms"] >= 0
    finally:
        app.dependency_overrides.clear()
