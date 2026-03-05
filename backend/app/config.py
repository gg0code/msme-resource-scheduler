"""
config.py — V1.1
Adds JWT + CORS + tier limit settings to existing V1.0 config.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── V1.0 fields (unchanged) ───────────────────────────────────────────────
    DATABASE_URL: str
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "msme_user"
    DB_PASSWORD: str = "msme_pass"
    DB_NAME: str = "msme_scheduler"
    BACKEND_PORT: int = 8000
    FRONTEND_PORT: int = 3000

    # ── V1.1 new fields ───────────────────────────────────────────────────────
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALLOWED_ORIGINS: str = "http://localhost:5173"
    FREE_TIER_MAX_WORKERS: int = 10
    FREE_TIER_MAX_JOBS: int = 50
    APP_NAME: str = "MSME Resource Scheduler"
    APP_VERSION: str = "1.1.0"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
