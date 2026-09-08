"""Application settings, loaded from environment variables and .env.

See .env.example for the full list of supported keys, including
per-supplier credential blocks that have no fixed field here since
suppliers are added dynamically.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Paths
    output_dir: str = "output"
    parts_file: str = "parts.txt"
    pricing_tiers_file: str = "pricing_tiers.csv"
    warehouse_map_file: str = "warehouse_map.csv"

    # Playwright
    playwright_proxy: str | None = None
    playwright_version_min: str = "1.55.1"
    context_pool_size: int = 1

    # Logging
    log_level: str = "INFO"

    # Web panel
    web_secret_key: str = "change_me_32_chars_minimum_please"
    web_port: int = 8080
    web_access_token_ttl: int = 900
    web_refresh_token_ttl: int = 86400
    hawkeye_dir: str = "."
    hawkeye_python: str = "python"

    # Secret backend
    secret_backend: str = "env"
    vault_addr: str | None = None
    vault_token: str | None = None


settings = Settings()
