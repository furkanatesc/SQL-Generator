"""API rate limiting (Sprint 32.6).

Per-client token buckets kept in process memory: the API runs as a single uvicorn process
(backend/Dockerfile CMD), so the limit is exact; with several API replicas it would be per
replica (TECH-DEBT §42). Two limits, both off when 0:

- `NL2SQL_RATE_LIMIT_REQUESTS_PER_MINUTE` — every request except probes and CORS preflight;
- `NL2SQL_RATE_LIMIT_JOBS_PER_MINUTE` — additionally, the LLM-costly job-creation endpoints.

A client is its API key (SHA-256 prefix; the raw key is never stored) or, without one, its IP.
Exceeding a limit returns 429 with the canonical error envelope (`RATE_LIMITED`) and `Retry-After`.
"""
import hashlib
import math
import threading
import time
from collections import OrderedDict
from typing import Optional, Tuple

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.settings import get_settings

EXEMPT_PATHS = frozenset({"/health", "/ready"})
JOB_CREATION_ROUTES = frozenset({("POST", "/api/files/upload"), ("POST", "/api/jobs/without-file")})

Decision = Tuple[bool, float, int]  # (allowed, retry_after_seconds, remaining)


class Bucket:
    def __init__(self, capacity: float, refill_per_second: float, now: float):
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self.tokens = capacity
        self.updated = now

    def try_acquire(self, now: float) -> Decision:
        self.tokens = min(self.capacity, self.tokens + max(0.0, now - self.updated) * self.refill_per_second)
        self.updated = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True, 0.0, int(self.tokens)
        return False, (1.0 - self.tokens) / self.refill_per_second, 0


class RateLimiter:
    """`per_minute` sustained rate with a burst of `burst` (default: one minute's worth)."""

    def __init__(self, per_minute: int, burst: Optional[int] = None, max_clients: int = 10_000):
        self.per_minute = per_minute
        self.capacity = float(burst or per_minute)
        self.refill_per_second = per_minute / 60.0
        self.max_clients = max_clients
        self._buckets: "OrderedDict[str, Bucket]" = OrderedDict()
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._buckets)

    def check(self, key: str, now: Optional[float] = None) -> Decision:
        now = time.monotonic() if now is None else now
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                if len(self._buckets) >= self.max_clients:
                    # Drop the least recently used half to bound memory.
                    for _ in range(len(self._buckets) // 2):
                        self._buckets.popitem(last=False)
                bucket = self._buckets[key] = Bucket(self.capacity, self.refill_per_second, now)
            else:
                self._buckets.move_to_end(key)
            return bucket.try_acquire(now)


def client_key(request: Request) -> str:
    api_key = request.headers.get("x-api-key") or request.query_params.get("api_key")
    if api_key:
        return "key:" + hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
    host = request.client.host if request.client else "unknown"
    return f"ip:{host}"


_lock = threading.Lock()
_limiters: dict = {}


def reset_rate_limiters() -> None:
    with _lock:
        _limiters.clear()


def _limiter(name: str, per_minute: int) -> Optional[RateLimiter]:
    if per_minute <= 0:
        return None
    with _lock:
        current = _limiters.get(name)
        if current is None or current.per_minute != per_minute:
            current = _limiters[name] = RateLimiter(per_minute)
        return current


def _too_many(retry_after: float, limit: int) -> JSONResponse:
    seconds = max(1, math.ceil(retry_after))
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "RATE_LIMITED",
                "message": f"Rate limit exceeded. Retry after {seconds} seconds.",
                "details": {"retry_after_seconds": seconds, "limit_per_minute": limit},
            }
        },
        headers={"Retry-After": str(seconds), "X-RateLimit-Limit": str(limit), "X-RateLimit-Remaining": "0"},
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path in EXEMPT_PATHS:
            return await call_next(request)
        settings = get_settings()
        checks = [_limiter("requests", settings.rate_limit_requests_per_minute)]
        if (request.method, request.url.path) in JOB_CREATION_ROUTES:
            checks.append(_limiter("jobs", settings.rate_limit_jobs_per_minute))
        checks = [c for c in checks if c is not None]
        if not checks:
            return await call_next(request)

        key = client_key(request)
        headline = None
        for limiter in checks:
            allowed, retry_after, remaining = limiter.check(key)
            if not allowed:
                return _too_many(retry_after, limiter.per_minute)
            if headline is None:
                headline = (limiter.per_minute, remaining)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(headline[0])
        response.headers["X-RateLimit-Remaining"] = str(headline[1])
        return response
