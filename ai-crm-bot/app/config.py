from pydantic_settings import BaseSettings, SettingsConfigDict


FIELDS = [
    {
        "key": "name",
        "label": "Имя",
        "type": "str",
        "required": True,
        "amo_target": "contact",
        "amo_field_id": None,
        "validation": None,
    },
    {
        "key": "phone",
        "label": "Номер телефона",
        "type": "str",
        "required": True,
        "amo_target": "contact",
        "amo_field_id": None,
        "validation": r"^\+998\d{9}$",
    },
    {
        "key": "address",
        "label": "Адрес",
        "type": "str",
        "required": True,
        "amo_target": "lead",
        "amo_field_id": 123456,
        "validation": None,
    },
    {
        "key": "sqm",
        "label": "Площадь комнаты, м²",
        "type": "float",
        "required": True,
        "amo_target": "lead",
        "amo_field_id": 123457,
        "validation": None,
    },
    {
        "key": "budget",
        "label": "Бюджет",
        "type": "str",
        "required": True,
        "amo_target": "lead",
        "amo_field_id": 123458,
        "validation": None,
    },
]

FIELD_BY_KEY = {field["key"]: field for field in FIELDS}


class Settings(BaseSettings):
    telegram_bot_token: str = ""
    anthropic_api_key: str = ""

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_crm"

    amo_base_url: str = ""
    amo_token: str = ""

    manager_telegram_chat_id: int | None = None

    talker_model: str = "claude-3-5-sonnet-20241022"
    extractor_model: str = "claude-3-5-sonnet-20241022"

    total_retry_limit: int = 8
    field_retry_limit: int = 3
    timeout_hours: int = 6
    repeat_days: int = 90

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()