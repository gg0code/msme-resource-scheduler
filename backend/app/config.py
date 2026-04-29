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
    # FREE_TIER_MAX_WORKERS / FREE_TIER_MAX_JOBS removed in v6.3.2.3 — they
    # had zero callers. Resource limits live in app/core/plan_limits.py.
    APP_NAME: str = "ZetaOps Copilot"
    APP_VERSION: str = "4.0.9"
    GROQ_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    UPSTASH_REDIS_URL: Optional[str] = None
    

    # v5-whatsapp settings
    WHATSAPP_MOCK_MODE: bool = True
    WHATSAPP_VERIFY_TOKEN: str = "zetaops_verify_token_2026"
    WHATSAPP_APP_SECRET: Optional[str] = None
    WHATSAPP_ACCESS_TOKEN: Optional[str] = None
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = None
    INTERAKT_API_KEY: Optional[str] = None

    # v6.3.5: bot number rendered in the post-signup landing's "Open WhatsApp"
    # deep-link (https://wa.me/<digits>?text=Hi). Empty string = the CTA renders
    # disabled with a "Bot number not yet configured" tooltip; the rest of the
    # landing still renders. Production deployments must set this in .env.
    # Format: digits only, no leading + or spaces (wa.me requirement).
    WHATSAPP_BOT_NUMBER: str = ""

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
