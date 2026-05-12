from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/travelagent"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WEBHOOK_URL: str = ""

    # LLM (пробрасываются в src/llm/config.py)
    LLM_PROVIDER: str = "claude"

    # App
    MAX_STEPS: int = 5  # ADR-007
    MAX_RECENT_MESSAGES: int = 10


settings = Settings()
