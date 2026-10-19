"""Threaded urllib runner. Stdlib only."""
from __future__ import annotations

import http.client
import itertools
import json
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import Sequence

from .core import RequestSpec, Result, schedule

_WINDOW = 4096  # precomputed schedule window, cycled


def run(
    base_url: str,
    api_key: str,
    specs: Sequence[RequestSpec],
    concurrency: int,
    duration_s: float,
    timeout_s: float = 10.0,
) -> tuple[list[Result], float]:
    base = base_url.rstrip("/")
    run_id = uuid.uuid4().hex[:8]  # keeps slugs unique across repeated runs
    lock = threading.Lock()
    cursor = itertools.count()  # shared schedule cursor; also the per-run seq
    plan = schedule(specs, _WINDOW)
    results: list[Result] = []

    def next_spec() -> tuple[RequestSpec, int]:
        with lock:
            i = next(cursor)
        return plan[i % len(plan)], i

    def fire(spec: RequestSpec, seq: int) -> Result:
        data = None
        headers = {"X-API-Key": api_key}
        if spec.body is not None:
            data = json.dumps(spec.body(run_id, seq)).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(base + spec.path, data=data, method=spec.method, headers=headers)
        start = time.perf_counter()
        status: int | None
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                resp.read()
                status = resp.status
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
        except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError):
            status = None
        latency = (time.perf_counter() - start) * 1000.0
        return Result(spec.name, status, latency, status is not None and status in spec.expected)

    started = time.perf_counter()
    deadline = started + duration_s

    def worker() -> None:
        local: list[Result] = []
        try:
            while time.perf_counter() < deadline:
                spec, seq = next_spec()
                local.append(fire(spec, seq))
        finally:
            with lock:
                results.extend(local)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(max(1, concurrency))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results, time.perf_counter() - started
