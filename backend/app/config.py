from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://brillion:brillion@localhost:5432/brillion"
    redis_url: str = "redis://localhost:6379/0"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5-mini"
    admin_secret: str = "development-only-admin-secret"
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    session_signing_secret: str = "development-only-signing-secret-change-me"
    environment: str = "development"
    log_level: str = "INFO"
    sentry_dsn: str | None = None
    room_ttl_hours: int = 24
    inline_question_worker: bool = False

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("database_url", mode="before")
    @classmethod
    def async_postgres_driver(cls, value: object) -> object:
        if isinstance(value, str) and value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
