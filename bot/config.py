from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BOT_TOKEN: str
    DATABASE_URL: str
    ADMIN_TELEGRAM_ID: int

    # AI / OpenRouter
    OPENROUTER_API_KEY: str = ""
    AI_MODEL: str = "google/gemini-2.0-flash-001"
    AI_MAX_TOKENS: int = 600
    AI_SESSION_TTL_MINUTES: int = 30  # через сколько минут сбрасывать контекст диалога

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
