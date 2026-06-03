# API Contract Snapshots & Reviewer Runbook

This directory contains deterministic snapshots used to freeze backend API interfaces, response structures, and security behaviors before promoting releases.

---

## Snapshot Coverage

### 1. `openapi_snapshot.json`
- **What it protects**: Public route paths, HTTP methods, and their mapping to operation IDs.
- **Why it matters**: Prevents accidental endpoint additions or deletions that could expose debug routes or break frontend clients.

### 2. `schema_contract_snapshot.json`
- **What it protects**: Response envelope structure, property names, and `required` list of fields across all API schemas.
- **Why it matters**: Prevents property renaming or field omissions that would silently break frontend JSON parsing.

### 3. `status_contract_snapshot.json`
- **What it protects**: HTTP status code semantics for critical API workflows (e.g. missing API keys, nonexistent resources, validation failures, and health).
- **Why it matters**: Crucial for client retry logic, frontend redirection, and production monitoring/alerting dashboards.

---

## When to Update Snapshots

Snapshots must only be updated when **intentional, approved changes** are introduced to the API contracts. 

To regenerate snapshots, run:
```bash
cd backend
python scripts/generate_contract_snapshots.py
```

---

## Reviewer Guardrails & PR Requirements

> [!WARNING]
> Updating contract snapshots *just to get the tests to pass* is **strictly forbidden**. This practice, known as "blind blessing", bypasses the entire safety net and hides regression bugs.

### PR Requirements
Any PR that modifies a contract snapshot **must** include:
1. **Clear Rationale**: Explicit explanation in the PR body explaining why the contract is changing (e.g., adding a new feature, updating error models).
2. **Intentional Scope Check**: Demonstration that the snapshot diff matches only the expected code changes.

### Reviewer Checklist
When reviewing a PR with snapshot changes, you must verify:
- [ ] Is the API change fully intentional and documented?
- [ ] Are the changes in the JSON snapshot strictly limited to the PR scope?
- [ ] Did you confirm that no raw secrets or debug endpoints were accidentally exposed?
- [ ] Are frontend teams notified if the contract changes break compatibility?
