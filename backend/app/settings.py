from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "SQLGen API"
    app_version: str = "0.1.0"
    app_description: str = "SQLGen platformu için lokal FastAPI API katmanı"

    environment: str = "local"

    cors_allow_origins: list[str] = ["*"]
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = ["*"]
    cors_allow_headers: list[str] = ["*"]

    upload_dir: str | None = None

    debug_endpoints_enabled: bool = False

    model_config = SettingsConfigDict(
        env_prefix="NL2SQL_",
        env_file=".env",
        extra="ignore",
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()
