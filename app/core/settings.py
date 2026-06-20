from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5433/booking"
    redis_url: str = "redis://localhost:6379/0"

    confirm_failure_rate: float = 0.15
    confirm_max_retries: int = 5
    confirm_retry_delay: float = 1.0

    rate_limit_times: int = 10
    rate_limit_window_seconds: int = 60

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
