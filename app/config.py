from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    app_name: str = "HabitFlow"
    app_env: str = "development"  # development | production | testing
    host: str = "0.0.0.0"
    port: int = 8000

    # Database configuration (SQLite on persistent disk or PostgreSQL URL)
    database_url: str = "sqlite:///./habitflow.db"

    # Single-owner authentication settings (MUST be set via environment in production)
    secret_key: str = "dev-only-secret-key-change-in-production-via-env"
    owner_username: str = "owner"
    owner_password: Optional[str] = "habitflow-dev-pass"
    owner_password_hash: Optional[str] = None
    session_max_age_seconds: int = 60 * 60 * 24 * 30  # 30 days
    cookie_secure: Optional[bool] = None  # Defaults to True when app_env == "production"

    # Owner local timezone so laptop, phone, and cloud server agree on "today"
    owner_timezone: str = "Asia/Almaty"

    free_plan_max_habits: int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def use_secure_cookies(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.is_production

    @property
    def normalized_database_url(self) -> str:
        """Normalize legacy postgres:// URLs from cloud providers to SQLAlchemy format."""
        url = self.database_url.strip()
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql://", 1)
        return url


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()


def get_owner_now() -> datetime:
    """Return current datetime in the owner's configured timezone."""
    settings = get_settings()
    try:
        tz = ZoneInfo(settings.owner_timezone)
        return datetime.now(tz)
    except (ZoneInfoNotFoundError, Exception):
        return datetime.now()


def get_owner_today() -> date:
    """Return current calendar date in the owner's configured timezone."""
    return get_owner_now().date()
