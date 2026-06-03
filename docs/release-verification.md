# Release Verification Runbook

This document details the step-by-step verification commands required to validate a Release Candidate (RC) before promotion.

---

## 1. Run Automated Test Suite

Verify that all backend unit, integration, and contract tests pass successfully.

```bash
# Navigate to the backend directory
cd backend

# Run pytest in quiet mode
python -m pytest -q
```

### Expected Output
All required tests pass. Optional skipped tests are acceptable only when explicitly documented.

---

## 2. Build the Docker Image

Verify that the application package builds into a Docker image cleanly.

```bash
# From the repository root directory
docker build -t sqlgen-backend:rc backend
```

### Expected Output
The build output should run all steps and output a success status with a tagged image:
```text
DEPRECATED: The legacy builder is deprecated...
Sending build context to Docker daemon  240.2MB
Step 1/13 : FROM python:3.11-slim
 ---> ...
Successfully built 9a78de8f9021
Successfully tagged sqlgen-backend:rc
```

---

## 3. Run Smoke Test Container Local Execution

Validate container runtime behavior, port mapping, and startup configuration loading by executing the built image.

```bash
# Run the built container in detached mode mapping port 8000
docker run -d \
  --name sqlgen-backend-verify \
  -p 8000:8000 \
  -e NL2SQL_ENVIRONMENT=ci \
  -e NL2SQL_DEBUG_ENDPOINTS_ENABLED=true \
  -e NL2SQL_API_KEY=test_verification_key \
  sqlgen-backend:rc
```

### Expected Output
The command returns the container ID:
```text
3fa9b19dfb7d8b5a38a7c29676e102874ad8f902187f54c935408a280e77d24a
```

---

## 4. Query Health Endpoint

Verify endpoint connectivity, response format, and startup configuration diagnostic results.

```bash
# Run a HTTP GET request to local health route
curl -fsS http://localhost:8000/health
```

### Expected Output
The response must return a `200 OK` status and a valid JSON structure confirming the configurations were parsed correctly:
```json
{
  "status": "ok",
  "version": "0.1.0",
  "database": "SQLite ready",
  "config": {
    "environment": "ci",
    "debug_endpoints_enabled": true,
    "cors_origins_count": 1,
    "upload_dir_configured": false,
    "api_key_configured": true,
    "startup_warnings_count": 1,
    "startup_critical_warnings_count": 0
  }
}
```

Ensure that:
- `api_key_configured` is `true`.
- `startup_critical_warnings_count` is `0`.
- Raw secrets not exposed in the output.

---

## 5. Teardown Verification Resources

Clean up resources used during manual verification:

```bash
# Print container logs for review
docker logs sqlgen-backend-verify

# Stop and remove the test container
docker rm -f sqlgen-backend-verify
```
