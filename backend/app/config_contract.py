"""Environment Config Contract (Sprint 32.1).

Single machine-readable inventory of every runtime environment variable the backend
reads, whether through `Settings` (pydantic-settings, `NL2SQL_` prefix) or directly via
`os.getenv`. `docs/env-contract.md` is the operator-facing view of this module;
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
    # --- Direct os.getenv reads ----------------------------------------------------
    EnvVar("NL2SQL_API_KEY", "direct", True, True, "(none)",
           "API key fallback when no key is stored in the DB config (app/auth.py)."),
    EnvVar("NL2SQL_TRACE_DB_PATH", "direct", False, False, "data/nl2sql_traces.db",
           "SQLite trace database path (app/trace/dependencies.py)."),
    EnvVar("SQLGEN_DB_PATH", "direct", False, False, "<backend>/sqlgen.db",
           "SQLite application database path (app/database.py)."),
    EnvVar("NVIDIA_API_KEY", "direct", True, False, "(none)",
           "LLM / embedding provider key fallback (app/llm_client.py, app/sql_pipeline.py)."),
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
