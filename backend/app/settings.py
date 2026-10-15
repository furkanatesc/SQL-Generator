from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Publicly known local-development key (also the frontend default). Seeded into the
# config DB only outside production-like environments (Sprint 32.0).
DEV_DEFAULT_API_KEY = "sqlgen_secret_dev_key"


def is_production_like_environment(environment: str) -> bool:
    normalized = environment.strip().lower()
    return (
        normalized == "production"
        or normalized == "prod"
        or normalized.startswith("production-")
        or normalized.startswith("prod-")
    )

class Settings(BaseSettings):
    app_name: str = "SQLGen API"
    app_version: str = "0.1.0"
    app_description: str = "SQLGen platformu için lokal FastAPI API katmanı"

    environment: str = "local"

    cors_allow_origins: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_headers: list[str] = Field(default_factory=lambda: ["*"])

    upload_dir: str | None = None

    debug_endpoints_enabled: bool = True

    # Sprint 32.4 — where NL→SQL jobs run: in the API process ("inline") or in the
    # separate `python -m app.jobs.worker` process ("worker").
    job_execution_mode: Literal["inline", "worker"] = "inline"
    job_worker_poll_seconds: float = Field(default=1.0, gt=0)
    job_stale_seconds: int = Field(default=300, ge=10)
    # Sprint 32.5 — queue semantics (worker mode only).
    job_max_attempts: int = Field(default=3, ge=1)
    job_retry_backoff_seconds: float = Field(default=30.0, gt=0)
    job_max_concurrent: int = Field(default=0, ge=0)
    # Sprint 32.6 — API rate limits per client (0 = off) and the process-wide LLM call rate.
    rate_limit_requests_per_minute: int = Field(default=0, ge=0)
    rate_limit_jobs_per_minute: int = Field(default=0, ge=0)
    llm_requests_per_minute: float = Field(default=15.0, gt=0)
    llm_burst: int = Field(default=3, ge=1)
    # Sprint 32.7 — /ready fails below this much free space on the app DB volume (0 = off).
    health_min_free_disk_mb: int = Field(default=100, ge=0)

    model_config = SettingsConfigDict(
        env_prefix="NL2SQL_",
        env_file=".env",
        extra="ignore",
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()
