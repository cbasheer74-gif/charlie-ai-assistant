"""
licensing_server/routes/account.py — Account management endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from licensing_server.database import SubscriptionDB, UserDB, get_db
from licensing_server.middleware.auth_middleware import get_current_user

router = APIRouter(prefix="/account", tags=["Account"])


@router.get("/")
def get_account(
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sub = db.query(SubscriptionDB).filter(SubscriptionDB.user_id == user.id).first()
    return {
        "success": True,
        "data": {
            "user_id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "account_status": user.account_status,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "plan": sub.plan if sub else "STARTER",
            "subscription_status": sub.status if sub else "FREE",
            "active_device_id": sub.active_device_id if sub else None,
            "expires_at": sub.expires_at.isoformat() if sub and sub.expires_at else None,
        },
    }


class UpdateDisplayNameRequest(BaseModel):
    display_name: str


@router.patch("/")
def update_account(
    req: UpdateDisplayNameRequest,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user.display_name = req.display_name
    db.commit()
    return {"success": True, "message": "Account updated."}
