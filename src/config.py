from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        env_ignore_empty=True,  # empty env vars (e.g. ANTHROPIC_API_KEY='') don't override .env
    )

    # --- Database ---
    DATABASE_URL: str = (
        "postgresql+asyncpg://digitaltwin:changeme@localhost:5432/digitaltwin"
    )

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- LLM Provider ---
    LLM_PROVIDER: str = "anthropic"  # anthropic | openai | local

    ANTHROPIC_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    VOYAGE_API_KEY: Optional[str] = None

    LOCAL_LLM_BASE_URL: str = "http://localhost:11434"
    LOCAL_LLM_MODEL: str = "llama3"
    LOCAL_EMBED_MODEL: str = "nomic-embed-text"

    # --- API Security ---
    ADMIN_API_KEY: str = "change-me-in-production"

    # --- Memory ---
    EMBEDDING_DIM: int = 1024

    # --- Subject ---
    SUBJECT_ID: str = "default"
    SUBJECT_NAME: str = ""  # Human display name, e.g. "Vasil Andrijovich"

    # --- Slack ---
    SLACK_BOT_TOKEN: Optional[str] = None       # xoxb-...
    SLACK_SIGNING_SECRET: Optional[str] = None  # from Slack app Basic Information page

    # --- App ---
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"


settings = Settings()
