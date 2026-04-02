"""app/core/dependencies.py — FastAPI auth + RBAC dependencies"""
from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session
from app.core.security import decode_access_token
from app.database import get_db
from app.models.auth import User

bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Session = Depends(get_db),
) -> User:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
        tenant_id = int(payload["tenant_id"])
    except (JWTError, KeyError, ValueError):
        raise exc
    user = db.query(User).filter(
        User.id == user_id, User.tenant_id == tenant_id, User.is_active == True
    ).first()
    if not user:
        raise exc
    return user


def require_role(*allowed_roles: str):
    def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' not permitted. Required: {list(allowed_roles)}",
            )
        return user
    return _check


ProprietorOnly = Depends(require_role("proprietor"))
SchedulerAbove = Depends(require_role("proprietor", "scheduler"))
AnyAuthUser    = Depends(get_current_user)
