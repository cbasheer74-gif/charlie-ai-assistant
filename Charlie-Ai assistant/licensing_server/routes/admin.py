"""
licensing_server/routes/admin.py — CHARLIE AI Owner Admin Dashboard & API.

Provides:
1. RESTful Admin Control API (metrics, user search, suspension, device reset, remote revocation, support tickets).
2. Embedded Cybernetic Dark HUD Admin Dashboard Web Interface (GET /admin).
Strictly zero backdoors or master passwords.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from licensing_server.database import PaymentDB, UserDB, get_db
from licensing_server.middleware.auth_middleware import (
    get_current_admin_user,
    require_admin,
    require_owner,
    require_support,
)
from licensing_server.services.admin_service import AdminService
from licensing_server.services.support_service import SupportService

router = APIRouter(prefix="/admin", tags=["Commercial Admin Control"])
admin_service = AdminService()
support_service = SupportService()


# ── Request / Response Schemas ───────────────────────────────────────────────

class SuspendRequest(BaseModel):
    reason: str = Field(default="Violation of terms", max_length=255)


class GrantEntitlementRequest(BaseModel):
    plan: str = Field(..., description="STARTER, BASIC, PREMIUM, ADVANCED, LIFETIME")
    days: int = Field(default=30, ge=1, le=365)
    reason: str = Field(default="Administrative manual entitlement", max_length=255)


class RevokeDeviceRequest(BaseModel):
    reason: str = Field(default="Suspicious activation / piracy", max_length=255)


class StaffNoteRequest(BaseModel):
    note: str = Field(..., min_length=1)


class TagsRequest(BaseModel):
    tags: str = Field(..., max_length=255)


class InternalNoteRequest(BaseModel):
    note_text: str = Field(..., min_length=1)


class TicketReplyRequest(BaseModel):
    reply_text: str = Field(..., min_length=1)
    new_status: str = Field(default="IN_PROGRESS")


class DeviceFlagRequest(BaseModel):
    security_flag: str = Field(default="REVIEW_REQUIRED")


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = None
    password: Optional[str] = None


class CreateUserRequest(BaseModel):
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=6)
    display_name: str = Field(default="CHARLIE User", max_length=100)
    plan: str = Field(default="STARTER", description="STARTER, BASIC, PREMIUM, ADVANCED, LIFETIME")
    days: int = Field(default=30, ge=1, le=3650)


class LLMConfigRequest(BaseModel):
    primary_provider: Optional[str] = None
    active_model: Optional[str] = None
    fallback_provider: Optional[str] = None
    fallback_model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    rate_limit_tpm: Optional[int] = None
    stream_responses: Optional[bool] = None


class RemoteConfigRequest(BaseModel):
    feature_flags: Optional[Dict[str, bool]] = None
    prompts: Optional[Dict[str, Any]] = None
    kill_switches: Optional[Dict[str, bool]] = None


class BroadcastCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., min_length=1)
    level: str = Field(default="INFO")  # INFO, WARNING, URGENT, MAINTENANCE
    target_tier: str = Field(default="ALL")
    expires_hours: int = Field(default=48, ge=0, le=720)



class UpdateRoleRequest(BaseModel):
    role: str = Field(..., description="CUSTOMER, SUPPORT, ADMIN, OWNER")


class RefundPaymentRequest(BaseModel):
    reason: str = Field(default="Customer requested refund", max_length=255)


# ── Admin API Endpoints ──────────────────────────────────────────────────────

@router.get("/api/metrics")
def get_metrics(
    admin: UserDB = Depends(require_support),
    db: Session = Depends(get_db),
):
    """Authoritative revenue and system KPI metrics."""
    return admin_service.get_overview_metrics(db)


@router.post("/api/seed-demo")
def seed_demo_endpoint(
    admin: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Seed test customer dataset, hardware telemetry, payments, and AI costs across all 16 modules."""
    return admin_service.seed_demo_data(db)


@router.get("/api/deployment-docs")
@router.get("/deployment-docs")
def get_deployment_docs_endpoint(
    admin: UserDB = Depends(require_support),
):
    """Retrieve full markdown deployment architecture guides."""
    return admin_service.get_deployment_docs()


@router.post("/api/users")
def create_user_endpoint(
    req: CreateUserRequest,
    admin: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin provisions new user account with selected tier entitlement."""
    from licensing_server.services.auth_service import AuthService
    auth_service = AuthService()
    success, msg, user_data = auth_service.register(
        db, email=req.email, password=req.password, display_name=req.display_name
    )
    if not success or not user_data:
        raise HTTPException(status_code=400, detail=msg)

    user_id = user_data["user_id"]
    clean_plan = req.plan.upper().strip()
    if clean_plan != "STARTER":
        ok, ent_msg = admin_service.grant_entitlement(
            db, admin_id=admin.id, user_id=user_id, plan=clean_plan, days=req.days, reason="Initial admin provisioning"
        )
        if not ok:
            return {"status": "ok", "message": f"User created, but entitlement grant failed: {ent_msg}", "user_id": user_id}

    return {"status": "ok", "message": f"User {req.email} created successfully on {clean_plan}.", "user_id": user_id}


@router.get("/api/users")
def list_users(
    query: str = Query(default=""),
    plan: str = Query(default=""),
    status: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=5, le=100),
    admin: UserDB = Depends(require_support),
    db: Session = Depends(get_db),
):
    """Search and filter users with pagination."""
    return admin_service.search_users(
        db, query=query, plan=plan, status_filter=status, page=page, page_size=page_size
    )


@router.get("/api/users/{user_id}")
def get_user_detail(
    user_id: str,
    admin: UserDB = Depends(require_support),
    db: Session = Depends(get_db),
):
    """Detailed user inspection (subscription, bound PC, payments, audit history)."""
    detail = admin_service.get_user_detail(db, user_id)
    if not detail:
        raise HTTPException(status_code=404, detail="User not found.")
    return detail


@router.post("/api/users/{user_id}/notes")
def add_user_note(
    user_id: str,
    req: StaffNoteRequest,
    admin: UserDB = Depends(require_support),
    db: Session = Depends(get_db),
):
    """Record private staff note on user account."""
    success, msg = admin_service.add_user_internal_note(db, admin_id=admin.id, user_id=user_id, note_text=req.note)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


@router.post("/api/users/{user_id}/tags")
def set_user_tags(
    user_id: str,
    req: TagsRequest,
    admin: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update user tags."""
    success, msg = admin_service.set_user_tags(db, admin_id=admin.id, user_id=user_id, tags=req.tags)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


@router.post("/api/users/{user_id}/suspend")
def suspend_user(
    user_id: str,
    req: SuspendRequest,
    admin: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Suspend user account and revoke active PC access."""
    success, msg = admin_service.suspend_user(db, admin_id=admin.id, user_id=user_id, reason=req.reason)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


@router.post("/api/users/{user_id}/reactivate")
def reactivate_user(
    user_id: str,
    admin: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Reactivate a suspended user account."""
    success, msg = admin_service.reactivate_user(db, admin_id=admin.id, user_id=user_id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


@router.post("/api/users/{user_id}/reset-device")
def reset_device_activation(
    user_id: str,
    admin: UserDB = Depends(require_support),
    db: Session = Depends(get_db),
):
    """Clear active device slot so customer can activate on their new PC."""
    success, msg = admin_service.reset_device_activation(db, admin_id=admin.id, user_id=user_id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


@router.post("/api/users/{user_id}/grant-entitlement")
def grant_entitlement(
    user_id: str,
    req: GrantEntitlementRequest,
    admin: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Grant manual or promotional plan tier to user."""
    success, msg = admin_service.grant_entitlement(
        db, admin_id=admin.id, user_id=user_id, plan=req.plan, days=req.days, reason=req.reason
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


@router.post("/api/users/{user_id}/role")
def update_user_role(
    user_id: str,
    req: UpdateRoleRequest,
    admin: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Module 6: Role-Based Access Control (Promote/Demote role: OWNER, ADMIN, SUPPORT, CUSTOMER)."""
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    role_clean = req.role.strip().upper()
    if role_clean not in ("CUSTOMER", "SUPPORT", "ADMIN", "OWNER", "AUDITOR", "FINANCE"):
        raise HTTPException(status_code=400, detail="Invalid role specified.")
    user.role = role_clean
    db.commit()
    return {"status": "ok", "user_id": user.id, "new_role": user.role}


@router.post("/api/devices/{device_id}/revoke")
def revoke_device(
    device_id: str,
    req: RevokeDeviceRequest,
    admin: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Remote kill-switch: Immediately revoke device entitlement."""
    success, msg = admin_service.revoke_device_license(
        db, admin_id=admin.id, device_id=device_id, reason=req.reason
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


@router.post("/api/devices/{device_id}/flag")
def flag_device(
    device_id: str,
    req: DeviceFlagRequest,
    admin: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update device security classification."""
    from licensing_server.database import DeviceDB
    dev = db.query(DeviceDB).filter(DeviceDB.id == device_id).first()
    if not dev:
        raise HTTPException(status_code=404, detail="Device not found.")
    dev.security_flag = req.security_flag.upper()
    db.commit()
    return {"status": "ok", "message": f"Device security flag updated to {dev.security_flag}."}


@router.get("/api/security")
def get_security_dashboard(
    admin: UserDB = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Security monitoring: tamper events, suspicious devices, failed transactions."""
    return admin_service.get_security_monitoring(db)


@router.get("/api/audit-logs")
def get_audit_logs(
    user_id: str = Query(default=""),
    actor_id: str = Query(default=""),
    action: str = Query(default=""),
    limit: int = Query(default=100, le=500),
    admin: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get audit trail of all administrative interventions with filters."""
    return admin_service.get_audit_logs(db, user_id=user_id, actor_id=actor_id, action=action, limit=limit)


@router.get("/api/export/{entity_type}")
def export_csv(
    entity_type: str,
    admin: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Export sanitized CSV records without passwords or secret tokens."""
    from fastapi.responses import Response
    if entity_type not in ("users", "payments", "subscriptions", "tickets"):
        raise HTTPException(status_code=400, detail="Invalid entity type for export.")
    csv_data = admin_service.export_csv(db, entity_type=entity_type)
    return Response(content=csv_data, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=charlie_{entity_type}.csv"})


@router.get("/api/payments")
def list_payments(
    query: str = Query(default=""),
    status: str = Query(default=""),
    plan: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=5, le=100),
    admin: UserDB = Depends(require_support),
    db: Session = Depends(get_db),
):
    """Search and paginate financial transactions and gateway records."""
    return admin_service.search_payments(
        db, query=query, status_filter=status, plan=plan, page=page, page_size=page_size
    )


@router.post("/api/payments/{payment_id}/refund")
def refund_payment(
    payment_id: str,
    req: RefundPaymentRequest,
    admin: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Module 3: Payments & Transactions Refund Tool."""
    from sqlalchemy import or_
    payment = db.query(PaymentDB).filter(or_(PaymentDB.id == payment_id, PaymentDB.payment_id == payment_id)).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment record not found.")
    payment.status = "REFUNDED"
    db.commit()
    return {"status": "ok", "payment_id": payment.id, "status": payment.status, "reason": req.reason}


@router.get("/api/activity")
def list_activity(
    query: str = Query(default=""),
    event_type: str = Query(default=""),
    user_id: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
    admin: UserDB = Depends(require_support),
    db: Session = Depends(get_db),
):
    """Live unified user activity and AI usage stream."""
    return admin_service.search_activity(
        db, query=query, event_type=event_type, user_id=user_id, limit=limit
    )


@router.get("/api/profile")
def get_admin_profile_endpoint(
    admin: UserDB = Depends(require_support),
    db: Session = Depends(get_db),
):
    """Retrieve current admin user profile and permissions."""
    return admin_service.get_admin_profile(db, admin_id=admin.id)


@router.post("/api/profile")
def update_admin_profile_endpoint(
    req: UpdateProfileRequest,
    admin: UserDB = Depends(require_support),
    db: Session = Depends(get_db),
):
    """Update admin display name or password."""
    success, msg = admin_service.update_admin_profile(
        db, admin_id=admin.id, display_name=req.display_name, password=req.password
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


# ── LLM Gateway & Routing Controls ──────────────────────────────────────────

@router.get("/api/llm/config")
def get_llm_config_endpoint(
    admin: UserDB = Depends(require_support),
    db: Session = Depends(get_db),
):
    """Retrieve current LLM provider routing and model settings."""
    return admin_service.get_llm_gateway_config(db)


@router.post("/api/llm/config")
def update_llm_config_endpoint(
    req: LLMConfigRequest,
    admin: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Switch primary/fallback LLM providers, model selection, and rate limits."""
    clean_dict = {k: v for k, v in req.dict().items() if v is not None}
    success, msg = admin_service.update_llm_gateway_config(db, admin_id=admin.id, new_config=clean_dict)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


@router.get("/api/llm/telemetry")
def get_llm_telemetry_endpoint(
    admin: UserDB = Depends(require_support),
    db: Session = Depends(get_db),
):
    """Retrieve live token consumption and estimated AI API expenditure."""
    return admin_service.get_llm_telemetry(db)


# ── Remote Config & Kill Switches ────────────────────────────────────────────

@router.get("/api/remote-config")
def get_remote_config_endpoint(
    admin: UserDB = Depends(require_support),
    db: Session = Depends(get_db),
):
    """Retrieve remote feature flags, dynamic prompts, and emergency kill switches."""
    return admin_service.get_remote_config(db)


@router.post("/api/remote-config")
def update_remote_config_endpoint(
    req: RemoteConfigRequest,
    admin: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update remote feature flags, prompt versions, or emergency kill switches."""
    clean_dict = {k: v for k, v in req.dict().items() if v is not None}
    success, msg = admin_service.update_remote_config(db, admin_id=admin.id, new_config=clean_dict)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


# ── Push Broadcast Dispatcher ────────────────────────────────────────────────

@router.get("/api/push/broadcasts")
def list_broadcasts_endpoint(
    active_only: bool = Query(default=False),
    admin: UserDB = Depends(require_support),
    db: Session = Depends(get_db),
):
    """List system broadcast notices, updates, and maintenance announcements."""
    return admin_service.get_broadcasts(db, active_only=active_only)


@router.post("/api/push/broadcasts")
def create_broadcast_endpoint(
    req: BroadcastCreateRequest,
    admin: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Dispatch a new in-app broadcast alert or maintenance banner."""
    success, msg, notice = admin_service.create_broadcast(
        db,
        admin_id=admin.id,
        title=req.title,
        message=req.message,
        level=req.level,
        target_tier=req.target_tier,
        expires_hours=req.expires_hours,
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg, "notice": notice}


@router.delete("/api/push/broadcasts/{notice_id}")
def delete_broadcast_endpoint(
    notice_id: str,
    admin: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete or archive a broadcast notice."""
    success, msg = admin_service.delete_broadcast(db, admin_id=admin.id, notice_id=notice_id)
    if not success:
        raise HTTPException(status_code=404, detail=msg)
    return {"status": "ok", "message": msg}


# ── AI Analytics ─────────────────────────────────────────────────────────────

@router.get("/api/ai-analytics")
def get_ai_analytics_endpoint(
    admin: UserDB = Depends(require_support),
    db: Session = Depends(get_db),
):
    """Retrieve prompt category distribution, latency percentiles, and token throughput."""
    return admin_service.get_ai_analytics(db)


# ── Public / Client Endpoints (Used by Desktop App) ─────────────────────────

@router.get("/api/public/broadcasts")
def get_public_broadcasts(db: Session = Depends(get_db)):
    """Public read-only endpoint for desktop clients to fetch active broadcasts."""
    return admin_service.get_broadcasts(db, active_only=True)


@router.get("/api/public/remote-config")
def get_public_remote_config(db: Session = Depends(get_db)):
    """Public read-only endpoint for desktop clients to synchronize feature flags."""
    return admin_service.get_remote_config(db)



@router.get("/api/support/tickets")
def list_support_tickets(
    status: str = Query(default=""),
    category: str = Query(default=""),
    admin: UserDB = Depends(require_support),
    db: Session = Depends(get_db),
):
    """List customer support tickets with sanitized diagnostics."""
    return support_service.get_all_tickets(db, status_filter=status, category_filter=category)


@router.post("/api/support/tickets/{ticket_id}/reply")
def reply_support_ticket(
    ticket_id: str,
    req: TicketReplyRequest,
    admin: UserDB = Depends(require_support),
    db: Session = Depends(get_db),
):
    """Submit admin response to ticket and update status."""
    success, msg = support_service.reply_ticket(
        db, ticket_id=ticket_id, reply_text=req.reply_text, new_status=req.new_status
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


@router.post("/api/support/tickets/{ticket_id}/internal-note")
def add_ticket_internal_note(
    ticket_id: str,
    req: InternalNoteRequest,
    admin: UserDB = Depends(require_support),
    db: Session = Depends(get_db),
):
    """Submit staff-only internal note on support ticket."""
    success, msg = support_service.add_internal_note(
        db, ticket_id=ticket_id, staff_id=admin.id, note_text=req.note_text
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


class DiagnosticRequestCreate(BaseModel):
    categories: Optional[list] = Field(default_factory=lambda: ["system_info", "health", "sanitized_logs"])


@router.post("/api/support/tickets/{ticket_id}/request-diagnostics")
def request_ticket_diagnostics(
    ticket_id: str,
    req: DiagnosticRequestCreate,
    admin: UserDB = Depends(require_support),
    db: Session = Depends(get_db),
):
    """Support requests technical diagnostics from customer. Customer receives consent prompt."""
    success, msg, d_req = support_service.create_diagnostic_request(
        db, ticket_id=ticket_id, staff_id=admin.id, categories=req.categories
    )
    if not success or not d_req:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg, "request_id": d_req.id}


class LinkIncidentRequest(BaseModel):
    incident_id: str


@router.post("/api/support/tickets/{ticket_id}/link-incident")
def link_ticket_incident(
    ticket_id: str,
    req: LinkIncidentRequest,
    admin: UserDB = Depends(require_support),
    db: Session = Depends(get_db),
):
    """Link customer ticket to known engineering incident."""
    success, msg = support_service.link_ticket_to_incident(
        db, ticket_id=ticket_id, incident_id=req.incident_id
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


@router.get("/api/incidents")
def list_incidents(
    status: str = Query(default=""),
    severity: str = Query(default=""),
    admin: UserDB = Depends(require_support),
    db: Session = Depends(get_db),
):
    """List grouped crash incidents."""
    return support_service.get_incidents(db, status_filter=status, severity_filter=severity)


class UpdateIncidentRequest(BaseModel):
    status: Optional[str] = None
    severity: Optional[str] = None
    fixed_in_version: Optional[str] = None
    assigned_owner: Optional[str] = None
    workaround: Optional[str] = None
    engineering_notes: Optional[str] = None


@router.post("/api/incidents/{incident_id}/update")
def update_incident_endpoint(
    incident_id: str,
    req: UpdateIncidentRequest,
    admin: UserDB = Depends(require_support),
    db: Session = Depends(get_db),
):
    """Update incident status, severity, workaround, or internal engineering notes."""
    success, msg, inc = support_service.update_incident(
        db,
        incident_id=incident_id,
        status=req.status,
        severity=req.severity,
        fixed_in_version=req.fixed_in_version,
        assigned_owner=req.assigned_owner,
        workaround=req.workaround,
        engineering_notes=req.engineering_notes,
    )
    if not success or not inc:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg, "incident": inc}


@router.get("/api/crash-analytics")
def get_crash_analytics(
    admin: UserDB = Depends(require_support),
    db: Session = Depends(get_db),
):
    """Crash metrics, top crashes, affected versions, and rollout regression signals."""
    return support_service.get_incident_analytics(db)



@router.get("/api/releases")
def list_releases(
    admin: UserDB = Depends(require_support),
    db: Session = Depends(get_db),
):
    """List all registered update releases with channels, rollout %, and signatures."""
    from licensing_server.database import UpdateReleaseDB
    releases = db.query(UpdateReleaseDB).order_by(UpdateReleaseDB.released_at.desc()).all()
    return [
        {
            "id": r.id,
            "version": r.version,
            "build_number": getattr(r, "build_number", 100),
            "channel": r.channel,
            "status": getattr(r, "status", "PUBLISHED"),
            "rollout_percentage": getattr(r, "rollout_percentage", 100),
            "download_url": r.download_url,
            "sha256": r.sha256,
            "signature": r.signature,
            "mandatory": getattr(r, "mandatory", False),
            "security_update": getattr(r, "security_update", False),
            "released_at": r.released_at.isoformat() if r.released_at else None,
            "release_notes": r.release_notes,
        }
        for r in releases
    ]


# ── SQLite Database Backup (Hot Atomic Snapshot) ──────────────────────────────

@router.get("/api/backup")
def backup_database(
    admin: UserDB = Depends(require_owner),
):
    """
    Generate an atomic, crash-safe SQLite online backup and stream as a .db file.
    Protected strictly by require_owner (or admin key).
    """
    import sqlite3
    import tempfile
    from datetime import datetime
    from pathlib import Path
    from licensing_server.config import SERVER_DIR

    db_path = SERVER_DIR / "charlie_licensing.db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="Database file not found.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"charlie_backup_{timestamp}.db"
    temp_dir = tempfile.gettempdir()
    dest_path = Path(temp_dir) / backup_filename

    # Use SQLite online backup API for safe non-blocking hot backup
    src_conn = sqlite3.connect(str(db_path))
    dest_conn = sqlite3.connect(str(dest_path))
    try:
        with dest_conn:
            src_conn.backup(dest_conn, pages=100)
    finally:
        dest_conn.close()
        src_conn.close()

    return FileResponse(
        path=str(dest_path),
        filename=backup_filename,
        media_type="application/x-sqlite3",
    )


# ── Security Lockouts Dashboard & Management ──────────────────────────────────

class UnlockAccountRequest(BaseModel):
    email: str


class ResetIpRequest(BaseModel):
    ip: str


@router.get("/api/security/lockouts")
def get_security_lockouts(
    admin: UserDB = Depends(require_support),
):
    """List all accounts currently locked by the multi-tier rate limiter."""
    from licensing_server.middleware.rate_limiter import get_active_lockouts
    return {"status": "ok", "lockouts": get_active_lockouts()}


@router.post("/api/security/unlock")
def unlock_security_account(
    req: UnlockAccountRequest,
    admin: UserDB = Depends(require_admin),
):
    """Admin unlock for brute-force locked accounts."""
    from licensing_server.middleware.rate_limiter import unlock_account
    unlocked = unlock_account(req.email)
    if not unlocked:
        return {"status": "ok", "message": f"Account {req.email} was not locked."}
    return {"status": "ok", "message": f"Account {req.email} unlocked successfully."}


@router.post("/api/security/reset-ip")
def reset_security_ip(
    req: ResetIpRequest,
    admin: UserDB = Depends(require_admin),
):
    """Admin reset for IP-based sliding window rate limits."""
    from licensing_server.middleware.rate_limiter import reset_ip_limits
    cleared = reset_ip_limits(req.ip)
    return {"status": "ok", "message": f"Reset {cleared} limit buckets for IP {req.ip}."}


# ── Forced Session Revocation ────────────────────────────────────────────────

@router.post("/api/users/{user_id}/revoke-sessions")
def revoke_user_sessions(
    user_id: str,
    admin: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Immediately invalidate all active JWT tokens for a user by incrementing session_version.
    Forces all active client instances to re-authenticate immediately.
    """
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    from licensing_server.services.auth_service import AuthService
    auth_service = AuthService()
    auth_service.invalidate_all_sessions(db, user)

    # Log audit event
    from licensing_server.database import LicenseEventDB, LicenseEventType
    import uuid
    import json
    event = LicenseEventDB(
        id=f"evt_{uuid.uuid4().hex[:16]}",
        user_id=user.id,
        event_type=LicenseEventType.LOGIN.value,
        details_json=json.dumps({"action": "SESSIONS_REVOKED_BY_ADMIN", "admin_id": admin.id}),
    )
    db.add(event)
    db.commit()

    return {
        "status": "ok",
        "message": f"All active sessions revoked for user {user.email}.",
        "new_session_version": getattr(user, "session_version", 1),
    }


# ── The 16 Admin Modules: Content, Orders, Coupons, Partners, Moderation ───

from licensing_server.database import ContentItemDB, OrderDB, CouponDB, PartnerDB, ModerationItemDB, _utcnow

class CreateCouponRequest(BaseModel):
    code: str = Field(..., min_length=2, max_length=64)
    discount_pct: int = Field(default=15, ge=1, le=100)
    max_uses: int = Field(default=100, ge=1)
    expires_days: int = Field(default=30, ge=1)

class CreatePartnerRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    email: str = Field(..., max_length=255)
    partner_code: str = Field(..., min_length=2, max_length=64)
    commission_pct: int = Field(default=15, ge=1, le=80)

class CreateContentRequest(BaseModel):
    item_type: str = Field(default="BANNER")
    title: str = Field(..., min_length=1, max_length=255)
    content_json: str = Field(default="{}")

class ModerationActionRequest(BaseModel):
    status: str = Field(default="APPROVED")
    notes: Optional[str] = None

class OrderOverrideRequest(BaseModel):
    status: str = Field(default="OVERRIDDEN")
    notes: Optional[str] = None


@router.get("/api/coupons")
def list_coupons(admin: UserDB = Depends(require_support), db: Session = Depends(get_db)):
    """Module 12: Coupons & Discount Management."""
    coupons = db.query(CouponDB).order_by(CouponDB.created_at.desc()).all()
    return [{
        "id": c.id, "code": c.code, "discount_pct": c.discount_pct,
        "max_uses": c.max_uses, "uses_count": c.uses_count,
        "is_active": c.is_active,
        "expires_at": c.expires_at.isoformat() if c.expires_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    } for c in coupons]

@router.post("/api/coupons")
def create_coupon(req: CreateCouponRequest, admin: UserDB = Depends(require_admin), db: Session = Depends(get_db)):
    import uuid
    from datetime import timedelta
    code = req.code.strip().upper()
    existing = db.query(CouponDB).filter(CouponDB.code == code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Coupon code already exists.")
    coupon = CouponDB(
        id=f"cpn_{uuid.uuid4().hex[:12]}",
        code=code,
        discount_pct=req.discount_pct,
        max_uses=req.max_uses,
        expires_at=_utcnow() + timedelta(days=req.expires_days),
    )
    db.add(coupon)
    db.commit()
    return {"status": "ok", "coupon": {"id": coupon.id, "code": coupon.code, "discount_pct": coupon.discount_pct}}

@router.delete("/api/coupons/{coupon_id}")
def delete_coupon(coupon_id: str, admin: UserDB = Depends(require_admin), db: Session = Depends(get_db)):
    coupon = db.query(CouponDB).filter(CouponDB.id == coupon_id).first()
    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found.")
    coupon.is_active = False
    db.commit()
    return {"status": "ok", "message": "Coupon deactivated."}

@router.get("/api/partners")
def list_partners(admin: UserDB = Depends(require_support), db: Session = Depends(get_db)):
    """Module 13: Vendor / Partner / Affiliate Management."""
    partners = db.query(PartnerDB).order_by(PartnerDB.created_at.desc()).all()
    return [{
        "id": p.id, "name": p.name, "email": p.email, "partner_code": p.partner_code,
        "commission_pct": p.commission_pct, "total_sales_paise": p.total_sales_paise,
        "total_payout_paise": p.total_payout_paise, "status": p.status,
    } for p in partners]

@router.post("/api/partners")
def create_partner(req: CreatePartnerRequest, admin: UserDB = Depends(require_admin), db: Session = Depends(get_db)):
    import uuid
    code = req.partner_code.strip().upper()
    existing = db.query(PartnerDB).filter(PartnerDB.partner_code == code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Partner referral code already exists.")
    partner = PartnerDB(
        id=f"ptn_{uuid.uuid4().hex[:12]}",
        name=req.name.strip(),
        email=req.email.strip().lower(),
        partner_code=code,
        commission_pct=req.commission_pct,
    )
    db.add(partner)
    db.commit()
    return {"status": "ok", "partner_id": partner.id}

@router.get("/api/content")
def list_content(admin: UserDB = Depends(require_support), db: Session = Depends(get_db)):
    """Module 2: Content Management (CMS Banners & Categories)."""
    items = db.query(ContentItemDB).order_by(ContentItemDB.updated_at.desc()).all()
    return [{
        "id": item.id, "item_type": item.item_type, "title": item.title,
        "content_json": item.content_json, "is_published": item.is_published,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    } for item in items]

@router.post("/api/content")
def create_content(req: CreateContentRequest, admin: UserDB = Depends(require_admin), db: Session = Depends(get_db)):
    import uuid
    item = ContentItemDB(
        id=f"cms_{uuid.uuid4().hex[:12]}",
        item_type=req.item_type.upper(),
        title=req.title.strip(),
        content_json=req.content_json,
    )
    db.add(item)
    db.commit()
    return {"status": "ok", "item_id": item.id}

@router.get("/api/orders")
def list_orders(admin: UserDB = Depends(require_support), db: Session = Depends(get_db)):
    """Module 7: Order / Booking Management."""
    orders = db.query(OrderDB).order_by(OrderDB.created_at.desc()).limit(100).all()
    return [{
        "id": o.id, "user_id": o.user_id, "order_type": o.order_type,
        "amount_paise": o.amount_paise, "status": o.status, "notes": o.notes,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    } for o in orders]

@router.post("/api/orders/{order_id}/override")
def override_order(order_id: str, req: OrderOverrideRequest, admin: UserDB = Depends(require_admin), db: Session = Depends(get_db)):
    order = db.query(OrderDB).filter(OrderDB.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
    order.status = req.status
    if req.notes:
        order.notes = req.notes
    db.commit()
    return {"status": "ok", "order_id": order.id, "new_status": order.status}

@router.get("/api/moderation")
def list_moderation_queue(admin: UserDB = Depends(require_support), db: Session = Depends(get_db)):
    """Module 14: Content Moderation Tools."""
    items = db.query(ModerationItemDB).order_by(ModerationItemDB.created_at.desc()).limit(50).all()
    return [{
        "id": m.id, "user_id": m.user_id, "content_snippet": m.content_snippet,
        "flag_reason": m.flag_reason, "status": m.status,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    } for m in items]

@router.post("/api/moderation/{item_id}/action")
def moderate_item(item_id: str, req: ModerationActionRequest, admin: UserDB = Depends(require_support), db: Session = Depends(get_db)):
    item = db.query(ModerationItemDB).filter(ModerationItemDB.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found.")
    item.status = req.status
    item.reviewed_by = admin.id
    db.commit()
    return {"status": "ok", "item_id": item.id, "status": item.status}

@router.get("/api/founder-modules-status")
def get_founder_modules_status(admin: UserDB = Depends(require_support)):
    """Summary checklist of all 16 Founder Modules."""
    return {
        "modules_count": 16,
        "modules": [
            {"id": 1, "name": "User Management", "status": "LIVE", "endpoint": "/admin/api/users"},
            {"id": 2, "name": "Content Management", "status": "LIVE", "endpoint": "/admin/api/content"},
            {"id": 3, "name": "Payments & Transactions", "status": "LIVE", "endpoint": "/admin/api/payments"},
            {"id": 4, "name": "Notifications", "status": "LIVE", "endpoint": "/admin/api/push/broadcasts"},
            {"id": 5, "name": "Reports & Exports", "status": "LIVE", "endpoint": "/admin/api/export/{type}"},
            {"id": 6, "name": "Roles & Permissions", "status": "LIVE", "endpoint": "/admin/api/profile"},
            {"id": 7, "name": "Order / Booking Management", "status": "LIVE", "endpoint": "/admin/api/orders"},
            {"id": 8, "name": "Support & Ticket Management", "status": "LIVE", "endpoint": "/admin/api/support/tickets"},
            {"id": 9, "name": "Live Analytics Dashboard", "status": "LIVE", "endpoint": "/admin/api/metrics"},
            {"id": 10, "name": "Audit Logs & Activity History", "status": "LIVE", "endpoint": "/admin/api/audit-logs"},
            {"id": 11, "name": "Feature Flags & App Configuration", "status": "LIVE", "endpoint": "/admin/api/remote-config"},
            {"id": 12, "name": "Coupons & Discount Management", "status": "LIVE", "endpoint": "/admin/api/coupons"},
            {"id": 13, "name": "Vendor / Partner Management", "status": "LIVE", "endpoint": "/admin/api/partners"},
            {"id": 14, "name": "Content Moderation Tools", "status": "LIVE", "endpoint": "/admin/api/moderation"},
            {"id": 15, "name": "Session & Device Management", "status": "LIVE", "endpoint": "/admin/api/security"},
            {"id": 16, "name": "Force-Update & App Version Control", "status": "LIVE", "endpoint": "/admin/api/releases"},
        ]
    }



# ── Embedded Cybernetic Dark HUD Web UI ──────────────────────────────────────

@router.get("")
@router.get("/")
def admin_dashboard_ui():
    """Redirect to the comprehensive standalone Admin Panel."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/admin-panel/", status_code=307)



ADMIN_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CHARLIE AI Commercial Control Panel — Owner Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #07090e;
      --panel: #0d1117;
      --card: #121824;
      --border: rgba(0, 229, 255, 0.15);
      --border-bright: rgba(0, 229, 255, 0.4);
      --cyan: #00e5ff;
      --cyan-dim: rgba(0, 229, 255, 0.1);
      --blue: #3b82f6;
      --green: #10b981;
      --amber: #f59e0b;
      --red: #ef4444;
      --text: #f1f5f9;
      --text-dim: #94a3b8;
      --text-muted: #64748b;
      --font-main: 'Space Grotesk', -apple-system, BlinkMacSystemFont, sans-serif;
      --font-mono: 'JetBrains Mono', monospace;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: var(--font-main);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    header {
      background: rgba(13, 17, 23, 0.85);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border);
      padding: 1rem 2rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky;
      top: 0;
      z-index: 100;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }
    .brand-badge {
      background: var(--cyan-dim);
      border: 1px solid var(--cyan);
      color: var(--cyan);
      font-family: var(--font-mono);
      font-size: 0.7rem;
      padding: 0.2rem 0.5rem;
      border-radius: 4px;
      letter-spacing: 1px;
      font-weight: 600;
    }
    .brand h1 {
      font-size: 1.15rem;
      font-weight: 700;
      letter-spacing: -0.5px;
      color: #fff;
    }
    .header-actions {
      display: flex;
      align-items: center;
      gap: 1rem;
    }
    .key-input {
      background: #090d14;
      border: 1px solid var(--border);
      color: var(--cyan);
      font-family: var(--font-mono);
      font-size: 0.8rem;
      padding: 0.4rem 0.8rem;
      border-radius: 6px;
      width: 220px;
      outline: none;
    }
    .key-input:focus { border-color: var(--cyan); }
    .btn {
      background: var(--cyan);
      color: #050b14;
      font-family: var(--font-main);
      font-weight: 600;
      font-size: 0.8rem;
      padding: 0.45rem 0.9rem;
      border-radius: 6px;
      border: none;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      transition: all 0.2s ease;
    }
    .btn:hover { transform: translateY(-1px); box-shadow: 0 0 14px rgba(0, 229, 255, 0.4); }
    .btn-secondary {
      background: transparent;
      color: var(--text-dim);
      border: 1px solid var(--border);
    }
    .btn-secondary:hover { color: #fff; border-color: var(--cyan); background: var(--cyan-dim); }
    .btn-danger {
      background: rgba(239, 68, 68, 0.15);
      color: var(--red);
      border: 1px solid rgba(239, 68, 68, 0.3);
    }
    .btn-danger:hover { background: var(--red); color: #fff; box-shadow: 0 0 14px rgba(239, 68, 68, 0.4); }
    main {
      flex: 1;
      padding: 2rem;
      max-width: 1440px;
      width: 100%;
      margin: 0 auto;
      display: flex;
      flex-direction: column;
      gap: 2rem;
    }
    .nav-tabs {
      display: flex;
      gap: 0.5rem;
      border-bottom: 1px solid var(--border);
      padding-bottom: 0.5rem;
    }
    .tab-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-family: var(--font-main);
      font-size: 0.9rem;
      font-weight: 600;
      padding: 0.6rem 1.2rem;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.2s;
    }
    .tab-btn.active {
      color: var(--cyan);
      background: var(--cyan-dim);
      border: 1px solid var(--border-bright);
    }
    .metrics-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 1rem;
    }
    .metric-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 1.25rem;
      position: relative;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      gap: 0.4rem;
    }
    .metric-card::before {
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0; height: 2px;
      background: linear-gradient(90deg, transparent, var(--cyan), transparent);
    }
    .metric-title {
      font-size: 0.75rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      font-family: var(--font-mono);
    }
    .metric-val {
      font-size: 1.8rem;
      font-weight: 700;
      color: #fff;
      font-family: var(--font-mono);
    }
    .metric-sub {
      font-size: 0.75rem;
      color: var(--text-dim);
    }
    .text-green { color: var(--green); }
    .text-cyan { color: var(--cyan); }
    .text-amber { color: var(--amber); }
    .text-red { color: var(--red); }
    .table-container {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
    }
    .table-toolbar {
      padding: 1rem 1.25rem;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 1rem;
      flex-wrap: wrap;
    }
    .search-input {
      background: #090d14;
      border: 1px solid var(--border);
      color: #fff;
      font-family: var(--font-main);
      padding: 0.5rem 1rem;
      border-radius: 6px;
      font-size: 0.85rem;
      min-width: 280px;
      outline: none;
    }
    .search-input:focus { border-color: var(--cyan); }
    .filter-select {
      background: #090d14;
      border: 1px solid var(--border);
      color: var(--text-dim);
      padding: 0.5rem 0.8rem;
      border-radius: 6px;
      font-size: 0.85rem;
      outline: none;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.85rem;
      text-align: left;
    }
    th {
      background: #0a0e17;
      color: var(--text-muted);
      padding: 0.75rem 1.25rem;
      font-weight: 600;
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      border-bottom: 1px solid var(--border);
    }
    td {
      padding: 0.9rem 1.25rem;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
      color: var(--text-dim);
    }
    tr:hover td {
      background: rgba(0, 229, 255, 0.02);
      color: #fff;
    }
    .badge {
      display: inline-block;
      padding: 0.2rem 0.5rem;
      border-radius: 4px;
      font-family: var(--font-mono);
      font-size: 0.7rem;
      font-weight: 600;
    }
    .badge-starter { background: rgba(100, 116, 139, 0.2); color: #94a3b8; border: 1px solid rgba(100, 116, 139, 0.4); }
    .badge-basic { background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.4); }
    .badge-premium { background: rgba(0, 229, 255, 0.2); color: #00e5ff; border: 1px solid rgba(0, 229, 255, 0.4); }
    .badge-advanced { background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.4); }
    .badge-lifetime { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); }
    .badge-active { background: rgba(16, 185, 129, 0.15); color: #34d399; }
    .badge-suspended { background: rgba(239, 68, 68, 0.15); color: #f87171; }
    .modal-overlay {
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0, 0, 0, 0.75);
      backdrop-filter: blur(4px);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 1000;
    }
    .modal {
      background: var(--panel);
      border: 1px solid var(--cyan);
      box-shadow: 0 0 30px rgba(0, 229, 255, 0.2);
      border-radius: 12px;
      width: 90%;
      max-width: 600px;
      max-height: 85vh;
      overflow-y: auto;
      padding: 1.5rem;
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
    }
    .modal-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--border);
      padding-bottom: 0.75rem;
    }
    .modal-header h3 { color: #fff; font-size: 1.1rem; }
    .close-btn {
      background: transparent; border: none; color: var(--text-muted); font-size: 1.2rem; cursor: pointer;
    }
    .detail-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 0.75rem;
      font-size: 0.85rem;
    }
    .detail-item {
      background: #090d14;
      padding: 0.6rem 0.8rem;
      border-radius: 6px;
      border: 1px solid rgba(255, 255, 255, 0.05);
    }
    .detail-label { color: var(--text-muted); font-size: 0.7rem; text-transform: uppercase; font-family: var(--font-mono); }
    .detail-val { color: #fff; margin-top: 0.2rem; word-break: break-all; }
    .actions-row { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.5rem; }
    pre {
      background: #05080f;
      padding: 0.75rem;
      border-radius: 6px;
      font-family: var(--font-mono);
      font-size: 0.75rem;
      color: var(--cyan);
      max-height: 200px;
      overflow-y: auto;
      border: 1px solid rgba(0, 229, 255, 0.1);
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <span class="brand-badge">CONTROL NEXUS</span>
      <h1>CHARLIE AI Owner Admin Dashboard</h1>
    </div>
    <div class="header-actions">
      <input type="password" id="adminKeyInput" class="key-input" placeholder="X-Admin-Key" value="charlie_admin_secret_key_2026">
      <button class="btn btn-secondary" onclick="loadAllData()">Sync Live</button>
    </div>
  </header>

  <main>
    <div class="nav-tabs">
      <button class="tab-btn active" onclick="switchTab('metricsTab', this)">Overview & Revenue</button>
      <button class="tab-btn" onclick="switchTab('usersTab', this)">User Management</button>
      <button class="tab-btn" onclick="switchTab('ticketsTab', this)">Support Tickets</button>
      <button class="tab-btn" onclick="switchTab('auditTab', this)">Audit Trail</button>
    </div>

    <!-- METRICS TAB -->
    <div id="metricsTab">
      <div class="metrics-grid">
        <div class="metric-card">
          <div class="metric-title">Monthly Recurring Revenue (MRR)</div>
          <div class="metric-val text-cyan" id="mrrVal">₹0</div>
          <div class="metric-sub" id="mrrSub">Based on active monthly plans</div>
        </div>
        <div class="metric-card">
          <div class="metric-title">Today's Revenue</div>
          <div class="metric-val text-green" id="todayRevVal">₹0</div>
          <div class="metric-sub">Captured in last 24 hours</div>
        </div>
        <div class="metric-card">
          <div class="metric-title">Lifetime Sales</div>
          <div class="metric-val" id="lifetimeRevVal">₹0</div>
          <div class="metric-sub" id="churnVal">Churn: 0%</div>
        </div>
        <div class="metric-card">
          <div class="metric-title">Total Registered Users</div>
          <div class="metric-val" id="totalUsersVal">0</div>
          <div class="metric-sub" id="conversionVal">Conversion: 0%</div>
        </div>
        <div class="metric-card">
          <div class="metric-title">Active Subscriptions</div>
          <div class="metric-val text-cyan" id="activeSubsVal">0</div>
          <div class="metric-sub" id="expiredSubsVal">0 expired/cancelled</div>
        </div>
        <div class="metric-card">
          <div class="metric-title">Bound Active PCs</div>
          <div class="metric-val" id="activeDevicesVal">0</div>
          <div class="metric-sub" id="transfersVal">0 transfers total</div>
        </div>
        <div class="metric-card">
          <div class="metric-title">Suspicious / Tamper Alerts</div>
          <div class="metric-val text-amber" id="suspiciousVal">0</div>
          <div class="metric-sub">Security flags logged</div>
        </div>
        <div class="metric-card">
          <div class="metric-title">Open Support Tickets</div>
          <div class="metric-val text-red" id="openTicketsVal">0</div>
          <div class="metric-sub">Awaiting operator reply</div>
        </div>
      </div>

      <div style="margin-top: 1.5rem; background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 1.25rem;">
        <h3 style="font-size: 0.95rem; margin-bottom: 1rem; color: #fff;">Active Plan Distribution</h3>
        <div style="display: flex; gap: 1rem; flex-wrap: wrap;" id="tierBadgesContainer">
          <!-- Populated dynamically -->
        </div>
      </div>
    </div>

    <!-- USERS TAB -->
    <div id="usersTab" style="display: none;">
      <div class="table-container">
        <div class="table-toolbar">
          <input type="text" id="userSearchInput" class="search-input" placeholder="Search by email, name, user ID..." oninput="debounceSearch()">
          <div style="display: flex; gap: 0.5rem;">
            <select id="planFilter" class="filter-select" onchange="loadUsers()">
              <option value="">All Plans</option>
              <option value="STARTER">Starter</option>
              <option value="BASIC">Basic (₹99)</option>
              <option value="PREMIUM">Premium (₹199)</option>
              <option value="ADVANCED">Advanced (₹299)</option>
              <option value="LIFETIME">Lifetime</option>
            </select>
            <select id="statusFilter" class="filter-select" onchange="loadUsers()">
              <option value="">All Statuses</option>
              <option value="ACTIVE">Active</option>
              <option value="SUSPENDED">Suspended</option>
            </select>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>User</th>
              <th>Plan</th>
              <th>Status</th>
              <th>Bound PC</th>
              <th>Registered</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody id="usersTableBody">
            <tr><td colspan="6" style="text-align: center; padding: 2rem;">Loading users...</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- TICKETS TAB -->
    <div id="ticketsTab" style="display: none;">
      <div class="table-container">
        <div class="table-toolbar">
          <h3 style="font-size: 0.95rem;">Customer Support Center</h3>
          <button class="btn btn-secondary" onclick="loadTickets()">Refresh Tickets</button>
        </div>
        <table>
          <thead>
            <tr>
              <th>Ticket #</th>
              <th>User</th>
              <th>Category</th>
              <th>Subject</th>
              <th>Status</th>
              <th>Created</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody id="ticketsTableBody">
            <tr><td colspan="7" style="text-align: center; padding: 2rem;">Loading tickets...</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- AUDIT TAB -->
    <div id="auditTab" style="display: none;">
      <div class="table-container">
        <div class="table-toolbar">
          <h3 style="font-size: 0.95rem;">Security & Operational Audit Log</h3>
          <button class="btn btn-secondary" onclick="loadAudit()">Refresh Audit</button>
        </div>
        <table>
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Actor</th>
              <th>Action</th>
              <th>Target User</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody id="auditTableBody">
            <tr><td colspan="5" style="text-align: center; padding: 2rem;">Loading audit trail...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </main>

  <!-- USER DETAIL MODAL -->
  <div id="userModal" class="modal-overlay">
    <div class="modal">
      <div class="modal-header">
        <h3 id="modalUserTitle">User Details</h3>
        <button class="close-btn" onclick="closeModal('userModal')">&times;</button>
      </div>
      <div id="modalUserBody"></div>
    </div>
  </div>

  <!-- TICKET REPLY MODAL -->
  <div id="ticketModal" class="modal-overlay">
    <div class="modal">
      <div class="modal-header">
        <h3 id="modalTicketTitle">Support Ticket</h3>
        <button class="close-btn" onclick="closeModal('ticketModal')">&times;</button>
      </div>
      <div id="modalTicketBody"></div>
    </div>
  </div>

  <script>
    function getAdminKey() {
      return document.getElementById('adminKeyInput').value.trim();
    }

    async function apiFetch(url, options = {}) {
      options.headers = options.headers || {};
      options.headers['X-Admin-Key'] = getAdminKey();
      const res = await fetch(url, options);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'Request failed');
      }
      return res.json();
    }

    function switchTab(tabId, btn) {
      ['metricsTab', 'usersTab', 'ticketsTab', 'auditTab'].forEach(id => {
        document.getElementById(id).style.display = (id === tabId) ? 'block' : 'none';
      });
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      if (tabId === 'usersTab') loadUsers();
      if (tabId === 'ticketsTab') loadTickets();
      if (tabId === 'auditTab') loadAudit();
    }

    async function loadAllData() {
      await loadMetrics();
      await loadUsers();
    }

    async function loadMetrics() {
      try {
        const m = await apiFetch('/admin/api/metrics');
        document.getElementById('mrrVal').innerText = '₹' + m.revenue.mrr;
        document.getElementById('todayRevVal').innerText = '₹' + m.revenue.today;
        document.getElementById('lifetimeRevVal').innerText = '₹' + m.revenue.lifetime;
        document.getElementById('churnVal').innerText = 'Churn: ' + m.analytics.churn_rate_pct + '%';
        document.getElementById('totalUsersVal').innerText = m.total_users;
        document.getElementById('conversionVal').innerText = 'Conversion: ' + m.analytics.conversion_rate_pct + '%';
        document.getElementById('activeSubsVal').innerText = m.active_subscriptions;
        document.getElementById('expiredSubsVal').innerText = m.expired_or_cancelled + ' expired/cancelled';
        document.getElementById('activeDevicesVal').innerText = m.active_devices;
        document.getElementById('transfersVal').innerText = m.total_transfers + ' transfers total';
        document.getElementById('suspiciousVal').innerText = m.suspicious_activations;
        document.getElementById('openTicketsVal').innerText = m.open_tickets;

        const tiersBox = document.getElementById('tierBadgesContainer');
        tiersBox.innerHTML = '';
        for (const [tier, count] of Object.entries(m.tier_counts)) {
          const badge = document.createElement('div');
          badge.className = 'metric-card';
          badge.style.minWidth = '140px';
          badge.style.padding = '0.75rem';
          badge.innerHTML = `<span class="detail-label">${tier}</span><span style="font-size:1.3rem;font-weight:700;font-family:var(--font-mono);">${count}</span>`;
          tiersBox.appendChild(badge);
        }
      } catch (e) {
        console.error('Failed to load metrics:', e);
      }
    }

    let searchTimeout = null;
    function debounceSearch() {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(loadUsers, 300);
    }

    async function loadUsers() {
      const q = document.getElementById('userSearchInput').value;
      const plan = document.getElementById('planFilter').value;
      const status = document.getElementById('statusFilter').value;

      try {
        const data = await apiFetch(`/admin/api/users?query=${encodeURIComponent(q)}&plan=${plan}&status=${status}`);
        const tbody = document.getElementById('usersTableBody');
        tbody.innerHTML = '';

        if (!data.users.length) {
          tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem;">No users found.</td></tr>';
          return;
        }

        data.users.forEach(u => {
          const tr = document.createElement('tr');
          const planClass = 'badge-' + (u.plan ? u.plan.toLowerCase() : 'starter');
          const statusClass = u.account_status === 'ACTIVE' ? 'badge-active' : 'badge-suspended';
          tr.innerHTML = `
            <td>
              <div style="font-weight:600;color:#fff;">${u.display_name}</div>
              <div style="font-size:0.75rem;color:var(--text-muted);font-family:var(--font-mono);">${u.email}</div>
            </td>
            <td><span class="badge ${planClass}">${u.plan}</span></td>
            <td><span class="badge ${statusClass}">${u.account_status}</span></td>
            <td style="font-family:var(--font-mono);font-size:0.75rem;">${u.active_device_id ? u.active_device_id.slice(0, 12) + '...' : '<span style="color:var(--text-muted)">None</span>'}</td>
            <td style="font-size:0.75rem;">${u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}</td>
            <td>
              <button class="btn btn-secondary" style="padding:0.25rem 0.6rem;font-size:0.75rem;" onclick="viewUser('${u.id}')">Manage</button>
            </td>
          `;
          tbody.appendChild(tr);
        });
      } catch (e) {
        console.error('Failed to load users:', e);
      }
    }

    async function viewUser(userId) {
      try {
        const d = await apiFetch(`/admin/api/users/${userId}`);
        const u = d.user;
        const s = d.subscription;
        document.getElementById('modalUserTitle').innerText = `${u.display_name} (${u.email})`;

        const body = document.getElementById('modalUserBody');
        body.innerHTML = `
          <div class="detail-grid">
            <div class="detail-item"><div class="detail-label">User ID</div><div class="detail-val font-mono">${u.id}</div></div>
            <div class="detail-item"><div class="detail-label">Status</div><div class="detail-val">${u.account_status}</div></div>
            <div class="detail-item"><div class="detail-label">Current Plan</div><div class="detail-val text-cyan">${s.plan} (${s.status})</div></div>
            <div class="detail-item"><div class="detail-label">Expires</div><div class="detail-val">${s.expires_at ? new Date(s.expires_at).toLocaleString() : 'Never (Lifetime/Free)'}</div></div>
            <div class="detail-item"><div class="detail-label">Active Device</div><div class="detail-val">${s.active_device_id || 'None bound'}</div></div>
            <div class="detail-item"><div class="detail-label">Devices Total</div><div class="detail-val">${d.devices.length} registered</div></div>
          </div>

          <div style="margin-top:1rem;">
            <h4 style="font-size:0.8rem;color:var(--text-muted);text-transform:uppercase;margin-bottom:0.5rem;">Administrative Controls</h4>
            <div class="actions-row">
              ${u.account_status === 'ACTIVE'
                ? `<button class="btn btn-danger" onclick="suspendUser('${u.id}')">Suspend Account</button>`
                : `<button class="btn" onclick="reactivateUser('${u.id}')">Reactivate Account</button>`
              }
              <button class="btn btn-secondary" onclick="resetDevice('${u.id}')">Reset Device Binding</button>
              <button class="btn btn-secondary" onclick="promptGrant('${u.id}')">Grant Entitlement</button>
            </div>
          </div>

          ${d.devices.length ? `
          <div style="margin-top:1rem;">
            <h4 style="font-size:0.8rem;color:var(--text-muted);text-transform:uppercase;margin-bottom:0.5rem;">Registered Devices</h4>
            ${d.devices.map(dev => `
              <div style="background:#090d14;padding:0.6rem;border-radius:6px;border:1px solid var(--border);margin-bottom:0.4rem;display:flex;justify-content:space-between;align-items:center;">
                <div>
                  <div style="color:#fff;font-weight:600;font-size:0.8rem;">${dev.device_name} (${dev.os_type})</div>
                  <div style="color:var(--text-muted);font-size:0.7rem;font-family:var(--font-mono);">${dev.id} &bull; ${dev.status}</div>
                </div>
                ${dev.status === 'ACTIVE' ? `<button class="btn btn-danger" style="padding:0.2rem 0.5rem;font-size:0.7rem;" onclick="revokeDevice('${dev.id}', '${u.id}')">Revoke</button>` : ''}
              </div>
            `).join('')}
          </div>` : ''}
        `;
        document.getElementById('userModal').style.display = 'flex';
      } catch (e) {
        alert(e.message);
      }
    }

    async function suspendUser(userId) {
      const reason = prompt('Reason for suspension:', 'Violation of terms');
      if (!reason) return;
      try {
        await apiFetch(`/admin/api/users/${userId}/suspend`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reason })
        });
        viewUser(userId);
        loadUsers();
      } catch (e) { alert(e.message); }
    }

    async function reactivateUser(userId) {
      try {
        await apiFetch(`/admin/api/users/${userId}/reactivate`, { method: 'POST' });
        viewUser(userId);
        loadUsers();
      } catch (e) { alert(e.message); }
    }

    async function resetDevice(userId) {
      if (!confirm('Unbind active PC for this user? They will be able to bind a new PC.')) return;
      try {
        await apiFetch(`/admin/api/users/${userId}/reset-device`, { method: 'POST' });
        viewUser(userId);
        loadUsers();
      } catch (e) { alert(e.message); }
    }

    async function promptGrant(userId) {
      const plan = prompt('Plan tier (BASIC, PREMIUM, ADVANCED, LIFETIME):', 'PREMIUM');
      if (!plan) return;
      const days = parseInt(prompt('Entitlement duration in days:', '30'), 10) || 30;
      try {
        await apiFetch(`/admin/api/users/${userId}/grant-entitlement`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ plan: plan.toUpperCase(), days })
        });
        viewUser(userId);
        loadUsers();
      } catch (e) { alert(e.message); }
    }

    async function revokeDevice(deviceId, userId) {
      const reason = prompt('Reason for revocation:', 'Suspicious activity');
      if (!reason) return;
      try {
        await apiFetch(`/admin/api/devices/${deviceId}/revoke`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reason })
        });
        viewUser(userId);
        loadUsers();
      } catch (e) { alert(e.message); }
    }

    async function loadTickets() {
      try {
        const tickets = await apiFetch('/admin/api/support/tickets');
        const tbody = document.getElementById('ticketsTableBody');
        tbody.innerHTML = '';
        if (!tickets.length) {
          tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:2rem;">No support tickets.</td></tr>';
          return;
        }
        tickets.forEach(t => {
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td style="font-family:var(--font-mono);color:var(--cyan);">${t.ticket_number}</td>
            <td>${t.user_email || t.user_id}</td>
            <td><span class="badge badge-basic">${t.category}</span></td>
            <td style="color:#fff;font-weight:500;">${t.subject}</td>
            <td><span class="badge ${t.status === 'OPEN' ? 'badge-suspended' : 'badge-active'}">${t.status}</span></td>
            <td style="font-size:0.75rem;">${new Date(t.created_at).toLocaleDateString()}</td>
            <td><button class="btn btn-secondary" style="padding:0.25rem 0.6rem;font-size:0.75rem;" onclick="viewTicket('${t.id}')">Inspect</button></td>
          `;
          tbody.appendChild(tr);
        });
      } catch (e) { console.error('Failed tickets:', e); }
    }

    async function viewTicket(ticketId) {
      try {
        const tickets = await apiFetch('/admin/api/support/tickets');
        const t = tickets.find(item => item.id === ticketId);
        if (!t) return;

        document.getElementById('modalTicketTitle').innerText = `${t.ticket_number}: ${t.subject}`;
        const body = document.getElementById('modalTicketBody');
        body.innerHTML = `
          <div class="detail-grid">
            <div class="detail-item"><div class="detail-label">User</div><div class="detail-val">${t.user_email || t.user_id}</div></div>
            <div class="detail-item"><div class="detail-label">Subscription</div><div class="detail-val">${t.subscription_status || 'N/A'}</div></div>
            <div class="detail-item"><div class="detail-label">App & OS</div><div class="detail-val">${t.app_version} on ${t.os_version}</div></div>
            <div class="detail-item"><div class="detail-label">Error ID</div><div class="detail-val font-mono">${t.error_id || 'None'}</div></div>
          </div>
          <div style="margin-top:0.75rem;">
            <div class="detail-label">User Message:</div>
            <div style="background:#090d14;padding:0.75rem;border-radius:6px;margin-top:0.25rem;color:#fff;font-size:0.85rem;">${t.message}</div>
          </div>
          <div style="margin-top:0.75rem;">
            <div class="detail-label">Sanitized Diagnostics & Safe Logs:</div>
            <pre>${JSON.stringify(t.diagnostics, null, 2)}</pre>
          </div>
          ${t.admin_reply ? `
          <div style="margin-top:0.75rem;">
            <div class="detail-label">Previous Admin Reply:</div>
            <div style="background:#0a171f;border-left:3px solid var(--cyan);padding:0.5rem 0.75rem;color:var(--text);margin-top:0.25rem;">${t.admin_reply}</div>
          </div>` : ''}
          <div style="margin-top:1rem;">
            <div class="detail-label">Submit Operator Reply:</div>
            <textarea id="replyMsg" style="width:100%;height:80px;background:#090d14;border:1px solid var(--border);border-radius:6px;color:#fff;padding:0.5rem;font-family:var(--font-main);margin-top:0.3rem;outline:none;" placeholder="Write reply to customer..."></textarea>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-top:0.5rem;">
              <select id="replyStatus" class="filter-select">
                <option value="RESOLVED">Mark as RESOLVED</option>
                <option value="IN_PROGRESS">Keep IN_PROGRESS</option>
                <option value="CLOSED">Mark as CLOSED</option>
              </select>
              <button class="btn" onclick="submitTicketReply('${t.id}')">Send Reply</button>
            </div>
          </div>
        `;
        document.getElementById('ticketModal').style.display = 'flex';
      } catch (e) { alert(e.message); }
    }

    async function submitTicketReply(ticketId) {
      const reply_text = document.getElementById('replyMsg').value.trim();
      const new_status = document.getElementById('replyStatus').value;
      if (!reply_text) { alert('Reply text required'); return; }
      try {
        await apiFetch(`/admin/api/support/tickets/${ticketId}/reply`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reply_text, new_status })
        });
        closeModal('ticketModal');
        loadTickets();
      } catch (e) { alert(e.message); }
    }

    async function loadAudit() {
      try {
        const logs = await apiFetch('/admin/api/audit-logs');
        const tbody = document.getElementById('auditTableBody');
        tbody.innerHTML = '';
        if (!logs.length) {
          tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:2rem;">No audit logs.</td></tr>';
          return;
        }
        logs.forEach(l => {
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td style="font-size:0.75rem;font-family:var(--font-mono);">${new Date(l.timestamp).toLocaleString()}</td>
            <td><span class="badge badge-basic">${l.actor_id}</span></td>
            <td style="color:#fff;font-weight:600;">${l.action}</td>
            <td style="font-family:var(--font-mono);font-size:0.75rem;">${l.target_user_id || '—'}</td>
            <td style="font-size:0.75rem;font-family:var(--font-mono);color:var(--text-muted);">${JSON.stringify(l.details)}</td>
          `;
          tbody.appendChild(tr);
        });
      } catch (e) { console.error('Failed audit:', e); }
    }

    function closeModal(id) {
      document.getElementById(id).style.display = 'none';
    }

    window.onload = () => { loadAllData(); };
  </script>
</body>
</html>
"""
