# Deployment Acceptance Checklist

This checklist specifies the verification criteria and quality gates that must be satisfied before promoting a release candidate to production.

---

## 1. Configuration Check

Before deploying, verify the active configurations conform to target environment specifications:

- [ ] **API Key Configured**
  - Verify that a valid LLM API Key is configured in either the database settings table or via the `NL2SQL_API_KEY` environment variable.
- [ ] **Environment Configured**
  - Verify that `NL2SQL_ENVIRONMENT` is explicitly defined to match the target environment (e.g. `production-eu`, `production-us`).
- [ ] **CORS Configured**
  - Verify that `NL2SQL_CORS_ALLOW_ORIGINS` is configured with a restricted list of allowed, trusted origin domains. Wildcard `*` must not be used in production.
- [ ] **Debug Endpoints Reviewed**
  - Verify that development-only debug endpoints are turned off (`NL2SQL_DEBUG_ENDPOINTS_ENABLED=false`).
- [ ] **Upload Directory Reviewed**
  - Verify that a persistent storage volume is mounted and configured under `NL2SQL_UPLOAD_DIR` (defaults to `/app/uploads` inside the Docker container).

---

## 2. Runtime Check

Verify that the application starts up and runs correctly:

- [ ] **Container Build Successful**
  - Verify that the Docker image builds successfully without errors.
- [ ] **Container Startup Successful**
  - Verify that the built container starts up cleanly in detached mode.
- [ ] **`/health` Reachable**
  - Query `http://<host>:<port>/health` and ensure it responds with `200 OK` and `"status": "ok"`.
- [ ] **No Critical Startup Warnings**
  - Review `/health` diagnostics configuration response. Ensure `startup_critical_warnings_count` is `0` (the `ok` field of the startup validation result must be `true`).

---

## 3. Quality Gates

Ensure all automated code quality and regression checks pass:

- [ ] **`pytest` Green**
  - Run the full unit and integration test suite and verify `100%` test pass rate.
- [ ] **Golden Eval Green**
  - Execute SQL generator evaluation pipelines and ensure performance metrics satisfy the release criteria.
- [ ] **Docker Contract Tests Green**
  - Verify that all static Dockerfile and `.dockerignore` linting/structural assertions pass cleanly.
- [ ] **Runtime Smoke Test Green**
  - Run the container smoke test validation in the CI pipeline to verify end-to-end container startup and connectivity.

---

## 4. Security Check

Audit release environment variables and secrets configurations:

- [ ] **No Raw Secrets Committed**
  - Audit source files and Git history to ensure no API keys or database connection strings are hardcoded.
- [ ] **No Wildcard CORS in Production**
  - Confirm the API does not expose a wildcard CORS header (`Access-Control-Allow-Origin: *`) in any production-like environment.
- [ ] **Debug Endpoints Disabled in Production**
  - Confirm that debug/tracing routes are inaccessible in production-like environments to prevent execution parameter leaks.
