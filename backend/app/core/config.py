from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "SBLOC Engine API"
    app_version: str = "0.2.0"
    environment: Literal["development", "test", "production"] = "development"
    cors_allow_origins: str = "http://localhost:3000"

    database_path: str = "data/real_estate_simulator.db"
    session_cookie_name: str = "res_session"
    session_days: int = 30
    session_cookie_secure: bool = False
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    registration_enabled: bool = True

    rate_limit_enabled: bool = True
    rate_limit_trust_proxy_headers: bool = False
    scan_lease_minutes: int = 15

    fred_api_key: str | None = None
    sofr_series_id: str = "SOFR"
    effr_series_id: str = "EFFR"

    property_provider: str = "rentcast"
    rentcast_api_key: str | None = None
    scanner_result_limit: int = 24

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_use_tls: bool = True


settings = Settings()
