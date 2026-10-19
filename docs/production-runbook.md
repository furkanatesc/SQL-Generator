# Production Runbook

This document details the deployment, configuration verification, and diagnostics interpretation for running the SQLGen backend in production environments.

---

## Supported Deployment Model

The current supported model for deploying the SQLGen backend is:
- **Docker Compose (recommended, Sprint 32.0)**: `docker-compose.prod.yml` runs the backend and the
  frontend images with persistent named volumes and healthchecks. See
  [Docker Compose (Production)](#docker-compose-production).
- **Docker container**: A standalone container image built using the official Dockerfile.
- **Single backend instance**: The application runs as a single process inside a single container
  (the embedded Qdrant store and SQLite are single-process; do not scale `backend` replicas).
- **Manual environment configuration**: Configured entirely via system environment variables.

### Not Supported Yet
The following deployment methods and technologies are **not supported**:
- Kubernetes orchestration (including custom Pods/Services)
- Helm chart deployments
- Amazon ECS or EKS
- Azure Container Apps or App Services
- Automated Docker registry publishing workflow (e.g. pushing to Docker Hub or ECR via CI)

---

## Docker Compose (Production)

`docker-compose.prod.yml` (repo root) is the production orchestration. It is **separate** from
`docker-compose.yml`, which only provides local/CI test databases with fixed test passwords.

| Service | Image | Port (host) | Notes |
| :--- | :--- | :--- | :--- |
| `backend` | `sqlgen-backend:${SQLGEN_IMAGE_TAG}` (built from `backend/`) | `${SQLGEN_BACKEND_PORT:-8000}` | non-root, `HEALTHCHECK` on `/health` |
| `frontend` | `sqlgen-frontend:${SQLGEN_IMAGE_TAG}` (built from `frontend/`) | `${SQLGEN_FRONTEND_PORT:-8080}` | non-root nginx serving the Vue SPA; starts after `backend` is healthy |

The compose file **pins** production-safe settings (`NL2SQL_ENVIRONMENT=production`,
`NL2SQL_DEBUG_ENDPOINTS_ENABLED=false`, `NL2SQL_UPLOAD_DIR=/app/uploads`) and **refuses to start**
when `SQLGEN_API_KEY_SECRET_FILE` or `NL2SQL_CORS_ALLOW_ORIGINS` is missing. Since Sprint 32.2 the API
key is a **Docker secret**: the host file is mounted at `/run/secrets/nl2sql_api_key` and read through
`NL2SQL_API_KEY_FILE`, so the key never appears in the container environment (`docker inspect`,
`/proc/*/environ`).

```bash
# 1. Configure (.env and secrets/ are gitignored — never commit them)
cp .env.prod.example .env
#    edit .env: NL2SQL_CORS_ALLOW_ORIGINS (JSON array, no "*"), optional NVIDIA_API_KEY
mkdir -p secrets && openssl rand -hex 32 > secrets/nl2sql_api_key
chmod 0444 secrets/nl2sql_api_key   # the container runs as a non-root user and must read it

# 2. Build and start; --wait blocks until both services report healthy
docker compose -f docker-compose.prod.yml up -d --build --wait

# 3. Smoke test
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/ready     # 200 only with production-safe config
curl -fsS http://localhost:8080/          # the SPA

# Logs / stop (keeps data) / upgrade
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml down
git pull && docker compose -f docker-compose.prod.yml up -d --build --wait
```

### Persistent state
| Named volume | Mounted at | Contents |
| :--- | :--- | :--- |
| `sqlgen_data` | `/app/data` | SQLite app DB (`SQLGEN_DB_PATH=/app/data/sqlgen.db`) and trace DB (`NL2SQL_TRACE_DB_PATH`) |
| `sqlgen_uploads` | `/app/uploads` | uploaded files |
| `sqlgen_qdrant` | `/app/qdrant_data` | embedded Qdrant vector store |

`docker compose down` keeps the volumes; **`down -v` deletes all data**. Use the backup CLI below
(Sprint 32.8); the raw `tar` of a volume shown next is only safe while the stack is stopped. Compose prefixes volume names
with the project name (by default the checkout directory, e.g. `sqlgen_sqlgen_data`; check with
`docker volume ls`): `docker run --rm -v sqlgen_sqlgen_data:/data -v "$PWD":/backup alpine tar czf
/backup/sqlgen_data.tgz -C /data .`

### Releases (Sprint 32.11)
A release is a version tag. `.github/workflows/release.yml` runs **only** for `v*.*.*` tags or a manual
dispatch:
1. **verify**: backend test suite and frontend build.
2. **publish**: builds and pushes `ghcr.io/<owner>/sqlgen-backend` and `sqlgen-frontend`, tagged `<version>`,
   `<major>.<minor>` and `sha-<commit>`. The backend image reports the version on `/health`.
3. **staging-smoke**: pulls the **published** images (no build) and runs them with the staging overlay. It
   checks `/health` (version), `/ready` (no failing component), the SPA, and that a job runs on the worker.
4. **github-release**: for tags only, creates a GitHub Release with generated notes.

```bash
git tag v1.1.0 && git push origin v1.1.0      # publishes images: an outward-facing step, done by a maintainer
```

**Deploy a released version** (no local build):
```bash
# .env: SQLGEN_IMAGE_REGISTRY=ghcr.io/<owner>/  SQLGEN_IMAGE_TAG=1.1.0   (docker login ghcr.io if the package is private)
C="docker compose -f docker-compose.prod.yml"
$C exec backend python -m app.backup create        # 32.8: back up first
$C pull && $C up -d --no-build --wait
```
**Roll back:** set `SQLGEN_IMAGE_TAG` to the previous version and `pull && up`. If the newer release ran
migrations, the older image reports `DB_SCHEMA_AHEAD`: restore the backup taken before the upgrade.

### Staging (Sprint 32.11)
`docker-compose.staging.yml` is an overlay for the production file. It uses a separate compose project
(`sqlgen-staging`: its own volumes and network) and `NL2SQL_ENVIRONMENT=production-staging`, so every
production safety check stays on. Create `.env.staging` from `.env.prod.example` with other ports (e.g.
`SQLGEN_BACKEND_PORT=8100`, `SQLGEN_FRONTEND_PORT=8180`), its own API-key file and the release to test:
```bash
S="docker compose --env-file .env.staging -f docker-compose.prod.yml -f docker-compose.staging.yml"
$S pull && $S up -d --no-build --wait
```

### Backup and restore (Sprint 32.8)
`python -m app.backup` writes one `.tar.gz` that contains:
- consistent snapshots of the app DB and the trace DB (SQLite online backup API, safe while running);
- the uploads;
- the embedded Qdrant store, as a **best-effort** file copy (it is mostly re-buildable by re-indexing);
- a `manifest.json` with schema versions and SHA-256 checksums.

```bash
C="docker compose -f docker-compose.prod.yml"
$C exec backend python -m app.backup create                 # -> /app/backups/sqlgen-backup-<UTC>.tar.gz
$C exec backend python -m app.backup list
$C exec backend python -m app.backup verify /app/backups/<archive>
$C cp backend:/app/backups/<archive> ./offsite/             # keep a copy OFF the host
$C exec backend python -m app.backup prune --keep 7

# Restore: stop writers first, restore in a one-off container, start again
$C stop backend worker
$C run --rm --no-deps backend python -m app.backup restore /app/backups/<archive> --yes [--include-qdrant]
$C up -d --wait
```

Restore checks the archive first (checksums, SQLite integrity, safe paths). It refuses a backup taken by a
newer release (newer schema). Before writing anything it takes a `pre-restore` safety backup of the current
state. Databases are written through the SQLite backup API. Uploads are overwritten but extra files are kept.
Qdrant is restored only with `--include-qdrant`. Schedule `create` + `prune` with the host's cron.

**Before migrations:** when a new release has pending migrations, the backend first copies the app DB to
`/app/data/sqlgen.db.pre-v<N>-<ts>.bak` (`NL2SQL_BACKUP_BEFORE_MIGRATION`, last 3 kept).

### Secrets (Sprint 32.2)
- **Rotate the API key:** overwrite `secrets/nl2sql_api_key`; the file is re-read on every request, so
  no restart is needed. If `/ready` reports `API_KEY_ENV_SHADOWED`, a key stored in the database config
  (`POST /api/configs/api_key`) takes precedence and must be changed or removed as well.
- **LLM key as a secret:** `NVIDIA_API_KEY` stays an optional env value in the compose file (an optional
  secret file cannot be expressed in compose). To use a file instead, add a `docker-compose.override.yml`
  that declares a `nvidia_api_key` secret, lists it under `backend.secrets` and sets
  `NVIDIA_API_KEY_FILE: /run/secrets/nvidia_api_key`.
- A configured but unreadable/empty secret file raises the critical `SECRET_FILE_UNREADABLE`
  (`/ready` 503) and is **not** silently replaced by the env value.

### Logs (Sprint 32.9)
Backend and worker write **one JSON object per line** to stderr (`NL2SQL_LOG_FORMAT=json`, level
`NL2SQL_LOG_LEVEL`). Every line has `ts`, `level` and `logger`. Lines written while serving a request carry
`request_id` (the same value as the `X-Request-ID` response header). Lines written while running a job carry
`job_id` and the originating `request_id`. Request events (`"event": "http_request"`, `http_error`,
`slow_request`) have their fields at the top level. Secrets are redacted: `api_key=`, `token=`, `sk-…`,
`nvapi-…` and the configured secret values.

```bash
C="docker compose -f docker-compose.prod.yml"
$C logs -f backend worker
$C logs --no-log-prefix backend | grep '"request_id": "<id>"'      # follow one request
$C logs --no-log-prefix worker  | grep '"job_id": "<job id>"'      # follow one job
```

Before 32.9 the API process had no logging configuration, so INFO logs (including every `http_request`
event) were silently dropped. `uvicorn.access` is now WARNING-only because `http_request` replaces it.
Shipping logs to Loki or ELK is the platform's job (stdout/stderr of the containers).

### LLM failover (Sprint 32.10)
SQL generation uses a **model chain**: the configured `llm_model` first, then `NL2SQL_LLM_FALLBACK_MODELS`
(e.g. `meta/llama-3.1-70b-instruct,nvidia/llama-3.1-nemotron-70b-instruct`) on the same NVIDIA NIM endpoint
and key.
- A call moves to the next model when the current one fails transiently (429/5xx/network, after the client's
  own retries) or is unavailable (400/404). On 401/403 it does **not** fail over: fix the key.
- After `NL2SQL_LLM_CIRCUIT_FAILURES` consecutive failures a model's circuit **opens** and the model is
  skipped for `NL2SQL_LLM_CIRCUIT_RESET_SECONDS`. After that it gets one trial call.
- If every circuit is open, the model that reopens soonest is still tried.
- Circuits are kept per process (API and each worker).
- Inspect: `GET /api/v1/admin/llm` (chain, state, failures, retry-in).
- `/ready` reports `checks.llm = degraded (llm_circuits_open)` while every circuit is open.
- Failover events are logged by `app.llm.failover` with the job's `job_id`.
- Job-level retries (32.5) still apply when the whole chain fails.

### Rate limits (Sprint 32.6)
The compose file turns on per-client API limits: `NL2SQL_RATE_LIMIT_REQUESTS_PER_MINUTE=300` for all requests
and `NL2SQL_RATE_LIMIT_JOBS_PER_MINUTE=20` for job creation. A client is its API key (hashed) or its IP. Over
the limit, the API returns **429** with `{"error": {"code": "RATE_LIMITED", ...}}` and a `Retry-After` header;
normal responses carry `X-RateLimit-Limit` / `X-RateLimit-Remaining`. Probes (`/health`, `/ready`) are
exempt. The limits are kept in memory per API process and reset on restart. LLM calls are separately
throttled per process (API or worker) by `NL2SQL_LLM_REQUESTS_PER_MINUTE` / `NL2SQL_LLM_BURST`; across
workers, use `NL2SQL_JOB_MAX_CONCURRENT` (32.5) as the global brake.

### Job worker (Sprint 32.4)
NL→SQL jobs run in the separate `worker` service; the backend runs with `NL2SQL_JOB_EXECUTION_MODE=worker`,
so it only writes `pending` jobs. The worker claims them from the shared app database (claims are atomic),
sends a heartbeat while a job runs, and writes every log line to the `job_logs` table, where the API's SSE
stream (`/api/jobs/{id}/stream`) reads it.

- **Scale:** `docker compose -f docker-compose.prod.yml up -d --scale worker=3`. All workers must share
  one host, because the database is SQLite on a local volume.
- **Restart / crash:** a `processing` job whose heartbeat is older than `NL2SQL_JOB_STALE_SECONDS`
  (default 300 s) is marked `failed` ("worker stopped before completion"). It is not retried
  (retries → Sprint 32.5). On SIGTERM the worker finishes its current job first (`stop_grace_period: 60s`).
- **Retries and dead-letter (Sprint 32.5):** a job retries only on transient failures: every LLM call
  failed upstream, or its worker stopped heartbeating. It retries with exponential backoff
  (`NL2SQL_JOB_RETRY_BACKOFF_SECONDS`, capped at 900 s) up to `NL2SQL_JOB_MAX_ATTEMPTS`; after that it is
  `failed` with a `dead_lettered_at` marker. Deterministic failures (invalid SQL, schema or input errors, a
  missing LLM key) fail at once. Inline mode never retries.
- **Priority / concurrency:** `POST /api/jobs/without-file` accepts `"priority"` from -10 to 10 (higher runs
  first). `NL2SQL_JOB_MAX_CONCURRENT` caps how many jobs run at once across all workers.
- **Operate the queue:**
  ```bash
  curl -H "X-API-Key: $KEY" http://localhost:8000/api/v1/admin/queue                    # counts, retries, dead letters, oldest pending
  curl -X POST -H "X-API-Key: $KEY" http://localhost:8000/api/v1/admin/jobs/<id>/requeue  # failed -> pending, attempts reset
  ```
- **Health:** `python -m app.jobs.worker healthcheck` (the compose healthcheck) checks that the worker loop
  ran in the last 180 s. If the backend reports `JOB_QUEUE_STALLED`, check `docker compose logs worker`.
- **LLM key:** the worker needs `NVIDIA_API_KEY` (or a key stored via the config API) just like the
  backend did.

### Database migrations (Sprint 32.3)
The backend applies pending schema migrations to the app and trace databases on every start and records
them in `schema_migrations`. Check them with:

```bash
docker compose -f docker-compose.prod.yml exec backend python -m app.migrations status
```

**Upgrading:** take a backup first (`python -m app.backup create`, see *Backup and restore*), then
`up -d --build`; the backend also copies the app DB automatically before migrating it.
**Rolling back to an older image** after an upgrade that added migrations gives `DB_SCHEMA_AHEAD`
(`/ready` 503). Restore the pre-upgrade backup or run the newer image again. Details:
`docs/database-migrations.md`.

### Frontend → backend
The SPA calls the backend at `http://<browser host>:8000` by default. If `SQLGEN_BACKEND_PORT` is not
`8000`, or the backend is on another host, set the backend URL and API key in the UI settings. Add the
frontend's origin (e.g. `http://sqlgen.example.com:8080`) to `NL2SQL_CORS_ALLOW_ORIGINS`.

### Known limitations (Sprint 32.0)
No TLS termination or single-origin reverse proxy, no external secret store (Vault / cloud secret
managers; see §38), no automated server deploy (releases publish images to GHCR; deploying is an operator step, §47), and
the schema cache file (`/app/schema_cache.json`) is not persisted (it is rebuilt on demand). See
`docs/TECH-DEBT.md` §36.

The CI job `prod-compose-smoke` (`.github/workflows/backend-ci.yml`) boots this stack on every PR and
checks `/health`, `/ready`, the SPA, and that data survives recreating the backend container.

---

## Container Startup Example

To build and run the backend container locally, execute the following commands:

```bash
# 1. Build the Docker image from the root directory
docker build -t sql-generator-backend backend

# 2. Run the container with required environment variables
docker run \
  -p 8000:8000 \
  -e NL2SQL_API_KEY=xxxxx \
  sql-generator-backend

# Or keep the key out of the environment (Sprint 32.2):
docker run \
  -p 8000:8000 \
  -v "$PWD/secrets/nl2sql_api_key:/run/secrets/nl2sql_api_key:ro" \
  -e NL2SQL_API_KEY_FILE=/run/secrets/nl2sql_api_key \
  sql-generator-backend
```

---

## Local Smoke Test

Once the container is running, verify that the application has started and is responsive by querying the health endpoint:

```bash
curl -fsS http://localhost:8000/health
```

### Expected Response Format
A healthy service will return a `200 OK` status code with a JSON body matching the following structure:

```json
{
  "status": "ok",
  "version": "0.1.0",
  "database": "SQLite ready",
  "config": {
    "environment": "local",
    "debug_endpoints_enabled": true,
    "cors_origins_count": 1,
    "upload_dir_configured": false,
    "api_key_configured": true,
    "startup_warnings_count": 1,
    "startup_critical_warnings_count": 0
  }
}
```

---

## Health Diagnostics Interpretation

The `config` object in the health response provides safe, structured metadata regarding the current application runtime configuration. 

### Diagnostics Fields

- **`environment`**: The runtime environment label (e.g. `production`, `prod-eu`, `ci`, `local`). Used to determine if the application is running in a production-like environment.
- **`debug_endpoints_enabled`**: A boolean indicating if development/debugging API routes (e.g., direct sandbox execution) are exposed.
- **`cors_origins_count`**: The number of allowed CORS origins registered in the system settings.
- **`upload_dir_configured`**: A boolean indicating if a custom directory has been explicitly configured for storage (if `false`, the system falls back to default uploads path).
- **`api_key_configured`**: A boolean indicating if a API Key is active (configured either through the database settings table or environment variable fallback).
- **`startup_warnings_count`**: The total number of configuration-level warnings detected during startup validation checks.
- **`startup_critical_warnings_count`**: The number of warnings flagged with a `critical` severity.

### Security and Secret Sizing
To prevent unauthorized information exposure, the health endpoint strictly adheres to these security rules:
- **Raw API keys** are never returned.
- **Raw upload paths** are never returned.
- **Raw CORS allowed origins lists** are never returned.

---

## Readiness Components (Sprint 32.7)

`/ready` also returns `checks`, one entry per component: `{"status": "ok" | "degraded" | "fail", "reason": <code> | null}`.
Any `fail` makes `/ready` return 503. `degraded` never does. Reasons are fixed codes (usually a startup
warning code in lower case), never paths or values.

| Component | `fail` when | `degraded` when |
| :--- | :--- | :--- |
| `database` | `SELECT 1` fails (`unreachable`) | — |
| `migrations` | `db_migrations_pending`, `db_schema_ahead` | — |
| `api_key` | `api_key_not_configured`, `api_key_insecure_default` | `api_key_env_shadowed` |
| `secrets` | `secret_file_unreadable` | `secret_source_conflict` |
| `upload_dir` | `upload_dir_not_writable`, `upload_dir_not_found` | — |
| `job_queue` | — | `job_queue_stalled` |
| `disk` | free space < `NL2SQL_HEALTH_MIN_FREE_DISK_MB` (`low_disk_space`) | < 2× that (`disk_space_low_soon`) |
| `llm` | — | no LLM key configured (`llm_key_not_configured`): jobs will fail; every model circuit open (`llm_circuits_open`) |
| `config` | any other critical warning (e.g. `cors_wildcard_in_production`) | any other warning (e.g. `unknown_config_env_var`) |

```bash
curl -s http://localhost:8000/ready | python3 -m json.tool
```

The worker container's healthcheck (`python -m app.jobs.worker healthcheck`) passes only when the worker
loop ran recently **and** the app database is reachable.

---

## Startup Warning Interpretation

Startup configuration validation checks are executed during application boot to identify misconfigurations.

> [!IMPORTANT]
> All startup warnings are **warning-only** and **non-fatal**. The application server startup will always proceed even if there are critical warnings.

### Warning Scenarios

- **`API_KEY_NOT_CONFIGURED`**
  - *Severity*: `critical`
  - *Trigger*: No API key is found in the database settings, `NL2SQL_API_KEY_FILE` or `NL2SQL_API_KEY`.
  - *Action*: Ensure a valid API key is set in the environment or database.

- **`API_KEY_INSECURE_DEFAULT`** (Sprint 32.0)
  - *Severity*: `critical`
  - *Trigger*: In a production-like environment, the active API key (the DB config key, which takes
    precedence, otherwise `NL2SQL_API_KEY`) is the public local-development default. Production-like
    environments no longer seed that default into a fresh database; an older database may still hold it.
  - *Action*: Set a strong `NL2SQL_API_KEY`; if the DB still holds the dev default, replace it via
    `POST /api/configs/api_key`.

- **`SECRET_FILE_UNREADABLE`** (Sprint 32.2)
  - *Severity*: `critical`
  - *Trigger*: `NL2SQL_API_KEY_FILE` or `NVIDIA_API_KEY_FILE` is set but the file is missing, unreadable
    (e.g. permissions for the non-root container user), empty or larger than 64 KiB. The secret is then
    treated as not configured — there is no fallback to the plain env variable.
  - *Action*: Fix the file / its mode (`chmod 0444`); the message names the variable only.

- **`SECRET_SOURCE_CONFLICT`** (Sprint 32.2)
  - *Severity*: `warning`
  - *Trigger*: Both `<NAME>` and `<NAME>_FILE` are set; the file wins.
  - *Action*: Remove the plain env variable.

- **`API_KEY_ENV_SHADOWED`** (Sprint 32.2)
  - *Severity*: `warning`
  - *Trigger*: The database config holds an API key that differs from the env/file key; the database key
    wins (`verify_api_key`), so rotating the env/file secret has no effect.
  - *Action*: Change or remove the database key via the config API.

- **`DB_MIGRATIONS_PENDING`** (Sprint 32.3)
  - *Severity*: `critical`
  - *Trigger*: The app or trace database still has pending migrations after start-up, which means a
    migration failed and was rolled back. The database stays at its last good version.
  - *Action*: Check the backend logs for the failing migration, fix the cause, then restart or run
    `python -m app.migrations upgrade`.

- **`DB_SCHEMA_AHEAD`** (Sprint 32.3)
  - *Severity*: `critical`
  - *Trigger*: The database schema version is newer than the running release supports, usually after
    rolling back to an older image. No migrations are applied.
  - *Action*: Run the newer image, or restore the backup taken before the upgrade.

- **`JOB_QUEUE_STALLED`** (Sprint 32.4)
  - *Severity*: `warning` (does not fail `/ready`)
  - *Trigger*: In worker mode, at least one job has been due (`pending`, not waiting for a retry backoff)
    for longer than `NL2SQL_JOB_STALE_SECONDS`;
    no worker seems to be claiming jobs.
  - *Action*: Check that the `worker` service is running and healthy (`docker compose ps`,
    `docker compose logs worker`).

- **`UNKNOWN_CONFIG_ENV_VAR`** (Sprint 32.1)
  - *Severity*: `warning` (does not fail `/ready`)
  - *Trigger*: The process environment contains an `NL2SQL_*` variable that is not in the
    environment contract (`backend/app/config_contract.py`) — usually a typo that the application
    would otherwise ignore silently.
  - *Action*: Fix the variable name (see `docs/env-contract.md`); the message lists the names only.

- **`CORS_WILDCARD_IN_PRODUCTION`**
  - *Severity*: `critical`
  - *Trigger*: Allowed CORS origins includes wildcard (`*`) while running in a production-like environment (e.g. environment starts with `prod` or `production`).
  - *Action*: Configure specific domains in the allowed CORS origins settings to secure the API.

- **`DEBUG_ENDPOINTS_ENABLED_IN_PRODUCTION`**
  - *Severity*: `critical`
  - *Trigger*: Debug endpoints are enabled (`NL2SQL_DEBUG_ENDPOINTS_ENABLED=true`) while running in a production-like environment.
  - *Action*: Disable debug endpoints in production environments.

- **`UPLOAD_DIR_DEFAULT`**
  - *Severity*: `info`
  - *Trigger*: No custom upload directory path is configured via `NL2SQL_UPLOAD_DIR`.
  - *Action*: Informational only; the application will fall back to using `/app/uploads` locally.
