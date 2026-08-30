from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Heat-to-Shelf Backend"
    app_version: str = "0.1.0"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://heat:heat@localhost:5432/heat2shelf"

    fortyguard_api_key: str | None = None
    fortyguard_base_url: str = "https://api.fortyguard.com"
    fortyguard_timeout_seconds: float = 10.0
    fortyguard_max_retries: int = 2
    fortyguard_retry_backoff_seconds: float = 0.2
    fortyguard_cache_ttl_seconds: int = 300
    fortyguard_max_staleness_minutes: int = 60

    routing_provider: str = "fixture"
    routing_base_url: str = ""
    routing_api_key: str | None = None
    routing_timeout_seconds: float = 10.0

    route_segment_count: int = 20
    corridor_margin_degrees: float = 0.01
    time_alignment_tolerance_minutes: int = 60
    max_heatmap_requests: int = 20

    scenario_horizon_hours: int = 168

    rate_limit_requests: int = 10
    rate_limit_window_seconds: int = 60

    risk_weight_peak_temperature: float = 0.55
    risk_weight_duration: float = 0.45
    risk_weight_persistence: float = 0.0
    risk_weight_high_risk_segments: float = 0.0
    risk_band_warning_at: float = 25.0
    risk_band_high_at: float = 50.0
    risk_band_critical_at: float = 75.0
    risk_calculation_version: str = "1.0.0"

    default_user_email: str = "demo@heat2shelf.dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()