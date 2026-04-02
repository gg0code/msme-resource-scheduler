"""
config.py — Application Configuration Settings for ZetaOps Copilot

FILE PURPOSE
This file defines all application configuration settings using Pydantic BaseSettings for the ZetaOps Copilot scheduling system. It centralizes environment variable loading and validation, supporting database connections, JWT authentication, CORS settings, tier limits, AI service keys, and WhatsApp integration settings. Originally introduced in v1.0 for basic database configuration, it was extended in v1.1 for JWT/CORS support and further expanded in v5-whatsapp branch for WhatsApp Copilot features. This sits at the core of the backend architecture as the single source of truth for all configurable application behavior, ensuring consistent settings across all services, routers, and background tasks.

WHAT THIS FILE DOES — step by step
1. Imports pydantic_settings.BaseSettings to enable automatic environment variable loading with type validation
2. Defines the Settings class inheriting from BaseSettings to automatically parse environment variables
3. Declares V1.0 database connection fields (DATABASE_URL, DB_HOST, DB_PORT, etc.) with default values for local development
4. Declares V1.1 JWT authentication fields (SECRET_KEY, ALGORITHM, token expiration times) for user session management
5. Declares CORS settings (ALLOWED_ORIGINS) and tier limits (FREE_TIER_MAX_WORKERS, FREE_TIER_MAX_JOBS) for multi-tenant restrictions
6. Declares AI service configuration (GROQ_API_KEY, APP_NAME, APP_VERSION) for LLaMA integration
7. Declares v5-whatsapp specific fields (UPSTASH_REDIS_URL, WHATSAPP_VERIFY_TOKEN, INTERAKT_API_KEY, etc.) for WhatsApp Copilot features
8. Implements allowed_origins_list property method to parse comma-separated ALLOWED_ORIGINS string into a list for FastAPI CORS middleware
9. Configures Pydantic to load from .env file with UTF-8 encoding and ignore unknown environment variables
10. Creates a singleton settings instance that will be imported throughout the application

KEY FUNCTIONS / CLASSES / COMPONENTS

Settings
Type         : Pydantic BaseSettings class
Purpose      : Centralized configuration container that automatically loads and validates all application settings from environment variables. Provides type-safe access to database credentials, JWT secrets, API keys, tier limits, and feature flags. Uses Pydantic's BaseSettings to handle environment variable parsing, type conversion, and default value assignment.
Parameters   : None (initialized automatically from environment variables and .env file)
Returns      : N/A (class definition)
Calls        : pydantic_settings.BaseSettings constructor for environment variable loading
DB/API       : No direct database or API calls, but provides DATABASE_URL and API keys used by other services
Side effects : Reads .env file from filesystem, validates environment variables on application startup, raises validation errors if required settings are missing or invalid

allowed_origins_list
Type         : Property method
Purpose      : Parses the ALLOWED_ORIGINS environment variable (comma-separated string) into a proper Python list for use with FastAPI's CORS middleware. This enables flexible CORS configuration for multiple frontend domains in different environments (development, staging, production).
Parameters   : self (Settings instance)
Returns      : list[str] - List of allowed origin URLs, with whitespace stripped from each entry
Calls        : Python built-in string methods (split, strip)
DB/API       : None
Side effects : None (pure transformation function)

settings
Type         : Settings instance (singleton)
Purpose      : Global singleton instance of the Settings class that provides application-wide access to all configuration values. This instance is imported by routers, services, database connections, and other modules that need access to environment-specific settings like database URLs, JWT secrets, or API keys.
Parameters   : None (uses environment variables and .env file)
Returns      : Settings object with all configuration fields populated
Calls        : Settings class constructor
DB/API       : None directly, but configuration enables all database and API connections
Side effects : Loads and validates environment variables on module import

WHO CALLS THIS FILE
- backend/app/main.py (imports settings for FastAPI app configuration, CORS setup, and app metadata)
- backend/app/database.py (imports settings.DATABASE_URL for SQLAlchemy engine creation)
- backend/app/core/security.py (imports settings for SECRET_KEY, ALGORITHM, and token expiration times)
- backend/app/core/plan_limits.py (imports settings for FREE_TIER_MAX_WORKERS and FREE_TIER_MAX_JOBS)
- backend/app/services/ai_service.py (imports settings.GROQ_API_KEY for LLaMA API authentication)
- backend/app/services/whatsapp_service.py (imports WhatsApp-related settings in v5-whatsapp branch)
- backend/app/services/redis_service.py (imports settings.UPSTASH_REDIS_URL in v5-whatsapp branch)
- backend/app/routers/*.py files (various routers import settings for configuration-dependent behavior)

IMPORTS EXPLAINED
- pydantic_settings.BaseSettings: Pydantic's configuration management class that automatically loads environment variables, performs type validation, and provides default values for application settings

INTERN NOTES
- Easiest thing to break: Adding new required settings without default values will crash the application on startup if the environment variable is missing - always provide sensible defaults or mark fields as optional
- Non-obvious design decision: Settings uses a singleton pattern (global `settings` instance) rather than dependency injection because configuration should be consistent across the entire application lifecycle and doesn't need per-request variation
- Most common mistake: Forgetting to add new WhatsApp-related settings to the v5-whatsapp section when adding new WhatsApp features, or accidentally putting v5 settings in the wrong version section
- Design principle #3: This file implements "No .env in git. All secrets from settings.*" by using pydantic_settings to load sensitive data from environment variables rather than hardcoding secrets
- What to check if behaving unexpectedly: Verify .env file exists and has correct encoding, check that environment variable names exactly match field names (case-sensitive), and ensure required fields like SECRET_KEY and DATABASE_URL are set
- v5-whatsapp merge consideration: When merging v5-whatsapp into v4-dev, all WhatsApp-related settings should have safe defaults (like WHATSAPP_MOCK_MODE: bool = True) to prevent breaking existing v4 deployments that don't have WhatsApp environment variables configured
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
    APP_NAME: str = "ZetaOps Copilot"
    APP_VERSION: str = "4.0.9"
    GROQ_API_KEY: str = ""

    # ── v5-whatsapp new fields ────────────────────────────────────────────────
    UPSTASH_REDIS_URL: str = ""
    WHATSAPP_VERIFY_TOKEN: str = ""
    WHATSAPP_APP_SECRET: str = ""
    INTERAKT_API_KEY: str = ""
    WHATSAPP_MOCK_MODE: bool = True
    WHISPER_MODE: str = "local"
    OPENAI_API_KEY: str = ""

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
