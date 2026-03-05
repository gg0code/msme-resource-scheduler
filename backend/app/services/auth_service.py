"""app/services/auth_service.py — register, login, refresh, logout"""
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.core.security import (
    create_access_token, generate_refresh_token, hash_password,
    hash_refresh_token, refresh_token_expiry, verify_password,
)
from app.models.auth import RefreshToken, Tenant, User
from app.schemas.auth import LoginRequest, RegisterRequest


def register_tenant_and_user(payload: RegisterRequest, db: Session) -> dict:
    if db.query(Tenant).filter(Tenant.slug == payload.slug).first():
        raise HTTPException(status_code=400, detail="Slug already taken")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    tenant = Tenant(name=payload.company_name, slug=payload.slug, plan="free")
    db.add(tenant)
    db.flush()
    user = User(tenant_id=tenant.id, email=payload.email,
                hashed_password=hash_password(payload.password), role="proprietor")
    db.add(user)
    db.flush()
    raw_refresh = _create_refresh_token(db, user)
    db.commit()
    db.refresh(user)
    access_token = create_access_token(user.id, tenant.id, user.role)
    return {"access_token": access_token, "refresh_token": raw_refresh, "user": user}


def login(payload: LoginRequest, db: Session) -> dict:
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")
    raw_refresh = _create_refresh_token(db, user)
    db.commit()
    access_token = create_access_token(user.id, user.tenant_id, user.role)
    return {"access_token": access_token, "refresh_token": raw_refresh, "user": user}


def refresh_access_token(raw_token: str, db: Session) -> dict:
    token_hash = hash_refresh_token(raw_token)
    now = datetime.now(timezone.utc)
    record = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.revoked == False,
        RefreshToken.expires_at > now,
    ).first()
    if not record:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    user = db.query(User).filter(User.id == record.user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    record.revoked = True
    raw_refresh = _create_refresh_token(db, user)
    db.commit()
    access_token = create_access_token(user.id, user.tenant_id, user.role)
    return {"access_token": access_token, "refresh_token": raw_refresh}


def logout(raw_token: str, db: Session) -> None:
    record = db.query(RefreshToken).filter(
        RefreshToken.token_hash == hash_refresh_token(raw_token)
    ).first()
    if record:
        record.revoked = True
        db.commit()


def _create_refresh_token(db: Session, user: User) -> str:
    raw = generate_refresh_token()
    db.add(RefreshToken(
        user_id=user.id, tenant_id=user.tenant_id,
        token_hash=hash_refresh_token(raw), expires_at=refresh_token_expiry(),
    ))
    return raw
