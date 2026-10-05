"""
licensing_server/routes/auth.py — Authentication endpoints: register, login, logout, refresh.
"""

from __future__ import annotations

import os

from typing import Optional

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from licensing_server.database import get_db
from licensing_server.middleware.rate_limiter import (
    limit_login, limit_password_reset, limit_register,
    record_login_failure, record_login_success,
)
from licensing_server.services.auth_service import AuthService
from licensing_server.services.email_service import EmailService

router = APIRouter(prefix="/auth", tags=["Authentication"])
auth_service = AuthService()
email_service = EmailService()


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=5)
    password: str = Field(..., min_length=8)
    display_name: str = Field(default="CHARLIE User", max_length=128)


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
def register(req: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    limit_register(request)
    ok, msg, data = auth_service.register(db, req.email, req.password, req.display_name)
    if not ok:
        return {"success": False, "error": msg}
    # Dispatch email verification if token is generated
    if data and "user_id" in data:
        verify_token = auth_service.create_email_verification_token(str(data["user_id"]))
        email_service.send_verification_email(req.email, verify_token)
    return {"success": True, "message": msg, "data": data}


@router.post("/login")
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    # Stage 1: IP sliding window + per-email lockout check
    limit_login(request, email=req.email)
    # Stage 2: Authenticate credentials
    ok, msg, data = auth_service.login(db, req.email, req.password)
    if not ok:
        record_login_failure(req.email)   # increment failure counter / escalate lockout
        return {"success": False, "error": msg}
    record_login_success(req.email)       # clear lockout state on success
    return {"success": True, "message": msg, "data": data}


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None


class ResendVerificationRequest(BaseModel):
    email: str


@router.post("/refresh")
def refresh(req: RefreshRequest, db: Session = Depends(get_db)):
    ok, msg, data = auth_service.refresh(db, req.refresh_token)
    if not ok:
        return {"success": False, "error": msg}
    return {"success": True, "message": msg, "data": data}


@router.post("/logout")
def logout(
    req: Optional[LogoutRequest] = None,
    authorization: Optional[str] = Header(default=None),
):
    """Server-side JWT token invalidation via in-memory TTL blacklist."""
    revoked_count = 0
    # Revoke access token from Authorization header if present
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        if auth_service.revoke_jwt(token):
            revoked_count += 1

    # Revoke refresh token if supplied in request body
    if req and req.refresh_token:
        if auth_service.revoke_jwt(req.refresh_token):
            revoked_count += 1

    return {
        "success": True,
        "message": "Logged out successfully. Tokens revoked server-side.",
        "revoked_count": revoked_count,
    }


@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    """Request password reset token. Safe response avoids account enumeration."""
    limit_password_reset(request)
    from licensing_server.database import UserDB
    user = db.query(UserDB).filter(UserDB.email == req.email.lower().strip()).first()
    if not user:
        return {"success": True, "message": "If account exists, password reset instructions sent."}

    token = auth_service.create_password_reset_token(str(user.id), session_version=getattr(user, "session_version", 1) or 1)
    email_service.send_password_reset_email(str(user.email), token)
    return {
        "success": True,
        "message": "If account exists, password reset instructions sent.",
    }


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


@router.post("/resend-verification")
def resend_verification(req: ResendVerificationRequest, db: Session = Depends(get_db)):
    """Resend email verification token for unverified accounts."""
    from licensing_server.database import UserDB
    user = db.query(UserDB).filter(UserDB.email == req.email.lower().strip()).first()
    if not user:
        return {"success": True, "message": "If account exists, verification email sent."}
    if user.email_verified:
        return {"success": True, "message": "Email is already verified."}

    token = auth_service.create_email_verification_token(str(user.id))
    email_service.send_verification_email(str(user.email), token)
    return {"success": True, "message": "Verification email sent."}

