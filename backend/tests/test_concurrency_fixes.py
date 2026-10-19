"""Sprint 32.12 — concurrency fixes: thread-safe circuit breaker, non-blocking SSE endpoint."""
import asyncio
import sys
import threading
import uuid

from fastapi.testclient import TestClient

from app.settings import DEV_DEFAULT_API_KEY

HEADERS = {"X-API-Key": DEV_DEFAULT_API_KEY}


def test_breaker_counts_every_concurrent_failure():
    from app.llm.failover import CircuitBreaker

    breaker = CircuitBreaker(failure_threshold=10**9, reset_seconds=60.0)
    assert hasattr(breaker, "_lock")

    def hammer():
        for _ in range(5000):
            breaker.record_failure(0.0)

    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        threads = [threading.Thread(target=hammer) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        sys.setswitchinterval(old)
    assert breaker.consecutive_failures == 8 * 5000


def test_stream_endpoint_reads_job_off_the_event_loop(monkeypatch):
    import app.main as main
    from app.database import create_job, update_job_status

    job_id = str(uuid.uuid4())
    create_job(job_id, natural_query="q")
    update_job_status(job_id, "completed")

    real_get_job = main.get_job
    off_loop = []

    def spy(jid):
        try:
            asyncio.get_running_loop()
            off_loop.append(False)
        except RuntimeError:
            off_loop.append(True)
        return real_get_job(jid)

    monkeypatch.setattr(main, "get_job", spy)

    res = TestClient(main.app).get(f"/api/jobs/{job_id}/stream", headers=HEADERS)
    assert res.status_code == 200
    assert off_loop and all(off_loop)
