import json
import logging
import pytest
from fastapi.testclient import TestClient
from app.main import app
import app.middleware.request_logging as rl

client = TestClient(app)

def test_fast_request_performance(monkeypatch, caplog):
    # Mock time.perf_counter to return 0.0 then 0.05 (difference of 50ms = fast)
    calls = [0.0, 0.05]
    def mock_counter():
        return calls.pop(0) if calls else 0.05
    
    monkeypatch.setattr(rl, "get_current_time", mock_counter)
    
    with caplog.at_level(logging.INFO, logger="app.request_logging"):
        response = client.get("/health")
        assert response.status_code == 200
        
        records = [json.loads(r.message) for r in caplog.records if r.name == "app.request_logging"]
        request_logs = [log for log in records if log.get("event") == "http_request"]
        slow_logs = [log for log in records if log.get("event") == "slow_request"]
        
        assert len(request_logs) == 1
        assert len(slow_logs) == 0
        
        log_data = request_logs[0]
        assert log_data["performance_tier"] == "fast"
        assert log_data["duration_ms"] == 50.0

def test_normal_request_performance(monkeypatch, caplog):
    # Mock time.perf_counter to return 0.0 then 0.25 (difference of 250ms = normal)
    calls = [0.0, 0.25]
    def mock_counter():
        return calls.pop(0) if calls else 0.25
    
    monkeypatch.setattr(rl, "get_current_time", mock_counter)
    
    with caplog.at_level(logging.INFO, logger="app.request_logging"):
        response = client.get("/health")
        assert response.status_code == 200
        
        records = [json.loads(r.message) for r in caplog.records if r.name == "app.request_logging"]
        request_logs = [log for log in records if log.get("event") == "http_request"]
        slow_logs = [log for log in records if log.get("event") == "slow_request"]
        
        assert len(request_logs) == 1
        assert len(slow_logs) == 0
        
        log_data = request_logs[0]
        assert log_data["performance_tier"] == "normal"
        assert log_data["duration_ms"] == 250.0

def test_slow_request_performance(monkeypatch, caplog):
    # Mock time.perf_counter to return 0.0 then 0.90 (difference of 900ms = slow)
    calls = [0.0, 0.90]
    def mock_counter():
        return calls.pop(0) if calls else 0.90
    
    monkeypatch.setattr(rl, "get_current_time", mock_counter)
    
    with caplog.at_level(logging.INFO, logger="app.request_logging"):
        response = client.get("/health")
        assert response.status_code == 200
        
        # Verify request id header
        assert "X-Request-ID" in response.headers
        request_id = response.headers["X-Request-ID"]
        assert request_id != ""

        records = [json.loads(r.message) for r in caplog.records if r.name == "app.request_logging"]
        request_logs = [log for log in records if log.get("event") == "http_request"]
        slow_logs = [log for log in records if log.get("event") == "slow_request"]
        
        assert len(request_logs) == 1
        assert len(slow_logs) == 1
        
        req_log = request_logs[0]
        assert req_log["performance_tier"] == "slow"
        assert req_log["duration_ms"] == 900.0
        assert req_log["request_id"] == request_id
        
        slow_log = slow_logs[0]
        assert slow_log["duration_ms"] == 900.0
        assert slow_log["path"] == "/health"
        
        # Verify Correlation (matching request_id)
        assert slow_log["request_id"] == request_id
        assert slow_log["request_id"] == req_log["request_id"]
