"""Sprint 32.6 — Rate Limiting.

Per-client token buckets in front of the API (general + job creation), a canonical 429
`RATE_LIMITED` error with `Retry-After`, and a process-wide LLM call limiter shared by every
job (the old per-`NVIDIAClient` bucket was recreated for each job).
"""
import pytest
from fastapi.testclient import TestClient

from app.settings import DEV_DEFAULT_API_KEY, get_settings

HEADERS = {"X-API-Key": DEV_DEFAULT_API_KEY}


# --- bucket / limiter (pure) ---------------------------------------------------------------

def test_bucket_allows_burst_then_refills():
    from app.rate_limit import Bucket

    b = Bucket(capacity=2, refill_per_second=1.0, now=0.0)
    assert b.try_acquire(0.0)[0] and b.try_acquire(0.0)[0]
    allowed, retry_after, remaining = b.try_acquire(0.0)
    assert (allowed, remaining) == (False, 0)
    assert retry_after == pytest.approx(1.0)
    assert b.try_acquire(0.5)[0] is False
    assert b.try_acquire(1.0)[0] is True


def test_limiter_isolates_clients_and_reports_remaining():
    from app.rate_limit import RateLimiter

    lim = RateLimiter(per_minute=2)
    assert lim.check("a", now=0.0) == (True, 0.0, 1)
    assert lim.check("a", now=0.0)[0] is True
    assert lim.check("a", now=0.0)[0] is False
    assert lim.check("b", now=0.0)[0] is True  # other client unaffected
    # 2/min -> one token every 30 s
    assert lim.check("a", now=30.0)[0] is True


def test_limiter_bounds_memory():
    from app.rate_limit import RateLimiter

    lim = RateLimiter(per_minute=10, max_clients=100)
    for i in range(1000):
        lim.check(f"c{i}", now=float(i))
    assert len(lim) <= 100


def test_client_key_hashes_api_key_and_falls_back_to_ip():
    from starlette.requests import Request

    from app.rate_limit import client_key

    def req(headers=(), query=b""):
        return Request({"type": "http", "method": "GET", "path": "/x", "query_string": query,
                        "headers": list(headers), "client": ("10.0.0.7", 1234)})

    k = client_key(req([(b"x-api-key", b"super-secret-key")]))
    assert k.startswith("key:") and "super-secret-key" not in k
    assert client_key(req(query=b"api_key=super-secret-key")) == k
    assert client_key(req()) == "ip:10.0.0.7"


# --- middleware ------------------------------------------------------------------------------

@pytest.fixture
def limited(monkeypatch):
    from app.rate_limit import reset_rate_limiters

    def configure(requests=0, jobs=0):
        monkeypatch.setenv("NL2SQL_RATE_LIMIT_REQUESTS_PER_MINUTE", str(requests))
        monkeypatch.setenv("NL2SQL_RATE_LIMIT_JOBS_PER_MINUTE", str(jobs))
        monkeypatch.setenv("NL2SQL_JOB_EXECUTION_MODE", "worker")  # creating a job only enqueues
        get_settings.cache_clear()
        reset_rate_limiters()
        from app.main import app

        return TestClient(app)

    yield configure
    reset_rate_limiters()


def test_disabled_by_default(limited):
    client = limited()
    for _ in range(50):
        assert client.get("/api/jobs", headers=HEADERS).status_code == 200


def test_exceeding_the_limit_returns_canonical_429(limited):
    client = limited(requests=3)
    for _ in range(3):
        r = client.get("/api/jobs", headers=HEADERS)
        assert r.status_code == 200
    assert r.headers["X-RateLimit-Limit"] == "3" and r.headers["X-RateLimit-Remaining"] == "0"
    r = client.get("/api/jobs", headers=HEADERS)
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1
    assert r.headers.get("X-Request-ID")
    assert r.json()["error"]["code"] == "RATE_LIMITED"
    assert DEV_DEFAULT_API_KEY not in r.text


def test_other_clients_are_not_affected(limited):
    client = limited(requests=1)
    assert client.get("/api/jobs", headers=HEADERS).status_code == 200
    assert client.get("/api/jobs", headers=HEADERS).status_code == 429
    # an unauthenticated client is keyed by IP and still gets its own bucket (then 403 from auth)
    assert client.get("/api/jobs").status_code == 403


def test_job_creation_has_its_own_tighter_limit(limited):
    client = limited(requests=100, jobs=2)
    body = {"natural_query": "kaç hasta var"}
    assert client.post("/api/jobs/without-file", json=body, headers=HEADERS).status_code == 200
    assert client.post("/api/jobs/without-file", json=body, headers=HEADERS).status_code == 200
    r = client.post("/api/jobs/without-file", json=body, headers=HEADERS)
    assert r.status_code == 429 and r.json()["error"]["code"] == "RATE_LIMITED"
    assert client.get("/api/jobs", headers=HEADERS).status_code == 200  # reads still allowed


def test_probes_and_preflight_are_exempt(limited):
    client = limited(requests=1)
    for _ in range(5):
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code in (200, 503)
    preflight = {"Origin": "http://localhost:8080", "Access-Control-Request-Method": "GET"}
    for _ in range(5):
        assert client.options("/api/jobs", headers=preflight).status_code == 200


def test_429_carries_cors_headers(limited):
    client = limited(requests=1)
    headers = {**HEADERS, "Origin": "http://localhost:8080"}
    client.get("/api/jobs", headers=headers)
    r = client.get("/api/jobs", headers=headers)
    assert r.status_code == 429
    assert r.headers.get("access-control-allow-origin")


def test_rate_limited_is_a_required_contract_error_code():
    from app.api.contract import API_CONTRACT
    from app.api.errors import map_status_to_code

    assert map_status_to_code(429) == "RATE_LIMITED"
    assert "RATE_LIMITED" in API_CONTRACT.required_error_codes


# --- LLM limiter -------------------------------------------------------------------------------

def test_llm_limiter_is_shared_across_clients(monkeypatch):
    from app import llm_client

    monkeypatch.setenv("NL2SQL_LLM_REQUESTS_PER_MINUTE", "6")
    monkeypatch.setenv("NL2SQL_LLM_BURST", "2")
    get_settings.cache_clear()
    a, b = llm_client.NVIDIAClient(), llm_client.NVIDIAClient()
    assert a.limiter is b.limiter
    assert a.limiter.capacity == 2 and a.limiter.fill_rate == pytest.approx(0.1)
    monkeypatch.setenv("NL2SQL_LLM_REQUESTS_PER_MINUTE", "30")
    get_settings.cache_clear()
    assert llm_client.NVIDIAClient().limiter.fill_rate == pytest.approx(0.5)


def test_llm_defaults_match_previous_behaviour(monkeypatch):
    from app import llm_client

    monkeypatch.delenv("NL2SQL_LLM_REQUESTS_PER_MINUTE", raising=False)
    monkeypatch.delenv("NL2SQL_LLM_BURST", raising=False)
    get_settings.cache_clear()
    lim = llm_client.get_llm_rate_limiter()
    assert lim.capacity == 3 and lim.fill_rate == pytest.approx(15 / 60)


def test_rate_limit_settings_are_validated(monkeypatch):
    from pydantic import ValidationError

    from app.settings import Settings

    for name, bad in (("NL2SQL_RATE_LIMIT_REQUESTS_PER_MINUTE", "-1"), ("NL2SQL_RATE_LIMIT_JOBS_PER_MINUTE", "-1"),
                      ("NL2SQL_LLM_REQUESTS_PER_MINUTE", "0"), ("NL2SQL_LLM_BURST", "0")):
        monkeypatch.setenv(name, bad)
        with pytest.raises(ValidationError):
            Settings()
        monkeypatch.delenv(name)
