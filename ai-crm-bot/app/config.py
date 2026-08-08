from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
if not ENV_FILE.exists():
    ENV_FILE = BASE_DIR / ".env.example"


class Settings(BaseSettings):
    telegram_bot_token: str = Field(..., env="TELEGRAM_BOT_TOKEN")
    anthropic_api_key: str | None = Field(None, env="ANTHROPIC_API_KEY")
    gemini_api_key: str | None = Field(None, env="GEMINI_API_KEY")
    groq_api_key: str | None = Field(None, env="GROQ_API_KEY")
    groq_api_url: str = Field("https://api.groq.com/v1/completions", env="GROQ_API_URL")
    llm_provider: str = Field(..., env="LLM_PROVIDER")

    database_url: str = Field(..., env="DATABASE_URL")

    amo_base_url: str = Field(..., env="AMO_BASE_URL")
    amo_token: str = Field(..., env="AMO_TOKEN")
    message_debounce_seconds: int = Field(5, env="MESSAGE_DEBOUNCE_SECONDS")

    manager_telegram_chat_id: int | None = Field(None, env="MANAGER_TELEGRAM_CHAT_ID")

    talker_model: str = Field(..., env="TALKER_MODEL")
    extractor_model: str = Field(..., env="EXTRACTOR_MODEL")

    @field_validator("manager_telegram_chat_id", mode="before")
    @classmethod
    def _empty_string_to_none(cls, value):
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    total_retry_limit: int = Field(8, env="TOTAL_RETRY_LIMIT")
    field_retry_limit: int = Field(3, env="FIELD_RETRY_LIMIT")
    timeout_hours: int = Field(6, env="TIMEOUT_HOURS")
    repeat_days: int = Field(90, env="REPEAT_DAYS")
    crm_retry_interval_minutes: int = Field(3, env="CRM_RETRY_INTERVAL_MINUTES")

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()