# Production Smoke Checklist

This checklist must be executed as the final verification step of the release process. A smoke test is only considered successful if all checks pass.

## Smoke Test Steps

1. **Verify Liveness**
   - **Endpoint**: `/health`
   - **Expected**: `200 OK`
   - **Action**: Confirms the application process is running and responding.

2. **Verify Readiness and Configuration**
   - **Endpoint**: `/ready`
   - **Expected**: `200 OK`
   - **Action**: Confirms that there are no critical startup warnings. Specifically validates that `NL2SQL_API_KEY`, `NL2SQL_ENVIRONMENT`, and `NL2SQL_CORS_ALLOW_ORIGINS` are correctly configured.

3. **Backend CI green**
   - **Action**: Re-verify that the pipeline status for the deployed commit remains green.

4. **Rollback Condition**
   - If either `/health` or `/ready` returns a `503 Service Unavailable` or any other error, immediately trigger a rollback. Do not attempt to fix configuration issues on a live container. 
   - A `docker build` and `docker run` sequence must be fully re-executed for any subsequent fix after a rollback.
