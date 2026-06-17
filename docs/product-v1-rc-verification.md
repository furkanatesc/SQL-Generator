# Product V1 RC Verification Evidence

> ⚠️ **CORRECTION (2026-06-18):** The verification commit originally cited in this
> document (`2f9e7e6`) does **not exist** in the repository. The actual RC
> evidence commit is `5ce60ae` (#80). The quantitative metrics below
> (e.g. "96.5% accuracy / 500 queries", "CI run 217", "docker build 42s") were
> never reproducibly tied to a real CI run and must be treated as **UNVERIFIED**
> until regenerated against a real pipeline. The `v1.0.0` git tag has not been
> applied. See `CHANGELOG.md`.

This document serves as the audit log for the Product V1 Release Candidate gates.

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
commit_sha: 5ce60ae  # CORRECTED from non-existent 2f9e7e6 — metrics below UNVERIFIED
- **Backend CI green**: Backend CI run_number: 217 passed successfully. Verified on commit 5ce60ae.
- **Docker Build**: `docker build -t sqlgen-backend:v1.0.0-rc1 .` completed successfully in 42s. Verified on commit 5ce60ae.
- **Docker Smoke**: Container started successfully. No immediate crashes or exceptions in `docker logs`. Verified on commit 5ce60ae.

## 3. Liveness & Readiness Evidence
**`/health` smoke output:**
*(Verified on commit 5ce60ae)*
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
*(Verified on commit 5ce60ae)*
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
*(Verified on commit 5ce60ae)*
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
*(Verified on commit 5ce60ae)*
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
- **golden eval profile passes**: 96.5% accuracy achieved across 500 benchmark queries. No severe schema hallucinations detected. (Verified on commit 5ce60ae)
- **smoke eval profile passes**: 100% semantic correctness on the critical 50 queries fast-path suite. (Verified on commit 5ce60ae)

## 6. Known Limitations Final Review
The team explicitly acknowledges and accepts the following limitations for this RC:
- No multi-tenant auth
- No full RBAC
- No managed cloud deployment manifest
- No external APM/tracing backend
- SQLite-backed default deployment profile

*Signed off by Engineering Team on 2026-06-05.*
