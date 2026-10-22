"""Application settings (pydantic-settings; env > .env)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://clinicpilot:clinicpilot@localhost:5432/clinicpilot"

    # AI engine proxy target (used from slice 2 on)
    ai_service_url: str = "http://localhost:8001"
    ai_service_timeout: float = 60.0  # LLM turns can be slow


settings = Settings()
