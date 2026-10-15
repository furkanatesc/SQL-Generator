"""Sprint 32.0 — Production Docker Compose contract guard.

Pins the production orchestration shape (`docker-compose.prod.yml`), the backend
image hardening (persistent dirs + HEALTHCHECK), the frontend production image and
the `.env.prod.example` drift guard. The real boot is exercised by the CI
`prod-compose-smoke` job; this suite keeps the static contract from drifting.
"""
import os
import re

import pytest
import yaml

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
COMPOSE_PATH = os.path.join(REPO_ROOT, "docker-compose.prod.yml")
ENV_EXAMPLE_PATH = os.path.join(REPO_ROOT, ".env.prod.example")
BACKEND_DOCKERFILE = os.path.join(REPO_ROOT, "backend", "Dockerfile")
FRONTEND_DIR = os.path.join(REPO_ROOT, "frontend")

# Known dev/test credentials that must never appear in the production compose.
FORBIDDEN_LITERALS = [
    "sqlgen_secret_dev_key",
    "Sqlgen_Str0ng!Pass",
    "Sqlgen_Ro0!Pass",
    "POSTGRES_PASSWORD",
    "MYSQL_ROOT_PASSWORD",
    "ORACLE_PASSWORD",
]
TEST_DB_IMAGES = ("postgres", "oracle", "mysql", "mssql")

VAR_REF = re.compile(r"\$\{([A-Z0-9_]+)")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def compose_text():
    assert os.path.exists(COMPOSE_PATH), "docker-compose.prod.yml must exist at the repo root"
    return _read(COMPOSE_PATH)


@pytest.fixture(scope="module")
def compose(compose_text):
    return yaml.safe_load(compose_text)


@pytest.fixture(scope="module")
def backend(compose):
    return compose["services"]["backend"]


@pytest.fixture(scope="module")
def frontend(compose):
    return compose["services"]["frontend"]


def _env(service):
    env = service.get("environment", {})
    if isinstance(env, list):
        env = dict(item.split("=", 1) for item in env)
    return {k: str(v) for k, v in env.items()}


def _mounts(service):
    """container_path -> source for every `source:target[:mode]` volume."""
    mounts = {}
    for entry in service.get("volumes", []):
        parts = entry.split(":")
        mounts[parts[1]] = parts[0]
    return mounts


def _build_context(service):
    build = service["build"]
    return build if isinstance(build, str) else build["context"]


def _healthcheck_cmd(service):
    test = service["healthcheck"]["test"]
    return " ".join(test) if isinstance(test, list) else test


# --- compose: shape -----------------------------------------------------------

def test_prod_compose_has_exactly_backend_and_frontend(compose):
    assert set(compose["services"]) == {"backend", "frontend"}


def test_prod_compose_has_no_test_database_images(compose):
    for name, svc in compose["services"].items():
        image = svc.get("image", "")
        assert not image.startswith(TEST_DB_IMAGES), f"{name} uses a test DB image: {image}"


def test_prod_compose_contains_no_literal_secrets(compose_text):
    for literal in FORBIDDEN_LITERALS:
        assert literal not in compose_text, f"literal secret/test credential leaked: {literal}"


# --- compose: backend -----------------------------------------------------------

def test_backend_builds_from_backend_dir_and_restarts(backend):
    assert _build_context(backend) == "./backend"
    assert backend["restart"] == "unless-stopped"
    assert "no-new-privileges:true" in backend.get("security_opt", [])


def test_backend_pins_production_safe_settings(backend):
    env = _env(backend)
    assert env["NL2SQL_ENVIRONMENT"] == "production"
    assert env["NL2SQL_DEBUG_ENDPOINTS_ENABLED"] == "false"


def test_backend_required_vars_fail_fast(backend):
    # `${VAR:?msg}` makes `docker compose` refuse to start when the value is missing.
    var = "NL2SQL_CORS_ALLOW_ORIGINS"
    assert _env(backend)[var].startswith("${" + var + ":?"), f"{var} must be required via :?"


# --- compose: secrets (Sprint 32.2) ---------------------------------------------

def test_api_key_is_a_docker_secret_not_an_env_value(compose, backend):
    env = _env(backend)
    assert "NL2SQL_API_KEY" not in env, "the API key must not be passed as a plain env value"
    assert env["NL2SQL_API_KEY_FILE"] == "/run/secrets/nl2sql_api_key"
    assert "nl2sql_api_key" in backend.get("secrets", [])
    secret = compose["secrets"]["nl2sql_api_key"]
    # Fail fast like the old `${NL2SQL_API_KEY:?}`: compose refuses to start without the path.
    assert secret["file"].startswith("${SQLGEN_API_KEY_SECRET_FILE:?")


def test_every_backend_secret_is_declared(compose, backend):
    declared = set(compose.get("secrets", {}) or {})
    for name in backend.get("secrets", []):
        assert name in declared, f"backend uses undeclared secret {name}"
        target = "/run/secrets/" + name
        assert target in _env(backend).values(), f"secret {name} is mounted but no *_FILE points at it"


def test_secrets_dir_is_gitignored():
    lines = {line.strip().rstrip("/") for line in _read(os.path.join(REPO_ROOT, ".gitignore")).splitlines()}
    assert "secrets" in lines or "/secrets" in lines


@pytest.mark.parametrize(
    "var", ["SQLGEN_DB_PATH", "NL2SQL_TRACE_DB_PATH", "NL2SQL_UPLOAD_DIR"]
)
def test_backend_state_paths_live_under_a_mounted_volume(backend, var):
    path = _env(backend)[var]
    mounted = _mounts(backend)
    assert any(
        path == target or path.startswith(target.rstrip("/") + "/") for target in mounted
    ), f"{var}={path} is not under any mounted volume {sorted(mounted)}"


def test_backend_persists_embedded_qdrant_store(backend):
    # rag_manager.py hard-codes <package>/qdrant_data -> /app/qdrant_data in the image.
    assert "/app/qdrant_data" in _mounts(backend)


def test_backend_volumes_are_declared_named_volumes(compose, backend):
    declared = set(compose.get("volumes", {}) or {})
    for target, source in _mounts(backend).items():
        assert source in declared, f"{target} must be backed by a declared named volume"


def test_backend_healthcheck_probes_health_endpoint(backend):
    assert "/health" in _healthcheck_cmd(backend)


# --- compose: frontend ----------------------------------------------------------

def test_frontend_builds_from_frontend_dir(frontend):
    assert _build_context(frontend) == "./frontend"
    assert frontend["restart"] == "unless-stopped"


def test_frontend_waits_for_healthy_backend(frontend):
    assert frontend["depends_on"]["backend"]["condition"] == "service_healthy"


def test_frontend_has_healthcheck(frontend):
    assert _healthcheck_cmd(frontend)


# --- env example drift guard ----------------------------------------------------

def test_env_example_documents_every_compose_variable(compose_text):
    assert os.path.exists(ENV_EXAMPLE_PATH), ".env.prod.example must exist at the repo root"
    documented = set(re.findall(r"^#?\s*([A-Z0-9_]+)=", _read(ENV_EXAMPLE_PATH), re.M))
    referenced = set(VAR_REF.findall(compose_text))
    missing = referenced - documented
    assert not missing, f".env.prod.example is missing: {sorted(missing)}"


def test_env_example_holds_no_real_dev_key():
    assert "sqlgen_secret_dev_key" not in _read(ENV_EXAMPLE_PATH)


# --- images ----------------------------------------------------------------------

def test_backend_dockerfile_creates_persistent_dirs_and_healthcheck():
    content = _read(BACKEND_DOCKERFILE)
    for d in ("/app/uploads", "/app/data", "/app/qdrant_data"):
        assert d in content, f"backend Dockerfile must create {d}"
    assert "HEALTHCHECK" in content
    assert "/health" in content


def test_frontend_dockerfile_is_multi_stage_non_root_nginx():
    content = _read(os.path.join(FRONTEND_DIR, "Dockerfile"))
    assert re.search(r"^FROM node:\S+ AS build", content, re.M)
    assert "npm ci" in content
    assert "npm run build" in content
    assert "nginx-unprivileged" in content
    assert "COPY --from=build" in content
    assert "EXPOSE 8080" in content


def test_frontend_nginx_has_spa_fallback():
    content = _read(os.path.join(FRONTEND_DIR, "nginx.conf"))
    assert "try_files $uri $uri/ /index.html" in content
    assert "listen 8080" in content


def test_frontend_dockerignore_excludes_local_artifacts():
    lines = {
        line.strip().rstrip("/")
        for line in _read(os.path.join(FRONTEND_DIR, ".dockerignore")).splitlines()
    }
    assert {"node_modules", "dist"} <= lines
