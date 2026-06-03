# Production Runbook

This document details the deployment, configuration verification, and diagnostics interpretation for running the SQLGen backend in production environments.

---

## Supported Deployment Model

The current supported model for deploying the SQLGen backend is:
- **Docker container**: A standalone container image built using the official Dockerfile.
- **Single backend instance**: The application runs as a single process inside a single container.
- **Manual environment configuration**: Configured entirely via system environment variables.

### Not Supported Yet
The following deployment methods and technologies are **not supported**:
- Docker Compose orchestration
- Kubernetes orchestration (including custom Pods/Services)
- Helm chart deployments
- Amazon ECS or EKS
- Azure Container Apps or App Services
- Automated Docker registry publishing workflow (e.g. pushing to Docker Hub or ECR via CI)

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

## Startup Warning Interpretation

Startup configuration validation checks are executed during application boot to identify misconfigurations.

> [!IMPORTANT]
> All startup warnings are **warning-only** and **non-fatal**. The application server startup will always proceed even if there are critical warnings.

### Warning Scenarios

- **`API_KEY_NOT_CONFIGURED`**
  - *Severity*: `critical`
  - *Trigger*: No LLM API Key is found in the database settings or in the `NL2SQL_API_KEY` environment variable.
  - *Action*: Ensure a valid API key is set in the environment or database.

- **`CORS_WILDCARD_IN_PRODUCTION`**
  - *Severity*: `warning`
  - *Trigger*: Allowed CORS origins includes wildcard (`*`) while running in a production-like environment (e.g. environment starts with `prod` or `production`).
  - *Action*: Configure specific domains in the allowed CORS origins settings to secure the API.

- **`DEBUG_ENDPOINTS_ENABLED_IN_PRODUCTION`**
  - *Severity*: `warning`
  - *Trigger*: Debug endpoints are enabled (`NL2SQL_DEBUG_ENDPOINTS_ENABLED=true`) while running in a production-like environment.
  - *Action*: Disable debug endpoints in production environments.

- **`UPLOAD_DIR_DEFAULT`**
  - *Severity*: `info`
  - *Trigger*: No custom upload directory path is configured via `NL2SQL_UPLOAD_DIR`.
  - *Action*: Informational only; the application will fall back to using `/app/uploads` locally.
