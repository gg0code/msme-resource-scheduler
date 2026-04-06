# app/models/auth.py - Version 1.2
# Branch: both
#
# FILE PURPOSE
# SQLAlchemy ORM models for core auth entities: Tenant, User, RefreshToken.
# Introduced in v1.0. AI usage tracking columns added v4.0.9.
# Layer: model
#
# WHAT THIS FILE DOES
# 1. Defines Tenant - top-level org unit, holds plan + AI quota tracking
# 2. Defines User - belongs to one Tenant, has a role
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
# Purpose      : Authenticated user belonging to a Tenant.
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
#
# INTERN NOTES
# - updated_at uses lambda: datetime.now(timezone.utc) not datetime.utcnow (deprecated py3.12)
# - ai_queries_date is a Date column (not DateTime) - resets daily in get_or_reset_usage()
# - ai_tokens_today tracked for future token-based limiting but not enforced yet
# - industry_type added v4.0.8 for AI terminology context

from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.orm import relationship
from app.database import Base


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

    tenant         = relationship("Tenant", back_populates="users")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")


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
