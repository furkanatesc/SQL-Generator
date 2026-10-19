"""Sprint 32.12 - CI load gate on the production compose stack (static contract)."""
import os

import pytest
import yaml

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def job():
    wf = yaml.safe_load(_read(".github", "workflows", "backend-ci.yml"))
    return wf["jobs"]["prod-compose-smoke"]


def _names(job):
    return [s.get("name") for s in job["steps"]]


def _step(job, name):
    return next(s for s in job["steps"] if s.get("name") == name)


def test_overlay_only_disables_the_two_rate_limits():
    overlay = yaml.safe_load(_read("docker-compose.loadtest.yml"))
    assert set(overlay) == {"services"}
    assert set(overlay["services"]) == {"backend"}
    assert set(overlay["services"]["backend"]) == {"environment"}
    assert overlay["services"]["backend"]["environment"] == {
        "NL2SQL_RATE_LIMIT_REQUESTS_PER_MINUTE": "0",
        "NL2SQL_RATE_LIMIT_JOBS_PER_MINUTE": "0",
    }
    assert "${" not in _read("docker-compose.loadtest.yml")
    assert "never in production" in _read("docker-compose.loadtest.yml").lower()


def test_validate_step_checks_the_overlay(job):
    run = _step(job, "Validate compose file")["run"]
    assert "-f docker-compose.prod.yml -f docker-compose.loadtest.yml config -q" in run


def test_load_step_order_and_content(job):
    names = _names(job)
    assert "Load test (mixed scenario)" in names
    assert names.index("Structured JSON logs with request ids") < names.index("Load test (mixed scenario)")
    assert names.index("Load test (mixed scenario)") < names.index("Dump logs on failure")
    run = _step(job, "Load test (mixed scenario)")["run"]
    assert "-f docker-compose.prod.yml -f docker-compose.loadtest.yml" in run
    assert "up -d --wait --wait-timeout 180 backend" in run
    assert "python3 -m loadtest" in run
    assert "--api-key-file ../secrets/nl2sql_api_key" in run
    for flag in ("--scenario mixed", "--concurrency 16", "--duration 20",
                 "--max-error-rate 0", "--max-p95-ms 2000", "--json ../loadtest-report.json"):
        assert flag in run
    assert "/ready" in run and "fail" in run
    assert _step(job, "Load test (mixed scenario)").get("working-directory") == "backend" or "cd backend" in run


def test_report_is_uploaded_always(job):
    names = _names(job)
    step = next(s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/upload-artifact@v4"))
    assert step["if"] == "always()"
    assert "loadtest-report.json" in str(step["with"]["path"])
    assert names.index(step["name"]) < names.index("Tear down")


def test_load_step_has_no_failure_masking(job):
    step = _step(job, "Load test (mixed scenario)")
    assert "continue-on-error" not in step
    assert "|| true" not in step["run"]


def test_load_step_waits_for_worker_to_drain_created_jobs(job):
    run = _step(job, "Load test (mixed scenario)")["run"]
    # Order: load run, then the queue drain poll, then the /ready check.
    assert run.index("python3 -m loadtest") < run.index("/api/v1/admin/queue") < run.index("/ready")
    assert "X-API-Key" in run
    # The poll is bounded and judges the documented queue fields.
    for token in ("deadline", "dead_lettered", "retry_scheduled", "pending", "processing", "failed"):
        assert token in run
    # It compares against the number of jobs the load run created (from the JSON report).
    assert "job_create" in run and "loadtest-report.json" in run
    # A timeout fails the step with the last stats.
    assert "sys.exit(1)" in run or "raise SystemExit(1)" in run


def test_drain_script_only_reads_real_queue_status_keys(job):
    import re

    from app.jobs.repository import JOB_STATUSES

    run = _step(job, "Load test (mixed scenario)")["run"]
    keys = set(re.findall(r'c\["(\w+)"\]', run))
    assert keys and keys <= set(JOB_STATUSES)
    assert "processing" in keys
    assert '"running"' not in run
