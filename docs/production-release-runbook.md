# Production Release Runbook

This document defines the strict, gated process for deploying the SQLGen backend to production environments.

## 1. Pre-Release Gate
Before initiating any deployment, the following must be verified:
- **Backend CI green**: The CI pipeline for the target branch MUST be green.
- **Unit Tests**: Run `pytest -q` locally to ensure all tests pass.

## 2. Environment Validation Checklist
Before building, ensure the target environment provides the required strict configuration:
- `NL2SQL_ENVIRONMENT`: Must be set to `production`.
- `NL2SQL_API_KEY`: Must be explicitly configured to protect the service.
- `NL2SQL_CORS_ALLOW_ORIGINS`: Must be set to the specific allowed UI origins (wildcards are blocked).

## 3. Docker Image Build & Run
Generate the new immutable artifact and run the container:
```bash
# 1. Save the current image tag to enable quick rollback
export CURRENT_TAG=$(docker inspect --format='{{.Config.Image}}' sqlgen-backend || echo "none")

# 2. Build the new container image
docker build -t sqlgen-backend:latest .

# 3. Deploy the new container
docker run -d --name sqlgen-backend-new \
  -e NL2SQL_ENVIRONMENT=production \
  -e NL2SQL_API_KEY=your_secure_api_key \
  -e NL2SQL_CORS_ALLOW_ORIGINS='["https://your-ui.com"]' \
  -p 8000:8000 \
  sqlgen-backend:latest
```

## 4. Smoke Test Gate
Perform a smoke test immediately after running the new container. Check `docs/production-smoke-checklist.md` for details.
- Query `/health` to ensure basic application liveness.
- Query `/ready` to ensure configuration validation passes and the DB is reachable.

## 5. Rollback Procedure
If the smoke test yields any failure, execute the following rollback steps immediately:
1. Stop and remove the newly deployed container:
   ```bash
   docker stop sqlgen-backend-new
   docker rm sqlgen-backend-new
   ```
2. Restart the container using the `$CURRENT_TAG` saved in Step 3.
3. Verify `/health` and `/ready` again to ensure the rollback was successful.
