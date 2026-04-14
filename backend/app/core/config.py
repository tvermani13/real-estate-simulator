from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "SBLOC Engine API"
    cors_allow_origins: str = "http://localhost:3000"

    fred_api_key: str | None = None
    sofr_series_id: str = "SOFR"
    effr_series_id: str = "EFFR"


settings = Settings()

