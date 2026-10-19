"""Sprint 32.11 — CI/CD Release Pipeline + Staging (static contract).

The release workflow only runs on a version tag or a manual dispatch; it verifies, publishes the
backend/frontend images to GHCR, smoke-tests the *published* images with the staging overlay,
then creates the GitHub Release. Images carry their version; compose can run registry images;
the staging overlay is production-like and isolated from production.
"""
import os
import re

import pytest
import yaml

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def wf():
    return yaml.safe_load(_read(".github", "workflows", "release.yml"))


def _on(wf):
    return wf.get("on", wf.get(True))  # PyYAML reads the bare `on` key as True


def _steps_text(job):
    return "\n".join(str(s.get("run", "")) + " " + str(s.get("uses", "")) + " " + str(s.get("with", ""))
                     for s in job.get("steps", []))


# --- release workflow ---------------------------------------------------------------------

def test_triggers_only_on_version_tags_and_manual_dispatch(wf):
    on = _on(wf)
    assert set(on) == {"push", "workflow_dispatch"}
    assert set(on["push"]) == {"tags"}
    assert on["push"]["tags"] == ["v*.*.*"]
    assert "version" in on["workflow_dispatch"]["inputs"]


def test_job_chain(wf):
    jobs = wf["jobs"]
    assert set(jobs) == {"verify", "publish", "staging-smoke", "github-release"}
    assert jobs["publish"]["needs"] == "verify"
    assert jobs["staging-smoke"]["needs"] == "publish"
    assert set(jobs["github-release"]["needs"]) == {"publish", "staging-smoke"}


def test_least_privilege_permissions(wf):
    assert wf["permissions"] == {"contents": "read"}
    assert wf["jobs"]["publish"]["permissions"]["packages"] == "write"
    assert wf["jobs"]["github-release"]["permissions"]["contents"] == "write"
    for name in ("verify", "staging-smoke"):
        assert "write" not in str(wf["jobs"][name].get("permissions", {}))


def test_github_release_only_for_tags(wf):
    assert "refs/tags/" in str(wf["jobs"]["github-release"]["if"])


def test_verify_runs_backend_tests_and_frontend_build(wf):
    text = _steps_text(wf["jobs"]["verify"])
    assert "pytest" in text and "npm ci" in text and "npm run build" in text


def test_publish_pushes_versioned_images_to_ghcr(wf):
    job = wf["jobs"]["publish"]
    text = _steps_text(job)
    assert "docker/login-action" in text and "ghcr.io" in text
    builds = [s for s in job["steps"] if "docker/build-push-action" in str(s.get("uses", ""))]
    assert len(builds) == 2
    contexts = {s["with"]["context"] for s in builds}
    assert contexts == {"backend", "frontend"}
    for s in builds:
        assert s["with"]["push"] is True
    backend = next(s for s in builds if s["with"]["context"] == "backend")
    assert "APP_VERSION=" in backend["with"]["build-args"]
    assert "sqlgen-backend" in text and "sqlgen-frontend" in text
    assert "type=semver" in text and "type=sha" in text


def test_staging_smoke_uses_published_images_and_overlay(wf):
    job = wf["jobs"]["staging-smoke"]
    env = job.get("env", {})
    text = _steps_text(job)
    assert "docker-compose.staging.yml" in env["COMPOSE_FILE"]
    assert "--no-build" in text and "pull" in text
    assert "/ready" in text and "/health" in text
    assert "publish.outputs.registry" in env["SQLGEN_IMAGE_REGISTRY"]
    assert "publish.outputs.version" in env["SQLGEN_IMAGE_TAG"]


# --- images ----------------------------------------------------------------------------------

def test_backend_image_embeds_version():
    dockerfile = _read("backend", "Dockerfile")
    assert re.search(r"^ARG APP_VERSION=0\.1\.0$", dockerfile, re.M)
    assert re.search(r"^ENV NL2SQL_APP_VERSION=\$\{APP_VERSION\}$", dockerfile, re.M)
    assert "org.opencontainers.image.version" in dockerfile


def test_frontend_image_is_labelled():
    assert "org.opencontainers.image.version" in _read("frontend", "Dockerfile")


# --- compose ---------------------------------------------------------------------------------

def test_prod_compose_can_run_registry_images():
    compose = yaml.safe_load(_read("docker-compose.prod.yml"))
    for name in ("backend", "worker"):
        assert compose["services"][name]["image"] == "${SQLGEN_IMAGE_REGISTRY:-}sqlgen-backend:${SQLGEN_IMAGE_TAG:-latest}"
    assert compose["services"]["frontend"]["image"] == "${SQLGEN_IMAGE_REGISTRY:-}sqlgen-frontend:${SQLGEN_IMAGE_TAG:-latest}"
    assert re.search(r"^#?\s*SQLGEN_IMAGE_REGISTRY=", _read(".env.prod.example"), re.M)


@pytest.fixture(scope="module")
def staging():
    return yaml.safe_load(_read("docker-compose.staging.yml"))


def test_staging_overlay_is_isolated_and_production_like(staging):
    from app.settings import is_production_like_environment

    assert staging["name"] == "sqlgen-staging"  # separate project: own volumes and network
    for name in ("backend", "worker"):
        env = staging["services"][name]["environment"]
        assert env["NL2SQL_ENVIRONMENT"] == "production-staging"
        assert is_production_like_environment(env["NL2SQL_ENVIRONMENT"])
    assert "sqlgen_secret_dev_key" not in _read("docker-compose.staging.yml")


def test_staging_overlay_adds_no_new_variables(staging):
    # Staging reuses the production variables (ports etc. come from a separate env file, see the
    # runbook), so .env.prod.example stays the single list of compose variables.
    referenced = set(re.findall(r"\$\{([A-Z0-9_]+)", _read("docker-compose.staging.yml")))
    assert referenced <= set(re.findall(r"\$\{([A-Z0-9_]+)", _read("docker-compose.prod.yml")))


def test_pr_ci_validates_the_staging_overlay():
    ci = _read(".github", "workflows", "backend-ci.yml")
    assert "docker-compose.staging.yml" in ci and "config -q" in ci
