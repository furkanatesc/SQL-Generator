"""Environment Config Contract (Sprint 32.1).

Single machine-readable inventory of every runtime environment variable the backend
reads, whether through `Settings` (pydantic-settings, `NL2SQL_` prefix) or directly via
`os.getenv` / `app/secret_resolver.py`. `docs/env-contract.md` is the operator-facing view of this module;
`tests/test_env_config_contract.py` keeps both in lock-step with the code and with
`docker-compose.prod.yml`.
"""
from dataclasses import dataclass
from typing import Iterable, Literal

CONTRACT_VERSION = "v1"

SETTINGS_ENV_PREFIX = "NL2SQL_"

# Local/CI database harness variables (app/evaluation/*_connection_resolver.py,
# mssql_seed.py). Deliberately outside the runtime contract.
TEST_HARNESS_ENV_PREFIXES = ("POSTGRES_TEST_", "MYSQL_TEST_", "ORACLE_TEST_", "MSSQL_TEST_")


@dataclass(frozen=True)
class EnvVar:
    name: str
    source: Literal["settings", "direct"]
    secret: bool
    required_in_production: bool
    default: str
    description: str


ENV_CONTRACT: tuple[EnvVar, ...] = (
    # --- Settings (app/settings.py) ---------------------------------------------
    EnvVar("NL2SQL_APP_NAME", "settings", False, False, "SQLGen API", "API title shown in OpenAPI."),
    EnvVar("NL2SQL_APP_VERSION", "settings", False, False, "0.1.0", "Version reported by /health."),
    EnvVar("NL2SQL_APP_DESCRIPTION", "settings", False, False, "(built-in)", "API description shown in OpenAPI."),
    EnvVar("NL2SQL_ENVIRONMENT", "settings", False, True, "local",
           "Deployment environment; production-like values enable the production safety checks."),
    EnvVar("NL2SQL_CORS_ALLOW_ORIGINS", "settings", False, True, '["*"]',
           "JSON array of allowed CORS origins; must not contain * in production."),
    EnvVar("NL2SQL_CORS_ALLOW_CREDENTIALS", "settings", False, False, "true", "CORS allow-credentials flag."),
    EnvVar("NL2SQL_CORS_ALLOW_METHODS", "settings", False, False, '["*"]', "JSON array of allowed CORS methods."),
    EnvVar("NL2SQL_CORS_ALLOW_HEADERS", "settings", False, False, '["*"]', "JSON array of allowed CORS headers."),
    EnvVar("NL2SQL_UPLOAD_DIR", "settings", False, False, "<backend>/uploads", "Directory for uploaded files."),
    EnvVar("NL2SQL_DEBUG_ENDPOINTS_ENABLED", "settings", False, True, "true",
           "Expose /api/debug/* endpoints; must be false in production."),
    EnvVar("NL2SQL_JOB_EXECUTION_MODE", "settings", False, False, "inline",
           "Where NL→SQL jobs run: inline (API process) or worker (python -m app.jobs.worker)."),
    EnvVar("NL2SQL_JOB_WORKER_POLL_SECONDS", "settings", False, False, "1.0",
           "Worker idle poll interval in seconds."),
    EnvVar("NL2SQL_JOB_STALE_SECONDS", "settings", False, False, "300",
           "A processing job whose worker heartbeat is older than this is failed; pending jobs "
           "older than this raise JOB_QUEUE_STALLED in worker mode."),
    EnvVar("NL2SQL_JOB_MAX_ATTEMPTS", "settings", False, False, "3",
           "Worker mode: total attempts for a transiently failing job before it is dead-lettered."),
    EnvVar("NL2SQL_JOB_RETRY_BACKOFF_SECONDS", "settings", False, False, "30",
           "Worker mode: base of the exponential retry backoff (capped at 900 s)."),
    EnvVar("NL2SQL_JOB_MAX_CONCURRENT", "settings", False, False, "0",
           "Worker mode: max jobs processing at once across all workers (0 = unlimited)."),
    EnvVar("NL2SQL_RATE_LIMIT_REQUESTS_PER_MINUTE", "settings", False, False, "0",
           "Per-client (API key or IP) API request limit per minute; 0 = off."),
    EnvVar("NL2SQL_RATE_LIMIT_JOBS_PER_MINUTE", "settings", False, False, "0",
           "Per-client limit for the job-creation endpoints per minute; 0 = off."),
    EnvVar("NL2SQL_LLM_REQUESTS_PER_MINUTE", "settings", False, False, "15",
           "Process-wide LLM (NVIDIA NIM) call rate shared by all jobs."),
    EnvVar("NL2SQL_LLM_BURST", "settings", False, False, "3", "Burst size of the LLM call limiter."),
    EnvVar("NL2SQL_HEALTH_MIN_FREE_DISK_MB", "settings", False, False, "100",
           "/ready fails (disk check) below this much free space on the app DB volume; 0 = off."),
    EnvVar("NL2SQL_BACKUP_DIR", "settings", False, False, "<backend>/backups",
           "Where `python -m app.backup` writes and lists archives."),
    EnvVar("NL2SQL_BACKUP_BEFORE_MIGRATION", "settings", False, False, "true",
           "Copy the app DB (<db>.pre-v<N>-<ts>.bak, last 3 kept) before applying pending migrations."),
    # --- Direct os.getenv reads ----------------------------------------------------
    EnvVar("NL2SQL_API_KEY", "direct", True, True, "(none)",
           "API key fallback when no key is stored in the DB config (app/auth.py)."),
    EnvVar("NL2SQL_API_KEY_FILE", "direct", False, False, "(none)",
           "Path of a file holding NL2SQL_API_KEY (Docker secret); wins over NL2SQL_API_KEY "
           "(app/secret_resolver.py)."),
    EnvVar("NL2SQL_TRACE_DB_PATH", "direct", False, False, "data/nl2sql_traces.db",
           "SQLite trace database path (app/trace/dependencies.py)."),
    EnvVar("SQLGEN_DB_PATH", "direct", False, False, "<backend>/sqlgen.db",
           "SQLite application database path (app/database.py)."),
    EnvVar("NVIDIA_API_KEY", "direct", True, False, "(none)",
           "LLM / embedding provider key fallback (app/llm_client.py, app/sql_pipeline.py)."),
    EnvVar("NVIDIA_API_KEY_FILE", "direct", False, False, "(none)",
           "Path of a file holding NVIDIA_API_KEY (Docker secret); wins over NVIDIA_API_KEY "
           "(app/secret_resolver.py)."),
)


def known_env_names() -> frozenset[str]:
    return frozenset(v.name for v in ENV_CONTRACT)


def find_unknown_prefixed_env(environ: Iterable[str]) -> list[str]:
    """Upper-cased `NL2SQL_*` names in `environ` that the contract does not know.

    Matching is case-insensitive like pydantic-settings. Only names are inspected,
    never values, so the result is safe to log.
    """
    known = known_env_names()
    return sorted(
        {
            name.upper()
            for name in environ
            if name.upper().startswith(SETTINGS_ENV_PREFIX) and name.upper() not in known
        }
    )
