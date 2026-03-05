"""app/routers/auth.py — register, login, refresh, logout, me"""
from typing import Optional
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from app.core.dependencies import get_current_user
from app.database import get_db
from app.schemas.auth import LoginRequest, MessageResponse, RegisterRequest, TokenResponse, UserResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
COOKIE_NAME = "refresh_token"
COOKIE_MAX_AGE = 7 * 24 * 60 * 60


def _set_cookie(response: Response, token: str):
    response.set_cookie(key=COOKIE_NAME, value=token, httponly=True,
        samesite="lax", secure=False, max_age=COOKIE_MAX_AGE, path="/auth")

def _clear_cookie(response: Response):
    response.delete_cookie(key=COOKIE_NAME, path="/auth")


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    result = auth_service.register_tenant_and_user(payload, db)
    _set_cookie(response, result["refresh_token"])
    return TokenResponse(access_token=result["access_token"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    result = auth_service.login(payload, db)
    _set_cookie(response, result["refresh_token"])
    return TokenResponse(access_token=result["access_token"])


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    response: Response,
    refresh_token: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    db: Session = Depends(get_db),
):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token provided")
    result = auth_service.refresh_access_token(refresh_token, db)
    _set_cookie(response, result["refresh_token"])
    return TokenResponse(access_token=result["access_token"])


@router.post("/logout", response_model=MessageResponse)
def logout(
    response: Response,
    refresh_token: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    db: Session = Depends(get_db),
):
    if refresh_token:
        auth_service.logout(refresh_token, db)
    _clear_cookie(response)
    return MessageResponse(message="Logged out successfully")


@router.get("/me", response_model=UserResponse)
def me(current_user=Depends(get_current_user)):
    return current_user
