"""Application configuration."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SmartVolt API"
    api_v1_prefix: str = "/api/v1"
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./smartvolt.db"
    default_tariff_per_kwh: float = 8.0
    simulator_interval_seconds: int = 3600
    simulator_min_kwh: float = 0.05
    simulator_max_kwh: float = 0.50

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached environment-backed configuration."""
    return Settings()


settings = get_settings()
