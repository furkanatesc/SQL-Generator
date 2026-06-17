# Environment Variable Contract

This document specifies the environment variable interface for the SQLGen backend, including requirements, defaults, and security configurations.

All configuration variables are prefixed with `NL2SQL_` and are loaded via `pydantic-settings` from system environment variables or local `.env` files.

---

## Required Variables

| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| **`NL2SQL_API_KEY`** | Conditionally | *None* | Runtime API Key fallback used for communicating with LLM providers. |

### API Key Resolution Priority
The application resolves the active API Key in the following order of precedence:
1. **Database Configuration**: Checked first. If a key exists in the database settings table (`config.api_key`), it is used.
2. **Environment Fallback**: Checked second. If no key is configured in the database, the system falls back to the `NL2SQL_API_KEY` environment variable.

If no API key is resolved by either method, a critical validation warning is generated.

---

## Optional Variables

| Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| **`NL2SQL_ENVIRONMENT`** | String | `local` | The deployment environment name (e.g. `local`, `ci`, `production`, `prod-eu`). |
| **`NL2SQL_UPLOAD_DIR`** | String | *None* | Absolute path to the custom directory used for storing uploaded files. |
| **`NL2SQL_CORS_ALLOW_ORIGINS`** | JSON Array | `["*"]` | List of allowed CORS origins to inject into the CORS middleware. |
| **`NL2SQL_DEBUG_ENDPOINTS_ENABLED`** | Boolean | `true` | Expose developer-only API endpoints for direct debugging/tracing. |

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
- **Warning Code**: `CORS_WILDCARD_IN_PRODUCTION` (Severity: `warning`)
- **Remediation**: Set `NL2SQL_CORS_ALLOW_ORIGINS` to a JSON array of specific trusted domains, e.g., `["https://sqlgen.mycompany.com"]`.

### 2. Debug Endpoints Enabled in Production
- **Condition**: Running in a production-like environment with `NL2SQL_DEBUG_ENDPOINTS_ENABLED` set to `true` (default value).
- **Warning Code**: `DEBUG_ENDPOINTS_ENABLED_IN_PRODUCTION` (Severity: `warning`)
- **Remediation**: Set `NL2SQL_DEBUG_ENDPOINTS_ENABLED=false` in the production environment variables.

---

## Startup Warn-Only Behavior
All configuration warnings are non-fatal. The application server will always complete its startup successfully to allow read-only or diagnostic operations even under misconfigurations.
