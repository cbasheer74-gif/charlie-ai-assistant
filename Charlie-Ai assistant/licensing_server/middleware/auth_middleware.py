"""
licensing_server/middleware/auth_middleware.py — JWT Bearer token validation for protected routes.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from licensing_server.database import UserDB, get_db
from licensing_server.services.auth_service import AuthService

security = HTTPBearer(auto_error=False)
auth_service = AuthService()


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> UserDB:
    """Extract and validate user from Bearer token. Raises 401 on failure."""
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    user = auth_service.get_user_from_token(db, credentials.credentials)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token.")

    if getattr(user, "account_status", "ACTIVE") != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is suspended or banned.")

    return user


async def require_support(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> UserDB:
    """Authorize SUPPORT, ADMIN, or OWNER role."""
    admin_key = request.headers.get("X-Admin-Key")
    from licensing_server.config import config
    if admin_key and config.ADMIN_API_KEY and admin_key == config.ADMIN_API_KEY:
        owner = db.query(UserDB).filter(UserDB.role.in_(["OWNER", "ADMIN"])).first()
        if not owner:
            owner = UserDB(
                id="usr_admin_system", email="admin@jarvis.local",
                password_hash="system_managed_no_login", display_name="System Administrator",
                role="OWNER", account_status="ACTIVE",
            )
        return owner

    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Staff credentials required.")

    user = auth_service.get_user_from_token(db, credentials.credentials)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

    role = str(getattr(user, "role", "CUSTOMER")).upper()
    if role not in ("SUPPORT", "ADMIN", "OWNER"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Support staff privileges required.")

    if getattr(user, "account_status", "ACTIVE") != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Staff account suspended.")

    return user


async def require_admin(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> UserDB:
    """Authorize ADMIN or OWNER role."""
    admin_key = request.headers.get("X-Admin-Key")
    from licensing_server.config import config
    if admin_key and config.ADMIN_API_KEY and admin_key == config.ADMIN_API_KEY:
        owner = db.query(UserDB).filter(UserDB.role.in_(["OWNER", "ADMIN"])).first()
        if not owner:
            owner = UserDB(
                id="usr_admin_system", email="admin@jarvis.local",
                password_hash="system_managed_no_login", display_name="System Administrator",
                role="OWNER", account_status="ACTIVE",
            )
        return owner

    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin credentials required.")

    user = auth_service.get_user_from_token(db, credentials.credentials)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

    role = str(getattr(user, "role", "CUSTOMER")).upper()
    if role not in ("ADMIN", "OWNER"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required.")

    if getattr(user, "account_status", "ACTIVE") != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin account suspended.")

    return user


async def require_owner(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> UserDB:
    """Authorize strictly OWNER role."""
    admin_key = request.headers.get("X-Admin-Key")
    from licensing_server.config import config
    if admin_key and config.ADMIN_API_KEY and admin_key == config.ADMIN_API_KEY:
        owner = db.query(UserDB).filter(UserDB.role == "OWNER").first()
        if not owner:
            owner = UserDB(
                id="usr_owner_system", email="owner@jarvis.local",
                password_hash="system_managed_no_login", display_name="Platform Owner",
                role="OWNER", account_status="ACTIVE",
            )
        return owner

    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Owner credentials required.")

    user = auth_service.get_user_from_token(db, credentials.credentials)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

    role = str(getattr(user, "role", "CUSTOMER")).upper()
    if role != "OWNER":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform Owner privileges required.")

    if getattr(user, "account_status", "ACTIVE") != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner account suspended.")

    return user


# Backward compatibility alias
get_current_admin_user = require_admin
