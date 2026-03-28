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
    GROQ_API_KEY: str = ""
     # ── v5-whatsapp new fields ────────────────────────────────────────────
    # Redis session storage for WhatsApp conversation history.
    # Get this URL from upstash.com → your Redis DB → Connect → Python.
    # Format: redis://default:password@host:6379
    UPSTASH_REDIS_URL: str = ""

    # WhatsApp webhook security — set in Meta developer dashboard.
    # Used to verify that inbound webhooks really came from Meta/Interakt.
    WHATSAPP_VERIFY_TOKEN: str = ""
    WHATSAPP_APP_SECRET: str = ""

    # Interakt API key for sending outbound WhatsApp messages.
    # Leave blank until v5.5 — simulator mode does not need this.
    INTERAKT_API_KEY: str = ""

    # When True, outbound messages are logged to console instead of
    # calling Interakt API. Set to True for all development work.
    WHATSAPP_MOCK_MODE: bool = True

    # Whisper transcription mode.
    # 'local'  = use openai-whisper Python library (free, no API key needed)
    # 'api'    = use OpenAI Whisper API (paid, more reliable in production)
    # Leave as 'local' until v5.5.
    WHISPER_MODE: str = "local"

    # OpenAI API key — only needed when WHISPER_MODE = 'api' (from v5.5).
    # Leave blank for now.
    OPENAI_API_KEY: str = ""
  
 

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
