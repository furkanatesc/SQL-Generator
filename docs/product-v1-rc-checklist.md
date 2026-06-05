# Product V1 Release Candidate Checklist

This document serves as the final gateway before declaring a V1 Release Candidate (RC) ready for production deployment. Every single item must be checked off.

## 1. Infrastructure Gates
- [ ] **Backend CI green**: The CI pipeline for the target branch must pass without any errors.
- [ ] **Docker build passes**: The immutable container artifact must build successfully from scratch.
- [ ] **Docker smoke passes**: The newly built container must start without immediately crashing.

## 2. Liveness & Readiness Gates
- [ ] **/health returns 200**: The basic liveness endpoint must respond with a 200 OK.
- [ ] **/ready returns 200**: The configuration validation endpoint must respond with a 200 OK, ensuring no critical startup warnings exist.

## 3. Eval Gates
- [ ] **golden eval profile passes**: The system must achieve expected accuracy thresholds against the primary golden dataset.
- [ ] **smoke eval profile passes**: The fast smoke evaluation suite must complete without regressions.

## 4. End-to-End User Journey Verification
- [ ] **text-to-SQL happy path verified**: A standard natural language query must successfully translate to valid SQL and execute without error.
- [ ] **SQL validation/error path verified**: Invalid or ambiguous natural language queries must be caught, producing clear user-facing errors rather than silent failures.

## 5. Security & Operations
- [ ] **auth/security contract verified**: The API key enforcement and CORS origin restrictions must behave exactly as defined in the configuration.
- [ ] **rollback runbook verified**: The documented rollback procedure (stopping the container and restarting the previous image tag) must be actively validated.
