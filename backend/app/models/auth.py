# app/models/auth.py - Version 1.3
# Branch: both
#
# FILE PURPOSE
# SQLAlchemy ORM models for core auth entities: Tenant, User, RefreshToken.
# Introduced in v1.0. AI usage tracking columns added v4.0.9. WhatsApp entry-
# gate columns (entry_mode, briefing_*, created_via, phone_e164) added v6.3.1
# via migration 027 to back SRS v6.4 §6.28.
# Layer: model
#
# WHAT THIS FILE DOES
# 1. Defines Tenant - top-level org unit, plan + AI quota + entry-gate config
# 2. Defines User - belongs to one Tenant, has a role and per-user briefing prefs
# 3. Defines RefreshToken - JWT refresh token store per user/tenant
#
# KEY FUNCTIONS / CLASSES
#
# Name         : Tenant
# Type         : SQLAlchemy model
# Purpose      : Represents one MSME customer. All data is scoped to tenant_id.
# DB/API       : table tenants
# Side effects : cascade deletes to users, refresh_tokens
#
# Name         : User
# Type         : SQLAlchemy model
# Purpose      : Authenticated user belonging to a Tenant. Exposes is_top_tier
#                Python property for v6.4 RBAC checks (see SRS §6.28.6).
# DB/API       : table users
#
# Name         : RefreshToken
# Type         : SQLAlchemy model
# Purpose      : Persisted refresh tokens for JWT rotation.
# DB/API       : table refresh_tokens
#
# WHO CALLS THIS FILE
# - app/core/dependencies.py - loads User via get_current_user
# - app/routers/auth.py - creates User and Tenant on registration
# - app/routers/ai_chat.py - reads/writes Tenant AI usage columns
# - app/services/role_helpers.py - validates User.role values
# - backend/scripts/backfill_v6_4_entry_gate.py - normalises new columns
#
# WHAT THIS FILE CALLS
# - app.database.Base - declarative base for all ORM models
# - sqlalchemy types: Boolean, Column, Date, DateTime, ForeignKey, Integer,
#                     String, Time, text
#
# INTERN NOTES
# - updated_at uses lambda: datetime.now(timezone.utc) not datetime.utcnow (deprecated py3.12)
# - ai_queries_date is a Date column (not DateTime) - resets daily in get_or_reset_usage()
# - ai_tokens_today tracked for future token-based limiting but not enforced yet
# - industry_type added v4.0.8 for AI terminology context
# - 'proprietor' (legacy) and 'owner' (v6.4) are synonyms — both grant top-tier
#   access. See TOP_TIER_ROLES comment below. 'scheduler' is NOT top-tier; it
#   maps to v6.4 'manager' once the v6.3.2 role-rename migration runs.

from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Time, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.database import Base


# Roles that grant top-tier (owner-equivalent) access. Used by User.is_top_tier
# and PhoneTenantMap.is_top_tier. Kept as a module-level tuple so both models
# share one source of truth — change here only.
#
# 'proprietor' is included as a synonym for 'owner' — they refer to the same
# real-world role (the factory's primary owner) and are used interchangeably
# in this codebase. 'proprietor' is the legacy spelling produced by
# auth_service.register_tenant_and_user(); 'owner' is the v6.4 spelling.
# Until the v6.3.2 role-rename migration runs, both spellings coexist and
# both must grant top-tier access.
TOP_TIER_ROLES: tuple = ("owner", "proprietor", "factory_manager", "co_owner")


class Tenant(Base):
    __tablename__ = "tenants"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String(255), nullable=False)
    slug       = Column(String(100), unique=True, nullable=False, index=True)
    plan       = Column(String(20), nullable=False, default="free")
    is_active  = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # AI usage tracking - reset daily by get_or_reset_usage() in ai_chat.py
    # Added v4.0.9 via migration 019
    ai_queries_today = Column(Integer, nullable=False, server_default="0")
    ai_tokens_today  = Column(Integer, nullable=False, server_default="0")
    ai_queries_date  = Column(Date, nullable=True)

    # Industry context for AI terminology - added v4.0.8
    industry_type = Column(String(50), nullable=True)

    # ---- v6.3.1 entry-gate columns (migration 027) ------------------------
    # Allowed-value validation lives in app/services/role_helpers.py and
    # tenant-config helpers (added in later v6.4 iterations) — the column
    # itself is a plain String per the project's existing convention.

    # Which surface this tenant primarily uses to drive the system.
    # Allowed: 'whatsapp_first' | 'desktop_first' | 'hybrid'.
    entry_mode = Column(String(20), nullable=False, server_default="desktop_first")

    # Factory size bucket. Nullable until v6.3.4 classifier runs.
    # Allowed when set: 'small' | 'medium' | 'large'.
    size_segment = Column(String(20), nullable=True)

    # Morning briefing config — opt-in WhatsApp summary.
    briefing_morning_enabled = Column(Boolean, nullable=False, server_default="false")
    briefing_morning_time    = Column(Time,    nullable=False, server_default="07:30:00")

    # Evening briefing config — opt-in end-of-day recap.
    briefing_evening_enabled = Column(Boolean, nullable=False, server_default="false")
    briefing_evening_time    = Column(Time,    nullable=False, server_default="18:30:00")

    # IANA timezone for converting briefing times to UTC. v6.3.1 supports
    # 'Asia/Kolkata' only; multi-timezone support tracked in SRS §6.28.4.
    briefing_timezone = Column(String(50), nullable=False, server_default="Asia/Kolkata")

    # Comma-separated ISO weekday numbers (1=Mon..7=Sun). Default Mon-Sat.
    briefing_working_days = Column(String(20), nullable=False, server_default="1,2,3,4,5,6")

    # How this tenant was created. 'desktop_signup' covers everyone before
    # v6.3.1; 'whatsapp_signup' arrives in v6.3.3.
    created_via = Column(String(30), nullable=False, server_default="desktop_signup")

    # ---- v6.3.16 Day-7 First-Insight Gate columns (migration 031) ---------
    # first_briefing_sent_at is the day-counting anchor for the Day-7 owner
    # gate. Set the first time briefings/dispatcher.dispatch_briefing emits
    # a successful morning briefing.sent for this tenant; never updated
    # after. NULL means "no morning briefing has ever landed" — the gate
    # silently skips such tenants. See app/services/day7_insight.py.
    first_briefing_sent_at = Column(DateTime(timezone=True), nullable=True)

    # engagement_ladder_state is the per-tenant idempotency ledger for
    # engagement-ladder messages. v6.3.16 writes one key:
    # 'day7_owner_sent_at' — its presence means the Day-7 gate has been
    # processed (sent OR suppressed) and must not fire again. v6.4.0 will
    # add more keys here for the full ladder.
    #
    # Note: server_default is set in migration 031 ('{}'::jsonb) for
    # existing Postgres rows. The Python-side default=dict covers both
    # production new rows and the SQLite test path where ::jsonb DDL
    # is incompatible (the conftest patches JSONB->JSON and never
    # applies the server_default text).
    engagement_ladder_state = Column(
        JSONB, nullable=False, default=dict,
    )

    users          = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    refresh_tokens = relationship("RefreshToken", back_populates="tenant", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, index=True)
    tenant_id       = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    email           = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role            = Column(String(20), nullable=False, default="viewer")
    is_active       = Column(Boolean, nullable=False, default=True)
    created_at      = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    updated_at      = Column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ---- v6.3.1 entry-gate columns (migration 027) ------------------------
    # Per-user briefing time overrides. Nullable — when NULL, the tenant-
    # level briefing_morning_time / briefing_evening_time apply.
    briefing_time_override_morning = Column(Time, nullable=True)
    briefing_time_override_evening = Column(Time, nullable=True)

    # Per-user opt-out flag for briefings. Default True so anyone whose
    # tenant enables briefings receives them; users mute via /unsubscribe.
    briefing_subscribed = Column(Boolean, nullable=False, server_default="true")

    # User's WhatsApp number in E.164 format (e.g. '+919876543210').
    # Indexed at the DB level (idx_users_phone_e164 from migration 027) —
    # resolve_identity() looks up users by phone on every inbound message.
    phone_e164 = Column(String(20), nullable=True, index=True)

    # How this user was created. Mirrors tenants.created_via but at user
    # granularity — a co_owner invited via WhatsApp would be 'whatsapp_invite'.
    created_via = Column(String(30), nullable=False, server_default="desktop_signup")

    tenant         = relationship("Tenant", back_populates="users")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")

    @property
    def is_top_tier(self) -> bool:
        """
        True if this user holds an owner-equivalent role (v6.4 RBAC).

        Called by:    permission decorators added in v6.3.5 (require_top_tier)
        Calls into:   nothing — pure property
        Side effects: none

        TOP_TIER_ROLES contains 'owner', 'proprietor' (legacy synonym for owner),
        'factory_manager', and 'co_owner'. Returns False for None and for any
        other role (including 'scheduler', 'manager', 'viewer').
        """
        if self.role is None:
            return False
        return self.role in TOP_TIER_ROLES


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id  = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(255), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked    = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    user   = relationship("User", back_populates="refresh_tokens")
    tenant = relationship("Tenant", back_populates="refresh_tokens")
