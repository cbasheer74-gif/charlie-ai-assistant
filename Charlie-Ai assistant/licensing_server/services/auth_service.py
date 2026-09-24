"""
licensing_server/services/auth_service.py — User authentication: bcrypt hashing, JWT tokens, session management.

Passwords NEVER stored in plaintext. Uses bcrypt with automatic salt.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import bcrypt
import jwt
from sqlalchemy.orm import Session

from licensing_server.config import config
from licensing_server.database import (
    AccountStatus,
    LicenseEventDB,
    LicenseEventType,
    PlanTier,
    SubscriptionDB,
    SubscriptionStatus,
    UserDB,
)


class AuthService:
    """Handles registration, login, JWT issuance, and token refresh."""

    @staticmethod
    def hash_password(password: str) -> str:
        """Bcrypt hash with automatic salt generation."""
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """Constant-time bcrypt comparison."""
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

    @staticmethod
    def create_access_token(user_id: str, email: str, role: str = "USER", session_version: int = 1) -> str:
        payload = {
            "sub": user_id,
            "email": email,
            "role": role,
            "sv": session_version,
            "type": "access",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=config.JWT_ACCESS_EXPIRY_MINUTES),
            "iat": datetime.now(timezone.utc),
        }
        return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)

    @staticmethod
    def create_refresh_token(user_id: str, session_version: int = 1) -> str:
        payload = {
            "sub": user_id,
            "sv": session_version,
            "type": "refresh",
            "exp": datetime.now(timezone.utc) + timedelta(days=config.JWT_REFRESH_EXPIRY_DAYS),
            "iat": datetime.now(timezone.utc),
        }
        return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)

    @staticmethod
    def decode_token(token: str) -> Optional[dict]:
        """Decode and validate JWT. Returns None on any failure."""
        try:
            return jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return None

    def register(self, db: Session, email: str, password: str, display_name: str = "JARVIS User") -> Tuple[bool, str, Optional[dict]]:
        """Create new user account with STARTER subscription."""
        # Check duplicate
        existing = db.query(UserDB).filter(UserDB.email == email).first()
        if existing:
            return False, "Email already registered.", None

        user_id = f"usr_{uuid.uuid4().hex[:16]}"
        sub_id = f"sub_{uuid.uuid4().hex[:16]}"

        user = UserDB(
            id=user_id,
            email=email.lower().strip(),
            password_hash=self.hash_password(password),
            display_name=display_name,
            account_status=AccountStatus.ACTIVE.value,
        )

        subscription = SubscriptionDB(
            id=sub_id,
            user_id=user_id,
            plan=PlanTier.STARTER.value,
            status=SubscriptionStatus.FREE.value,
            device_limit=1,
        )

        db.add(user)
        db.add(subscription)
        db.commit()

        access_token = self.create_access_token(user_id, email)
        refresh_token = self.create_refresh_token(user_id)

        return True, "Account created.", {
            "user_id": user_id,
            "email": email,
            "display_name": display_name,
            "plan": PlanTier.STARTER.value,
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

    def login(self, db: Session, email: str, password: str) -> Tuple[bool, str, Optional[dict]]:
        """Authenticate user and issue tokens."""
        user = db.query(UserDB).filter(UserDB.email == email.lower().strip()).first()
        if not user:
            return False, "Invalid email or password.", None

        if not self.verify_password(password, user.password_hash):
            return False, "Invalid email or password.", None

        if user.account_status == AccountStatus.BANNED.value:
            return False, "Account suspended. Contact support.", None

        # Update last login
        user.last_login = datetime.now(timezone.utc)
        db.commit()

        # Audit
        event = LicenseEventDB(
            id=f"evt_{uuid.uuid4().hex[:16]}",
            user_id=user.id,
            event_type=LicenseEventType.LOGIN.value,
            details_json="{}",
        )
        db.add(event)
        db.commit()

        # Get subscription
        sub = db.query(SubscriptionDB).filter(SubscriptionDB.user_id == user.id).first()

        access_token = self.create_access_token(user.id, user.email, role=getattr(user, "role", "USER") or "USER", session_version=getattr(user, "session_version", 1) or 1)
        refresh_token = self.create_refresh_token(user.id, session_version=getattr(user, "session_version", 1) or 1)

        return True, "Login successful.", {
            "user_id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": getattr(user, "role", "USER") or "USER",
            "plan": sub.plan if sub else PlanTier.STARTER.value,
            "subscription_status": sub.status if sub else SubscriptionStatus.FREE.value,
            "active_device_id": sub.active_device_id if sub else None,
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

    def refresh(self, db: Session, refresh_token: str) -> Tuple[bool, str, Optional[dict]]:
        """Issue new access token from valid refresh token."""
        payload = self.decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            return False, "Invalid or expired refresh token.", None

        user_id = payload["sub"]
        user = db.query(UserDB).filter(UserDB.id == user_id).first()
        if not user:
            return False, "User not found.", None

        user_sv = getattr(user, "session_version", 1) or 1
        token_sv = payload.get("sv", 1)
        if token_sv != user_sv:
            return False, "Session invalidated. Please log in again.", None

        new_access = self.create_access_token(user.id, user.email, role=getattr(user, "role", "USER") or "USER", session_version=user_sv)
        return True, "Token refreshed.", {"access_token": new_access}

    def get_user_from_token(self, db: Session, token: str) -> Optional[UserDB]:
        """Extract and validate user from access token, verifying session version."""
        payload = self.decode_token(token)
        if not payload or payload.get("type") != "access":
            return None
        user = db.query(UserDB).filter(UserDB.id == payload["sub"]).first()
        if not user:
            return None
        user_sv = getattr(user, "session_version", 1) or 1
        token_sv = payload.get("sv", 1)
        if token_sv != user_sv:
            return None
        return user

    def change_password(self, db: Session, user: UserDB, old_pass: str, new_pass: str) -> Tuple[bool, str]:
        """Change password, verify old password, and increment session_version."""
        if not self.verify_password(old_pass, user.password_hash):
            return False, "Current password incorrect."
        if len(new_pass) < 6:
            return False, "Password must be at least 6 characters."

        user.password_hash = self.hash_password(new_pass)
        user.session_version = (getattr(user, "session_version", 1) or 1) + 1
        db.commit()
        return True, "Password changed successfully. All sessions revoked."

    def invalidate_all_sessions(self, db: Session, user: UserDB) -> None:
        """Increment session_version so previous JWTs become invalid."""
        user.session_version = (getattr(user, "session_version", 1) or 1) + 1
        db.commit()

    @staticmethod
    def create_password_reset_token(user_id: str) -> str:
        """Generate time-limited password reset token (15 mins)."""
        payload = {
            "sub": user_id,
            "type": "password_reset",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
            "iat": datetime.now(timezone.utc),
        }
        return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)

    def reset_password(self, db: Session, token: str, new_password: str) -> Tuple[bool, str]:
        """Verify token and update password, invalidating old sessions."""
        payload = self.decode_token(token)
        if not payload or payload.get("type") != "password_reset":
            return False, "Invalid or expired password reset token."

        if len(new_password) < 6:
            return False, "Password must be at least 6 characters."

        user = db.query(UserDB).filter(UserDB.id == payload["sub"]).first()
        if not user:
            return False, "User not found."

        user.password_hash = self.hash_password(new_password)
        user.session_version = (getattr(user, "session_version", 1) or 1) + 1
        db.commit()
        return True, "Password reset successfully. Please log in with your new password."

    @staticmethod
    def create_email_verification_token(user_id: str) -> str:
        """Generate email verification token (24 hours)."""
        payload = {
            "sub": user_id,
            "type": "email_verify",
            "exp": datetime.now(timezone.utc) + timedelta(hours=24),
            "iat": datetime.now(timezone.utc),
        }
        return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)

    def verify_email(self, db: Session, token: str) -> Tuple[bool, str]:
        """Validate email verification token."""
        payload = self.decode_token(token)
        if not payload or payload.get("type") != "email_verify":
            return False, "Invalid or expired verification token."

        user = db.query(UserDB).filter(UserDB.id == payload["sub"]).first()
        if not user:
            return False, "User not found."

        # Audit event
        event = LicenseEventDB(
            id=f"evt_{uuid.uuid4().hex[:16]}",
            user_id=user.id,
            event_type=LicenseEventType.LOGIN.value,
            details_json=json.dumps({"action": "EMAIL_VERIFIED"}),
        )
        db.add(event)
        db.commit()
        return True, "Email verified successfully."

