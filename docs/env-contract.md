# Environment Variable Contract

This document specifies the environment variable interface for the SQLGen backend, including requirements, defaults, and security configurations.

Most configuration variables are prefixed with `NL2SQL_` and are loaded via `pydantic-settings` (case-insensitive) from system environment variables or a local `.env` file; a few are read directly with `os.getenv` (marked *direct* below).

> **Single source of truth (Sprint 32.1):** the machine-readable inventory is
> `backend/app/config_contract.py` (`ENV_CONTRACT`, version `v1`). This document is its
> operator-facing view. `backend/tests/test_env_config_contract.py` fails CI when a variable is read
> in code but missing from the contract, when a `Settings` field and the contract diverge, when a
> contract variable is missing here, or when a production-required variable is not pinned/required in
> `docker-compose.prod.yml`.

---

## Required in Production

These have no safe default for production and must be set explicitly (the production compose
file pins or requires all four; the API key is supplied as a Docker secret via `NL2SQL_API_KEY_FILE`):

| Variable | Production value |
| :--- | :--- |
| **`NL2SQL_ENVIRONMENT`** | `production` (or another production-like value) |
| **`NL2SQL_API_KEY`** | a strong random key (*direct*, secret) — in production via `NL2SQL_API_KEY_FILE` |
| **`NL2SQL_CORS_ALLOW_ORIGINS`** | JSON array of trusted origins, no `*` |
| **`NL2SQL_DEBUG_ENDPOINTS_ENABLED`** | `false` |

## Required Variables

| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| **`NL2SQL_API_KEY`** | Conditionally | *None* | API key clients send as `X-API-Key`; fallback when no key is stored in the database config (*direct*, secret). |

### API Key Resolution Priority
The application resolves the active API Key in the following order of precedence:
1. **Database Configuration**: Checked first. If a key exists in the database settings table (`config.api_key`), it is used.
2. **Secret file / environment fallback**: Checked second. If no key is configured in the database, the
   secret resolver (see *Secrets* below) reads `NL2SQL_API_KEY_FILE`, else `NL2SQL_API_KEY`.

If no API key is resolved by either method, a critical validation warning is generated. If both a
database key and an env/file key exist and differ, `API_KEY_ENV_SHADOWED` (severity `warning`) reports
that rotating the env/file secret has no effect until the database key is changed or removed.

**Development default (Sprint 32.0):** outside production-like environments a fresh database is seeded
with a public development key, which therefore shadows `NL2SQL_API_KEY`. Production-like environments
do **not** seed it, so `NL2SQL_API_KEY` is the active key; if the active key is still the development
default in production, the critical warning `API_KEY_INSECURE_DEFAULT` is raised (`/ready` returns 503).

---

## Secrets (Sprint 32.2)

Every contract secret (`NL2SQL_API_KEY`, `NVIDIA_API_KEY`) is read through one resolver,
`backend/app/secret_resolver.py`, and can be supplied in two ways:

| Variable | Description |
| :--- | :--- |
| **`NL2SQL_API_KEY_FILE`** | Path of a file holding `NL2SQL_API_KEY` (Docker secrets convention, e.g. `/run/secrets/nl2sql_api_key`). |
| **`NVIDIA_API_KEY_FILE`** | Path of a file holding `NVIDIA_API_KEY`. |

Rules:
- `<NAME>_FILE` wins over `<NAME>`. Surrounding whitespace / the trailing newline is stripped; files
  larger than 64 KiB are rejected.
- If `<NAME>_FILE` is set but the file is missing, unreadable, empty or too large, the secret is
  treated as **not configured** — there is no silent fallback to `<NAME>` — and the critical warning
  `SECRET_FILE_UNREADABLE` is raised (`/ready` returns 503).
- If both `<NAME>` and `<NAME>_FILE` are set, `SECRET_SOURCE_CONFLICT` (severity `warning`) is raised.
- The file is re-read on every use, so a rotated secret takes effect without a restart.
- Warnings name the variable only, never the value or the file path. File-based values are also added
  to the trace/result redaction set.

---

## Optional Variables

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| **`NL2SQL_ENVIRONMENT`** | String | `local` | The deployment environment name (e.g. `local`, `ci`, `production`, `prod-eu`). |
| **`NL2SQL_UPLOAD_DIR`** | String | *None* | Absolute path to the custom directory used for storing uploaded files. |
| **`NL2SQL_CORS_ALLOW_ORIGINS`** | JSON Array | `["*"]` | List of allowed CORS origins to inject into the CORS middleware. |
| **`NL2SQL_DEBUG_ENDPOINTS_ENABLED`** | Boolean | `true` | Expose developer-only API endpoints for direct debugging/tracing. |
| **`SQLGEN_DB_PATH`** | String | `<backend>/sqlgen.db` | Path of the SQLite application database (no `NL2SQL_` prefix; read directly by `app/database.py`). |
| **`NL2SQL_TRACE_DB_PATH`** | String | `data/nl2sql_traces.db` | Path of the SQLite trace database (relative paths resolve against the working directory). |
| **`NVIDIA_API_KEY`** | String | *None* | LLM / embedding provider key fallback (can also be set at runtime via the config API; *direct*, secret). |
| **`NL2SQL_CORS_ALLOW_CREDENTIALS`** | Boolean | `true` | CORS allow-credentials flag. |
| **`NL2SQL_CORS_ALLOW_METHODS`** | JSON Array | `["*"]` | Allowed CORS methods. |
| **`NL2SQL_CORS_ALLOW_HEADERS`** | JSON Array | `["*"]` | Allowed CORS headers. |
| **`NL2SQL_APP_NAME`** | String | `SQLGen API` | API title shown in OpenAPI. |
| **`NL2SQL_APP_VERSION`** | String | `0.1.0` | Version reported by `/health`. |
| **`NL2SQL_APP_DESCRIPTION`** | String | *(built-in)* | API description shown in OpenAPI. |

### Unknown `NL2SQL_*` variables (Sprint 32.1)

`Settings` ignores variables it does not know, so a typo (e.g. `NL2SQL_DEBUG_ENDPOINT_ENABLED`) would be
silently dropped. Startup validation now reports any process-environment `NL2SQL_*` name that is not
in the contract as `UNKNOWN_CONFIG_ENV_VAR` (severity `warning`: logged and counted in diagnostics, but
it does not fail `/ready`). Only names are reported, never values. Keys in a `.env` file are not
checked.

### Test-harness variables (not part of the runtime contract)

`POSTGRES_TEST_*`, `MYSQL_TEST_*`, `ORACLE_TEST_*` and `MSSQL_TEST_*` configure the local/CI
integration databases (`app/evaluation/*_connection_resolver.py`, `mssql_seed.py`). They are
deliberately excluded from the contract and are never needed in production.

### Production Docker Compose (Sprint 32.0)

`docker-compose.prod.yml` pins `NL2SQL_ENVIRONMENT=production`, `NL2SQL_DEBUG_ENDPOINTS_ENABLED=false`,
`NL2SQL_UPLOAD_DIR=/app/uploads`, `SQLGEN_DB_PATH=/app/data/sqlgen.db` and
`NL2SQL_TRACE_DB_PATH=/app/data/nl2sql_traces.db` (all on named volumes), and **requires**
`NL2SQL_CORS_ALLOW_ORIGINS` (compose refuses to start without it). Since Sprint 32.2 the API key is a
Docker secret: compose pins `NL2SQL_API_KEY_FILE=/run/secrets/nl2sql_api_key` and **requires**
`SQLGEN_API_KEY_SECRET_FILE` (host path of the key file, readable by the container's non-root user,
e.g. mode `0444`); `NL2SQL_API_KEY` is no longer passed as an env value. Compose-only
variables: `SQLGEN_API_KEY_SECRET_FILE`, `SQLGEN_BACKEND_PORT` (default `8000`), `SQLGEN_FRONTEND_PORT`
(default `8080`), `SQLGEN_IMAGE_TAG` (default `latest`). Every variable it references is documented in
`.env.prod.example` (enforced by `backend/tests/test_prod_compose_contract.py`).

---

## Safe Defaults

- **Upload Directory**: If `NL2SQL_UPLOAD_DIR` is not explicitly set (leaves the setting as *None*), the application defaults to using local storage directories. For production deployments inside the Docker container, the environment is configured to use `/app/uploads` via the Docker runtime setup.
- **Environment**: If `NL2SQL_ENVIRONMENT` is not configured, it default-initializes to `local`, which enables standard developer friendliness flags (such as debug endpoints and relaxed CORS policies).

---

## Dangerous Configurations

The application performs startup validation checks to prevent insecure or dangerous setups in production-like environments. An environment is considered **production-like** if `NL2SQL_ENVIRONMENT` is set to `production`, `prod`, or starts with `production-` / `prod-` (case-insensitive).

The following configurations will generate startup warnings:

### 1. Wildcard CORS in Production
- **Condition**: Running in a production-like environment with `NL2SQL_CORS_ALLOW_ORIGINS` containing the wildcard `*` (default value).
- **Warning Code**: `CORS_WILDCARD_IN_PRODUCTION` (Severity: `critical` — `/ready` returns 503)
- **Remediation**: Set `NL2SQL_CORS_ALLOW_ORIGINS` to a JSON array of specific trusted domains, e.g., `["https://sqlgen.mycompany.com"]`.

### 2. Debug Endpoints Enabled in Production
- **Condition**: Running in a production-like environment with `NL2SQL_DEBUG_ENDPOINTS_ENABLED` set to `true` (default value).
- **Warning Code**: `DEBUG_ENDPOINTS_ENABLED_IN_PRODUCTION` (Severity: `critical` — `/ready` returns 503)
- **Remediation**: Set `NL2SQL_DEBUG_ENDPOINTS_ENABLED=false` in the production environment variables.

---

## Startup Warn-Only Behavior
All configuration warnings are non-fatal. The application server will always complete its startup successfully to allow read-only or diagnostic operations even under misconfigurations. `critical` warnings do, however, make the readiness probe (`/ready`) return `503`.
