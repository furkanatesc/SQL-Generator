"""Sprint 32.12 — in-process API concurrency tests.

One shared TestClient hammered from a thread pool: job creation/reads, workspace
creation (distinct and colliding slugs) and exact rate limiting under contention.
"""
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.settings import DEV_DEFAULT_API_KEY, get_settings

HEADERS = {"X-API-Key": DEV_DEFAULT_API_KEY}


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


def _run(fns, workers=16):
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return [f.result() for f in [pool.submit(fn) for fn in fns]]


def test_parallel_job_creation_and_reads(limited):
    client = limited()
    n = 40
    calls = []
    for i in range(n):
        calls.append(lambda i=i: ("post", client.post(
            "/api/jobs/without-file", json={"natural_query": f"concurrency {i}"}, headers=HEADERS)))
        calls.append(lambda: ("list", client.get("/api/jobs", headers=HEADERS)))
    results = _run(calls)

    assert all(r.status_code < 500 for _, r in results)
    posts = [r for kind, r in results if kind == "post"]
    assert all(r.status_code == 200 for r in posts)
    ids = {r.json()["job"]["id"] for r in posts}
    assert len(ids) == n

    gets = _run([lambda j=j: client.get(f"/api/jobs/{j}", headers=HEADERS) for j in ids])
    assert all(r.status_code == 200 for r in gets)


def test_parallel_workspace_creation_unique_slugs(limited):
    client = limited()
    slugs = [f"ws-{uuid.uuid4().hex[:10]}" for _ in range(30)]
    responses = _run([lambda s=s: client.post(
        "/api/v1/workspaces", json={"name": s, "slug": s}, headers=HEADERS) for s in slugs])
    assert [r.status_code for r in responses] == [201] * 30

    listing = client.get("/api/v1/workspaces", params={"limit": 200}, headers=HEADERS)
    assert listing.status_code == 200
    assert set(slugs) <= {w["slug"] for w in listing.json()["data"]}


def test_parallel_same_slug_has_one_winner(limited):
    client = limited()
    slug = f"same-{uuid.uuid4().hex[:10]}"
    responses = _run([lambda: client.post(
        "/api/v1/workspaces", json={"name": "dup", "slug": slug}, headers=HEADERS) for _ in range(12)])
    codes = sorted(r.status_code for r in responses)
    assert codes == [201] + [409] * 11


def test_rate_limit_is_exact_under_concurrency(limited):
    client = limited(requests=5, jobs=0)
    responses = _run([lambda: client.get("/api/jobs", headers=HEADERS) for _ in range(20)])
    codes = [r.status_code for r in responses]
    assert codes.count(200) == 5
    assert codes.count(429) == 15
