"""
licensing_server/routes/support.py — Customer Support Ticket API.

Enables desktop and web clients to raise support tickets with automatically
sanitized diagnostics and secret-scrubbed system information.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from licensing_server.database import UserDB, get_db
from licensing_server.middleware.auth_middleware import get_current_user
from licensing_server.services.support_service import SupportService

router = APIRouter(prefix="/support", tags=["Customer Support"])
support_service = SupportService()


class CreateTicketRequest(BaseModel):
    subject: str = Field(..., min_length=3, max_length=255)
    message: str = Field(..., min_length=5)
    category: str = Field(default="OTHER", description="BILLING, LICENSE, CRASH, FEATURE, OTHER")
    error_id: Optional[str] = Field(default=None)
    app_version: str = Field(default="1.0.0")
    os_version: str = Field(default="Windows")
    raw_diagnostics: Optional[Dict[str, Any]] = Field(default_factory=dict)
    priority: str = Field(default="NORMAL")


@router.post("/tickets")
def create_support_ticket(
    req: CreateTicketRequest,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a customer support ticket. All diagnostics undergo automatic secret redaction."""
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

    return {
        "status": "ok",
        "message": msg,
        "ticket": {
            "ticket_number": ticket.ticket_number,
            "subject": ticket.subject,
            "status": ticket.status,
            "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        },
    }


@router.get("/tickets")
def list_my_tickets(
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all tickets raised by the authenticated user."""
    return support_service.get_user_tickets(db, user_id=user.id)


class CrashReportUploadRequest(BaseModel):
    crash: Dict[str, Any]
    bundle: Optional[Dict[str, Any]] = Field(default_factory=dict)


@router.post("/crash-report")
def upload_crash_report(
    req: CrashReportUploadRequest,
    db: Session = Depends(get_db),
):
    """Receive sanitized crash report from desktop client.
    Groups identical stack signatures into a single incident.
    """
    clean_crash = support_service.sanitize_diagnostics(req.crash)
    clean_bundle = support_service.sanitize_diagnostics(req.bundle or {})

    incident, is_new = support_service.record_crash_incident(db, clean_crash)

    return {
        "status": "ok",
        "crash_id": clean_crash.get("crash_id"),
        "incident_number": incident.incident_number,
        "incident_status": incident.status,
        "is_new_incident": is_new,
        "occurrences": incident.occurrences,
    }


@router.get("/known-issues")
def list_known_issues(
    version: str = "",
    db: Session = Depends(get_db),
):
    """List active known issues with workarounds."""
    return support_service.get_known_issues(db, user_version=version)


class DiagnosticConsentRequest(BaseModel):
    request_id: str
    approved: bool
    diagnostic_bundle: Optional[Dict[str, Any]] = Field(default_factory=dict)


@router.post("/tickets/{ticket_id}/consent-diagnostics")
def consent_diagnostics(
    ticket_id: str,
    req: DiagnosticConsentRequest,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Customer approves or declines remote diagnostic collection request."""
    success, msg = support_service.respond_diagnostic_request(
        db=db,
        request_id=req.request_id,
        user_id=user.id,
        approved=req.approved,
        diagnostic_bundle=req.diagnostic_bundle,
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


class CustomerReplyRequest(BaseModel):
    reply_text: str = Field(..., min_length=2)


@router.post("/tickets/{ticket_id}/reply")
def reply_ticket_customer(
    ticket_id: str,
    req: CustomerReplyRequest,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Customer sends message in support ticket thread."""
    success, msg = support_service.add_customer_reply(
        db=db,
        ticket_id=ticket_id,
        user_id=user.id,
        reply_text=req.reply_text,
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}

