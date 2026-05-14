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

    # v6.3.5: bot number rendered in the post-signup landing's "Open WhatsApp"
    # deep-link (https://wa.me/<digits>?text=Hi). Empty string = the CTA renders
    # disabled with a "Bot number not yet configured" tooltip; the rest of the
    # landing still renders. Production deployments must set this in .env.
    # Format: digits only, no leading + or spaces (wa.me requirement).
    WHATSAPP_BOT_NUMBER: str = ""

    # v6.3.11-alpha: comma-separated list of tenant IDs opted into the
    # pattern-aware briefing path (briefing_intelligence package). Empty
    # = OFF for everyone, which is the safe v6.3.11-alpha default. The
    # dispatcher falls back to the v6.3.4 templated path for any tenant
    # not listed here. Format: "12,17,34" — whitespace and bad tokens
    # are silently skipped.
    PATTERN_BRIEFING_TENANT_IDS: str = ""

    # v6.3.14: comma-separated list of tenant IDs opted into the entity
    # extractor (extraction_candidates writer). Empty = OFF for everyone,
    # which is the safe v6.3.14 default — no extractor work runs until
    # an operator explicitly opts a tenant in. Same parser semantics as
    # PATTERN_BRIEFING_TENANT_IDS above. Format: "12,17,34" — whitespace
    # and bad tokens are silently skipped.
    ENTITY_EXTRACTION_TENANT_IDS: str = ""

    # v6.3.15: nightly candidate-promotion job thresholds. The promoter
    # reuses ENTITY_EXTRACTION_TENANT_IDS for tenant scoping (no separate
    # PROMOTION_TENANT_IDS) — extractor-on implies promoter-on.
    #
    # PROMOTION_MENTION_THRESHOLD     - min mention_count to qualify.
    # PROMOTION_CONFIDENCE_THRESHOLD  - min LLM-self-reported confidence.
    # PROMOTION_FUZZY_MATCH_THRESHOLD - token_set_ratio cutoff for
    #                                   "this candidate matches an
    #                                   existing entity". Single-token
    #                                   candidates fall back to plain
    #                                   ratio at the higher cutoff below.
    # PROMOTION_RATIO_FALLBACK_THRESHOLD - plain ratio cutoff used for
    #                                      single-token candidates.
    # PROMOTION_DAILY_CAP_PER_TENANT  - max promotions per tenant per
    #                                   nightly run. Protects the owner
    #                                   from a "wall of changes" on the
    #                                   first run after weeks of capture.
    # Defaults match the v6.3.15 design doc; env override is the safety
    # valve documented in Q1 / Q5.
    PROMOTION_MENTION_THRESHOLD:        int   = 3
    PROMOTION_CONFIDENCE_THRESHOLD:     float = 0.7
    PROMOTION_FUZZY_MATCH_THRESHOLD:    int   = 85
    PROMOTION_RATIO_FALLBACK_THRESHOLD: int   = 90
    PROMOTION_DAILY_CAP_PER_TENANT:     int   = 10

    # v6.3.15 (revised): owner-confirmation flow. v6.3.15-original silently
    # auto-inserted candidates into employees/machines on the 02:00 IST
    # nightly tick. The revised model splits that into two crons:
    #   - 02:00 IST: evaluate_for_all_tenants — fuzzy-match short-circuit,
    #     skip-bookkeeping, no inserts, no confirmation messages.
    #   - 19:00 IST: send_confirmations_for_all_tenants — pick top-N
    #     pending candidates per tenant, compose a single WhatsApp
    #     message, send to the most-recently-active top-tier phone, flip
    #     state to 'pending'. Owner replies HAAN/NAHI/partial; the
    #     reply parser flips state to 'confirmed' / 'rejected' and ONLY
    #     THEN does insertion happen.
    #
    # PROMOTION_CONFIRMATION_BATCH_SIZE - max candidates per single
    #     evening WhatsApp message. 5 keeps the message readable and the
    #     reply tractable. Surplus qualifying candidates re-qualify
    #     tomorrow night under the same top-N ordering.
    # PROMOTION_CONFIRMATION_TIMEOUT_DAYS - days to wait for an owner
    #     reply before re-asking. 7 days = "you've had a week, here it
    #     is again." Re-ask resets confirmation_state to 'none' and
    #     bumps confirmation_retry_count.
    # PROMOTION_CONFIRMATION_MAX_RETRIES - after this many re-asks with
    #     no reply, the candidate is auto-rejected. 3 retries × 7 days
    #     = ~21 days of patient nudging before the system stops asking.
    # PROMOTION_CONFIRMATION_HOUR_IST / MINUTE_IST - cron clock for the
    #     evening confirmation send. Owner gets the message in the
    #     evening to review at leisure; replies arrive overnight; the
    #     morning briefing reflects approved insertions.
    PROMOTION_CONFIRMATION_BATCH_SIZE:    int = 5
    PROMOTION_CONFIRMATION_TIMEOUT_DAYS:  int = 7
    PROMOTION_CONFIRMATION_MAX_RETRIES:   int = 3
    PROMOTION_CONFIRMATION_HOUR_IST:      int = 19
    PROMOTION_CONFIRMATION_MINUTE_IST:    int = 0

    # v6.3.19.1 cutover release — PUSH_V2_ENABLED removed entirely. The
    # new push system (consolidated_briefing.push_v2_tick + the four
    # dispatch_* functions) is now the sole code path. The
    # shadow-mode verification approach v6.3.19 introduced was
    # abandoned because the safety benefit was theoretical (v5.11
    # production cutover blocked on Meta review; no real customer
    # traffic) and the cognitive cost was real every session.

    # v6.3.19 slice 2D-shadow — debug dispatch endpoint gate.
    #
    # When True, exposes POST /api/v1/whatsapp/debug/dispatch for
    # operator-driven shadow / force-send dispatch testing. Top-tier
    # auth required at the endpoint level. Default True so dev and
    # staging environments can smoke-test; production deployments must
    # set DEBUG_DISPATCH_ENABLED=false in .env.
    DEBUG_DISPATCH_ENABLED: bool = True

    # v6.3.23 brand asset library — public base URL the Meta submit
    # script references when uploading template HEADER IMAGE handles.
    # Dev default points at the local FastAPI asset endpoint
    # (GET /api/v1/whatsapp/assets/{filename}). Production deployments
    # MUST set this in .env to a URL Meta can reach (e.g. a CDN or a
    # publicly-routable subdomain of the API host). The runtime send
    # path does NOT read this — it only matters at template submission.
    WHATSAPP_ASSET_BASE_URL: str = "http://localhost:8000/api/v1/whatsapp/assets"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
