"""app/models/auth.py — V1.3
Added: industry_type to Tenant (v4.0.1)
"""
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, text, Date
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
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow, nullable=False)

    # AI usage tracking (migration 007)
    ai_queries_today = Column(Integer, default=0, nullable=False, server_default='0')
    ai_queries_date  = Column(Date, nullable=True)
    ai_queries_limit = Column(Integer, default=50, nullable=False, server_default='50')
    ai_tokens_today  = Column(Integer, default=0, nullable=False, server_default='0')

    # Job ID prefix (migration 008)
    job_id_prefix = Column(String(10), nullable=True)

    # v4.0.1 — industry profile selected during registration
    # Values: printing | manufacturing | fabrication | chemical | field_service
    industry_type = Column(String(50), nullable=True, server_default='printing')

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
    updated_at      = Column(DateTime(timezone=True), server_default=text("now()"), onupdate=datetime.utcnow, nullable=False)
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
