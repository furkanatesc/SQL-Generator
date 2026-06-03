import time
import uuid
import json
import logging
from urllib.parse import urlencode, parse_qsl
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.observability.performance import PerformanceClassifier

logger = logging.getLogger("app.request_logging")

def get_current_time() -> float:
    return time.perf_counter()

def get_sanitized_path(request: Request) -> str:
    path = request.url.path
    query = request.url.query
    if not query:
        return path
    parsed_query = parse_qsl(query, keep_blank_values=True)
    sanitized_query = []
    for k, v in parsed_query:
        # Mask sensitive key values
        if k.lower() in ("api_key", "apikey", "token", "secret", "password", "x-api-key"):
            sanitized_query.append((k, "******"))
        else:
            sanitized_query.append((k, v))
    return f"{path}?{urlencode(sanitized_query, safe='*')}"

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Retrieve or generate Request ID (case-insensitive for header)
        request_id = request.headers.get("X-Request-ID") or request.headers.get("x-request-id") or str(uuid.uuid4())
        
        # Store in request state for other parts of the application
        request.state.request_id = request_id
        
        start_time = get_current_time()
        
        # 2. Extract and sanitize path/query parameters
        sanitized_path = get_sanitized_path(request)
        
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            
            # 3. Add Request ID to response headers
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception as e:
            status_code = 500
            raise e
        finally:
            duration_ms = round((get_current_time() - start_time) * 1000.0, 2)
            tier = PerformanceClassifier.classify(duration_ms)
            log_data = {
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "path": sanitized_path,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "performance_tier": tier
            }
            logger.info(json.dumps(log_data))
            
            if tier == "slow":
                slow_event_data = {
                    "event": "slow_request",
                    "request_id": request_id,
                    "path": sanitized_path,
                    "duration_ms": duration_ms
                }
                logger.info(json.dumps(slow_event_data))
