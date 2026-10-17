"""Application configuration."""

from decimal import Decimal
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
    simulator_enabled: bool = False
    # CEA Version 22.0 FY 2025-26 weighted-average Indian grid factor.
    grid_co2_factor_kg_per_kwh: Decimal = Decimal("0.675")
    grid_co2_factor_source: str = (
        "Central Electricity Authority (CEA), CO2 Baseline Database Version 22.0, "
        "FY 2025-26 weighted-average grid factor including renewable generation."
    )
    grid_co2_factor_source_url: str = "https://cea.nic.in/cdm-co2-baseline-database/?lang=en"
    # Educational tree-year conversion only; not an estimate of actual trees saved.
    tree_co2_absorption_kg_per_year: Decimal = Decimal("22.0")
    auth_secret: str = "local-development-secret-change-before-deployment"
    admin_username: str = "admin"
    admin_password: str = "Admin123!"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached environment-backed configuration."""
    return Settings()


settings = get_settings()
