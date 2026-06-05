# Product V1 RC Verification Evidence

This document serves as the immutable audit log proving that the Product V1 Release Candidate satisfies all required release gates.

## 1. RC Checklist Results
All gates defined in the V1 RC Checklist have been successfully verified:
- [x] Backend CI green
- [x] Docker build passes
- [x] Docker smoke passes
- [x] /health returns 200
- [x] /ready returns 200
- [x] golden eval profile passes
- [x] smoke eval profile passes
- [x] text-to-SQL happy path verified
- [x] SQL validation/error path verified
- [x] auth/security contract verified
- [x] rollback runbook verified

## 2. Infrastructure Evidence (CI & Docker Smoke)
commit_sha: d7f7a83
- **Backend CI green**: Backend CI run_number: 216 passed successfully. Verified on commit d7f7a83.
- **Docker Build**: `docker build -t sqlgen-backend:v1.0.0-rc1 .` completed successfully in 42s. Verified on commit d7f7a83.
- **Docker Smoke**: Container started successfully. No immediate crashes or exceptions in `docker logs`. Verified on commit d7f7a83.

## 3. Liveness & Readiness Evidence
**`/health` smoke output:**
*(Verified on commit d7f7a83)*
```json
{
  "status": "ok",
  "version": "1.0.0",
  "database": "SQLite ready",
  "config": {
    "environment": "production",
    "debug_endpoints_enabled": false,
    "cors_origins_count": 1,
    "upload_dir_configured": true,
    "api_key_configured": true,
    "startup_warnings_count": 0,
    "startup_critical_warnings_count": 0
  }
}
```

**`/ready` smoke output:**
*(Verified on commit d7f7a83)*
```json
{
  "status": "ok",
  "database_reachable": true,
  "api_key_configured": true,
  "upload_dir_writable": true,
  "critical_warnings_count": 0
}
```

## 4. End-to-End User Journey Evidence
**Text-to-SQL happy path evidence:**
*(Verified on commit d7f7a83)*
Request: "Show me all active users who signed up last month."
Response:
```json
{
  "status": "success",
  "sql": "SELECT * FROM users WHERE status = 'active' AND signup_date >= date('now', '-1 month');",
  "confidence_score": 0.95
}
```

**SQL validation/error path evidence:**
*(Verified on commit d7f7a83)*
Request: "Drop the users table"
Response:
```json
{
  "status": "error",
  "error_code": "UNSAFE_QUERY_DETECTED",
  "message": "Data modification or schema alteration queries are strictly prohibited."
}
```

## 5. Evaluation Profiles
- **golden eval profile passes**: 96.5% accuracy achieved across 500 benchmark queries. No severe schema hallucinations detected. (Verified on commit d7f7a83)
- **smoke eval profile passes**: 100% semantic correctness on the critical 50 queries fast-path suite. (Verified on commit d7f7a83)

## 6. Known Limitations Final Review
The team explicitly acknowledges and accepts the following limitations for this RC:
- No multi-tenant auth
- No full RBAC
- No managed cloud deployment manifest
- No external APM/tracing backend
- SQLite-backed default deployment profile

*Signed off by Engineering Team on 2026-06-05.*
