"""
licensing_server/routes/me.py — Standard Customer Self-Service API.

All endpoints strictly derive user identity from the verified Bearer token (JWT),
providing mathematical IDOR immunity. Customers cannot access other users' data.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from licensing_server.config import config
from licensing_server.database import (
    DeviceDB,
    DeviceStatusEnum,
    PaymentDB,
    SubscriptionDB,
    SubscriptionStatus,
    SupportTicketDB,
    UserDB,
    get_db,
)
from licensing_server.middleware.auth_middleware import get_current_user
from licensing_server.services.auth_service import AuthService
from licensing_server.services.support_service import SupportService

router = APIRouter(prefix="/me", tags=["Customer Self-Service (IDOR Immune)"])
auth_service = AuthService()
support_service = SupportService()


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=128)


class TransferDeviceRequest(BaseModel):
    confirm: bool = Field(default=True)


class CustomerTicketRequest(BaseModel):
    subject: str = Field(..., min_length=3, max_length=255)
    message: str = Field(..., min_length=5)
    category: str = Field(default="OTHER")
    error_id: Optional[str] = Field(default=None)
    app_version: str = Field(default="1.0.0")
    os_version: str = Field(default="Windows")
    raw_diagnostics: Optional[Dict[str, Any]] = Field(default_factory=dict)
    priority: str = Field(default="NORMAL")


class CustomerTicketReplyRequest(BaseModel):
    reply_text: str = Field(..., min_length=1)


# ── Profile ──────────────────────────────────────────────────────────────────

@router.get("")
@router.get("/")
def get_my_profile(user: UserDB = Depends(get_current_user)):
    """Fetch profile of currently authenticated user."""
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": getattr(user, "role", "CUSTOMER"),
        "account_status": user.account_status,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


# ── Subscription ─────────────────────────────────────────────────────────────

@router.get("/subscription")
def get_my_subscription(user: UserDB = Depends(get_current_user)):
    """Fetch current subscription plan and expiry."""
    sub = user.subscription
    return {
        "plan": sub.plan if sub else "STARTER",
        "status": sub.status if sub else "FREE",
        "started_at": sub.started_at.isoformat() if sub and sub.started_at else None,
        "expires_at": sub.expires_at.isoformat() if sub and sub.expires_at else None,
        "is_lifetime": sub.plan == "LIFETIME" if sub else False,
        "device_limit": sub.device_limit if sub else 1,
        "active_device_id": sub.active_device_id if sub else None,
    }


# ── Devices ──────────────────────────────────────────────────────────────────

@router.get("/devices")
def get_my_devices(
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fetch active PC bound to this user's account."""
    devices = db.query(DeviceDB).filter(DeviceDB.user_id == user.id).all()
    sub = user.subscription
    active_id = sub.active_device_id if sub else None
    return [
        {
            "id": d.id,
            "name": d.device_name,
            "os": d.os_type,
            "app_version": d.app_version,
            "status": d.status,
            "is_active_license_holder": (d.id == active_id),
            "activated_at": d.activated_at.isoformat() if d.activated_at else None,
            "last_seen": d.last_seen.isoformat() if d.last_seen else None,
        }
        for d in devices
    ]


@router.post("/devices/deactivate")
def deactivate_my_device(
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Customer deactivates current active PC, freeing slot."""
    sub = user.subscription
    if not sub or not sub.active_device_id:
        return {"status": "ok", "message": "No active PC bound to deactivate."}

    dev = db.query(DeviceDB).filter(DeviceDB.id == sub.active_device_id).first()
    if dev:
        dev.status = DeviceStatusEnum.INACTIVE.value
    sub.active_device_id = None
    db.commit()
    return {"status": "ok", "message": "Device deactivated successfully."}


@router.post("/devices/transfer")
def transfer_my_device(
    req: TransferDeviceRequest,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Customer frees license slot to transfer to new machine."""
    sub = user.subscription
    if not sub:
        raise HTTPException(status_code=400, detail="Subscription not found.")

    if sub.active_device_id:
        dev = db.query(DeviceDB).filter(DeviceDB.id == sub.active_device_id).first()
        if dev:
            dev.status = DeviceStatusEnum.INACTIVE.value
        sub.active_device_id = None
        db.commit()

    return {"status": "ok", "message": "License slot cleared for transfer. Log in on your new machine."}


# ── Payments ─────────────────────────────────────────────────────────────────

@router.get("/payments")
def get_my_payments(
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fetch customer's verified billing transactions."""
    payments = (
        db.query(PaymentDB)
        .filter(PaymentDB.user_id == user.id)
        .order_by(PaymentDB.created_at.desc())
        .limit(25)
        .all()
    )
    return [
        {
            "id": p.id,
            "amount_inr": p.amount_paise / 100.0,
            "plan": p.plan,
            "status": p.status,
            "receipt_ref": p.payment_id or p.order_id,
            "date": p.created_at.isoformat() if p.created_at else None,
        }
        for p in payments
    ]


# ── Downloads ────────────────────────────────────────────────────────────────

@router.get("/downloads")
def get_downloads(user: UserDB = Depends(get_current_user)):
    """Return official verified installer metadata."""
    return {
        "installer_name": "CHARLIE-Setup.exe",
        "version": config.LATEST_APP_VERSION,
        "download_url": config.INSTALLER_DOWNLOAD_URL,
        "file_size": "158 MB",
        "sha256": "cba1489b6bc599007037820318113e5edfa6e6943e3a4fbd4f8214e01953882a",
        "os_support": "Windows 10 / 11 (64-bit)",
        "release_notes": "CHARLIE v1.0.0-rc.1 official release with autonomous desktop execution.",
    }


# ── Support ──────────────────────────────────────────────────────────────────

@router.get("/support")
def get_my_support_tickets(
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List customer tickets (internal staff notes are strictly excluded)."""
    return support_service.get_user_tickets(db, user_id=user.id)


@router.post("/support")
def create_my_support_ticket(
    req: CustomerTicketRequest,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create support ticket with automatic secret redacting on diagnostics."""
    success, msg, ticket = support_service.create_ticket(
        db=db,
        user=user,
        subject=req.subject,
        message=req.message,
        category=req.category,
        error_id=req.error_id,
        app_version=req.app_version,
        os_version=req.os_version,
        raw_diagnostics=req.raw_diagnostics,
        priority=req.priority,
    )
    if not success or not ticket:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg, "ticket_number": ticket.ticket_number}


@router.post("/support/{ticket_id}/reply")
def reply_my_support_ticket(
    ticket_id: str,
    req: CustomerTicketReplyRequest,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Customer sends message in support ticket thread."""
    success, msg = support_service.add_customer_reply(
        db=db, ticket_id=ticket_id, user_id=user.id, reply_text=req.reply_text
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


# ── Security ─────────────────────────────────────────────────────────────────

@router.post("/security/change-password")
def change_my_password(
    req: ChangePasswordRequest,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Secure password change with session invalidation."""
    success, msg = auth_service.change_password(
        db, user=user, old_pass=req.current_password, new_pass=req.new_password
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


@router.post("/security/logout-all")
def logout_all_my_sessions(
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Invalidate all active sessions across all devices."""
    auth_service.invalidate_all_sessions(db, user=user)
    return {"status": "ok", "message": "All sessions logged out successfully."}
