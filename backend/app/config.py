from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://msme_user:msme_pass@localhost:5432/msme_scheduler"
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "msme_user"
    DB_PASSWORD: str = "msme_pass"
    DB_NAME: str = "msme_scheduler"
    BACKEND_PORT: int = 8000
    FRONTEND_PORT: int = 3000
    SECRET_KEY: str = "changeme"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    FREE_TIER_MAX_WORKERS: int = 10
    FREE_TIER_MAX_JOBS: int = 50
    APP_NAME: str = "ZetaOps Copilot"
    APP_VERSION: str = "4.0.9"
    GROQ_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    UPSTASH_REDIS_URL: Optional[str] = None
    WHATSAPP_MOCK_MODE: bool = True   # True = no real WhatsApp API calls, safe for dev

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
