"""Runtime configuration. Everything is overridable with environment variables (see .env.example)."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CRM_", extra="ignore")

    app_name: str = "PropX CRM"
    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./crm.db"
    jwt_secret: str = Field(default="change-me-in-production", min_length=8)
    jwt_ttl_minutes: int = 12 * 60
    cors_origins: list[str] = ["http://localhost:3100", "http://127.0.0.1:3100"]
    webhook_timeout_s: float = 8.0
    webhook_max_attempts: int = 5
    allow_private_webhook_hosts: bool = False
    webhook_inline_delivery: bool = True  # deliver right after the request; the 30s sweeper still retries
    demo_seed: bool = False
    api_page_limit: int = 500

    @field_validator("database_url")
    @classmethod
    def _async_driver(cls, url: str) -> str:
        """Managed Postgres providers hand out ``postgres://``/``postgresql://`` URLs; we always drive asyncpg."""
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+asyncpg://" + url[len(prefix):]
        return url

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in ("production", "prod")


@lru_cache
def get_settings() -> Settings:
    return Settings()
