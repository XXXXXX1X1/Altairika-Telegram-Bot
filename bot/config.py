from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BOT_TOKEN: str
    DATABASE_URL: str
    ADMIN_TELEGRAM_ID: int

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
