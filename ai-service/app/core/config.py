"""AI service settings (pydantic-settings; env > .env)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM (OPENAI_BASE_URL makes any OpenAI-compatible provider work; DESIGN §5.5)
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    # P8: patient used when /chat carries no patient_id
    default_patient_id: str = "P001"

    # REST tools target (P3: ai-service never touches the DB; used from slice 3 on)
    backend_url: str = "http://localhost:8000"


settings = Settings()
