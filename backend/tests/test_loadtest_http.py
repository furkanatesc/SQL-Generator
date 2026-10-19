import json
import socket
import threading
import time

import pytest
import uvicorn

from app.settings import DEV_DEFAULT_API_KEY, get_settings
from loadtest.__main__ import main
from loadtest.core import SCENARIOS, evaluate, summarize
from loadtest.http_runner import run


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def live_url(monkeypatch):
    monkeypatch.setenv("NL2SQL_JOB_EXECUTION_MODE", "worker")
    monkeypatch.setenv("NL2SQL_RATE_LIMIT_REQUESTS_PER_MINUTE", "0")
    monkeypatch.setenv("NL2SQL_RATE_LIMIT_JOBS_PER_MINUTE", "0")
    get_settings.cache_clear()
    from app.main import app

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)
    get_settings.cache_clear()


def test_run_against_live_server(live_url):
    by_name = {s.name: s for s in SCENARIOS["read"] + SCENARIOS["write"]}
    specs = [by_name[n] for n in ("jobs_list", "workspaces_list", "workspace_create", "job_create")]
    results, elapsed = run(live_url, DEV_DEFAULT_API_KEY, specs, concurrency=8, duration_s=2)
    summary = summarize(results, elapsed)
    assert summary["requests"] > 0
    assert summary["errors"] == 0, summary["status_counts"]


def test_unreachable_server_counts_errors():
    url = f"http://127.0.0.1:{_free_port()}"
    results, elapsed = run(url, "k", SCENARIOS["read"], concurrency=2, duration_s=0.5, timeout_s=1)
    assert results and all(r.status is None for r in results)
    assert evaluate(summarize(results, elapsed), 0.0, 2000.0)


def test_cli_writes_json_and_hides_key(live_url, tmp_path, capsys):
    key_file = tmp_path / "key.txt"
    key_file.write_text(DEV_DEFAULT_API_KEY)
    out = tmp_path / "report.json"
    argv = ["--base-url", live_url, "--api-key-file", str(key_file), "--scenario", "read",
            "--concurrency", "2", "--duration", "1", "--json", str(out)]
    assert main(argv) == 0
    text = out.read_text()
    assert "summary" in json.loads(text)
    assert DEV_DEFAULT_API_KEY not in text
    assert DEV_DEFAULT_API_KEY not in capsys.readouterr().out
    assert main(argv + ["--max-p95-ms", "0"]) == 1


def test_http_protocol_errors_count_as_errors_and_keep_results(monkeypatch):
    import http.client
    import urllib.request

    def boom(*a, **k):
        raise http.client.IncompleteRead(b"x")

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", boom)
    results, elapsed = run("http://127.0.0.1:1", "k", SCENARIOS["read"], concurrency=2, duration_s=0.3)
    assert results and all(r.status is None and not r.ok for r in results)
    assert summarize(results, elapsed)["errors"] == len(results)


def test_runner_opener_ignores_proxy_env(monkeypatch):
    import urllib.request

    seen = {}
    real = urllib.request.build_opener

    def spy(*handlers):
        seen["handlers"] = handlers
        return real(*handlers)

    monkeypatch.setattr(urllib.request, "build_opener", spy)
    run("http://127.0.0.1:1", "k", SCENARIOS["read"], concurrency=1, duration_s=0.1)
    assert any(isinstance(h, urllib.request.ProxyHandler) and not h.proxies for h in seen["handlers"])
