"""
```python
"""
FILE PURPOSE
This file defines the core authentication and multi-tenancy data models for the ZetaOps 
Copilot system. It contains SQLAlchemy ORM models for Tenant, User, and RefreshToken 
tables that form the foundation of the application's security and tenant isolation. 
Introduced in the initial v4 release and sits at the data layer, these models are 
imported by CRUD operations, authentication services, and dependency injection functions 
to enforce tenant scoping across the entire application.

WHAT THIS FILE DOES — step by step
1. Imports SQLAlchemy column types, relationship functions, and the Base class for ORM models
2. Defines the Tenant model representing manufacturing businesses using the system
3. Sets up AI usage tracking fields (queries per day, token limits) added in migration 007
4. Adds job ID prefix customization field from migration 008
5. Includes industry_type field for business profile categorization (v4.0.1)
6. Defines the User model for individual accounts within each tenant
7. Creates the RefreshToken model for JWT refresh token management and revocation
8. Establishes foreign key relationships between all three models with CASCADE deletion

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : Tenant
Type         : SQLAlchemy ORM class
Purpose      : Represents a manufacturing business account in the system. Each tenant 
               is completely isolated from others and has their own users, jobs, machines, 
               and employees. Tracks AI usage quotas and industry-specific configuration.
Parameters   : None (ORM model)
Returns      : Database model instance when queried
Calls        : None directly (used by CRUD operations)
DB/API       : Primary table for tenant data, referenced by foreign keys in most other tables
Side effects : Cascade deletes all related users and refresh tokens when deleted

Name         : User
Type         : SQLAlchemy ORM class  
Purpose      : Represents individual user accounts within a tenant. Stores authentication 
               credentials, role-based permissions, and links to the parent tenant. Every 
               user belongs to exactly one tenant and inherits that tenant's permissions.
Parameters   : None (ORM model)
Returns      : Database model instance when queried
Calls        : None directly (used by authentication services)
DB/API       : Stores hashed passwords, never plaintext. References tenant via foreign key
Side effects : Cascade deletes all refresh tokens when user is deleted

Name         : RefreshToken
Type         : SQLAlchemy ORM class
Purpose      : Manages JWT refresh tokens for secure authentication. Stores hashed tokens 
               with expiration dates and revocation status. Allows users to stay logged in 
               while maintaining security through token rotation and selective revocation.
Parameters   : None (ORM model)
Returns      : Database model instance when queried
Calls        : None directly (used by auth services for token validation)
DB/API       : Stores token hashes, not raw tokens. References both user and tenant
Side effects : Tokens can be marked as revoked to invalidate sessions

WHO CALLS THIS FILE
- backend/app/crud/tenant_crud.py (creates and queries tenants)
- backend/app/crud/user_crud.py (user authentication and management)
- backend/app/crud/auth_crud.py (refresh token operations)
- backend/app/core/dependencies.py (get_current_user dependency injection)
- backend/app/services/auth_service.py (login, logout, token refresh)
- backend/app/routers/auth_router.py (authentication endpoints)
- backend/app/routers/tenant_router.py (tenant management endpoints)
- backend/alembic/versions/*.py (database migrations reference these models)

IMPORTS EXPLAINED
- datetime, timezone: Used for timestamp fields with timezone awareness in created_at/updated_at
- sqlalchemy.Boolean: Column type for is_active, revoked, and other true/false flags
- sqlalchemy.Column: Defines individual database table columns with types and constraints
- sqlalchemy.DateTime: Column type for timestamp fields with timezone support
- sqlalchemy.ForeignKey: Creates references between tables (user.tenant_id → tenants.id)
- sqlalchemy.Integer: Column type for primary keys and numeric fields like AI query counts
- sqlalchemy.String: Column type for text fields with maximum length constraints
- sqlalchemy.text: Allows raw SQL expressions like "now()" for server-side defaults
- sqlalchemy.Date: Column type for date-only fields like ai_queries_date
- sqlalchemy.orm.relationship: Defines ORM relationships for easy navigation between models
- app.database.Base: The declarative base class that all ORM models must inherit from

INTERN NOTES
- Easiest thing to break: Removing CASCADE from foreign keys will cause orphaned records and deletion failures when tenants are removed
- Non-obvious design decision: RefreshToken has both user_id AND tenant_id foreign keys for faster tenant-scoped queries without joins
- Most common mistake: Forgetting to add tenant_id to new models or missing the index=True on foreign key columns for query performance
- Design principle implemented: Principle #2 (tenant scoping) - every model either IS a tenant or has tenant_id for complete data isolation
- What to check if behaving unexpectedly: Verify migration 007 and 008 ran successfully, check that datetime fields use timezone-aware values
- Not v5-whatsapp specific: This is core authentication shared across all versions, but v5 adds PhoneTenantMap model in separate file
"""
```
"""

from datetime import datetime, timezone
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
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

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
    updated_at      = Column(DateTime(timezone=True), server_default=text("now()"), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
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
