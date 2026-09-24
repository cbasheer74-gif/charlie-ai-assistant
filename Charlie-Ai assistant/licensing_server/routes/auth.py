"""
licensing_server/routes/auth.py — Authentication endpoints: register, login, logout, refresh.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from licensing_server.database import get_db
from licensing_server.middleware.rate_limiter import limit_login
from licensing_server.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])
auth_service = AuthService()


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=5)
    password: str = Field(..., min_length=8)
    display_name: str = Field(default="JARVIS User", max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=6)


class VerifyEmailRequest(BaseModel):
    token: str


@router.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    ok, msg, data = auth_service.register(db, req.email, req.password, req.display_name)
    if not ok:
        return {"success": False, "error": msg}
    return {"success": True, "message": msg, "data": data}


@router.post("/login")
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    limit_login(request)
    ok, msg, data = auth_service.login(db, req.email, req.password)
    if not ok:
        return {"success": False, "error": msg}
    return {"success": True, "message": msg, "data": data}


@router.post("/refresh")
def refresh(req: RefreshRequest, db: Session = Depends(get_db)):
    ok, msg, data = auth_service.refresh(db, req.refresh_token)
    if not ok:
        return {"success": False, "error": msg}
    return {"success": True, "message": msg, "data": data}


@router.post("/logout")
def logout():
    # Client-side: discard tokens. Server-side: token blacklist optional for production.
    return {"success": True, "message": "Logged out. Discard tokens on client."}


@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Request password reset token. Safe response avoids account enumeration."""
    from licensing_server.database import UserDB
    user = db.query(UserDB).filter(UserDB.email == req.email.lower().strip()).first()
    if not user:
        return {"success": True, "message": "If account exists, password reset instructions sent."}

    token = auth_service.create_password_reset_token(str(user.id))
    res = {
        "success": True,
        "message": "If account exists, password reset instructions sent.",
    }
    # In non-production/test environments, return token for test runners
    if os.getenv("JARVIS_ENV", "development").lower() != "production":
        res["reset_token"] = token
    return res


@router.post("/reset-password")
def reset_password(req: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Complete password reset using time-limited token."""
    ok, msg = auth_service.reset_password(db, req.token, req.new_password)
    if not ok:
        return {"success": False, "error": msg}
    return {"success": True, "message": msg}


@router.post("/verify-email")
def verify_email(req: VerifyEmailRequest, db: Session = Depends(get_db)):
    """Verify email address with verification token."""
    ok, msg = auth_service.verify_email(db, req.token)
    if not ok:
        return {"success": False, "error": msg}
    return {"success": True, "message": msg}

