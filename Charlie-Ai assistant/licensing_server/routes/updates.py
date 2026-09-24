"""
licensing_server/routes/updates.py — Official Signed Updates & Release Management API.

Serves RSA-2048 verified update manifests, staged rollouts, and telemetry to desktop clients.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from licensing_server.database import UserDB, get_db
from licensing_server.middleware.auth_middleware import require_admin, require_owner
from licensing_server.services.update_service import UpdateService

router = APIRouter(prefix="/updates", tags=["Automatic Updates"])
update_service = UpdateService()


class RegisterReleaseRequest(BaseModel):
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$", description="SemVer string e.g. 1.0.1")
    build_number: int = Field(default=100)
    download_url: str = Field(...)
    sha256: str = Field(..., min_length=64, max_length=64)
    file_size: int = Field(default=0)
    channel: str = Field(default="STABLE")
    release_notes: str = Field(default="")
    mandatory: bool = Field(default=False)
    security_update: bool = Field(default=False)
    rollback_supported: bool = Field(default=True)
    database_schema_version: int = Field(default=1)
    min_supported_version: str = Field(default="1.0.0")
    minimum_os_version: str = Field(default="10.0")
    rollout_percentage: int = Field(default=100, ge=0, le=100)


class RolloutChangeRequest(BaseModel):
    rollout_percentage: int = Field(..., ge=0, le=100)


class RevokeReleaseRequest(BaseModel):
    reason: str = Field(..., min_length=3)


class TelemetryEventRequest(BaseModel):
    event_type: str = Field(..., description="e.g. UPDATE_AVAILABLE, DOWNLOAD_COMPLETED, INSTALL_SUCCESS, ROLLED_BACK")
    client_version: str = Field(...)
    target_version: str = Field(...)
    channel: str = Field(default="STABLE")
    device_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


@router.get("/check")
def check_for_updates(
    version: str = Query(default="1.0.0", description="Current client app version"),
    channel: str = Query(default="STABLE", description="Update channel: STABLE, BETA, INTERNAL"),
    device_id: Optional[str] = Query(default=None, description="Client device ID for staged rollout cohorts"),
    db: Session = Depends(get_db),
):
    """Check if an official signed update is available."""
    return update_service.check_update(db, client_version=version, channel=channel, device_id=device_id)


@router.get("/manifest/{version}")
def get_release_manifest(
    version: str,
    db: Session = Depends(get_db),
):
    """Fetch the canonical signed release manifest for a specific version."""
    from licensing_server.database import UpdateReleaseDB
    rel = db.query(UpdateReleaseDB).filter(UpdateReleaseDB.version == version).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Release version not found.")

    manifest = update_service._build_canonical_manifest(rel)
    return {
        "status": "ok",
        "version": rel.version,
        "manifest": manifest,
        "signature": rel.signature,
    }


@router.post("/telemetry")
def record_update_telemetry(
    req: TelemetryEventRequest,
    db: Session = Depends(get_db),
):
    """Records anonymous update execution telemetry."""
    ok = update_service.record_telemetry(
        db=db,
        event_type=req.event_type,
        client_version=req.client_version,
        target_version=req.target_version,
        channel=req.channel,
        device_id=req.device_id,
        details=req.details,
    )
    return {"status": "ok", "recorded": ok}


@router.post("/releases")
def register_release(
    req: RegisterReleaseRequest,
    admin: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Publish a cryptographically signed release to the update catalog."""
    success, msg, release = update_service.register_release(
        db,
        version=req.version,
        download_url=req.download_url,
        sha256=req.sha256,
        channel=req.channel,
        build_number=req.build_number,
        file_size=req.file_size,
        release_notes=req.release_notes,
        mandatory=req.mandatory,
        security_update=req.security_update,
        rollback_supported=req.rollback_supported,
        database_schema_version=req.database_schema_version,
        min_supported_version=req.min_supported_version,
        minimum_os_version=req.minimum_os_version,
        rollout_percentage=req.rollout_percentage,
        admin_id=admin.id,
    )
    if not success or not release:
        raise HTTPException(status_code=400, detail=msg)

    return {
        "status": "ok",
        "message": msg,
        "release": {
            "version": release.version,
            "channel": release.channel,
            "status": release.status,
            "rollout_percentage": release.rollout_percentage,
            "sha256": release.sha256,
            "signature": release.signature,
            "download_url": release.download_url,
        },
    }


@router.post("/releases/{version}/pause")
def pause_release(
    version: str,
    admin: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Pause an active release rollout immediately."""
    ok, msg = update_service.pause_release(db, version=version, admin_id=admin.id)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


@router.post("/releases/{version}/revoke")
def revoke_release(
    version: str,
    req: RevokeReleaseRequest,
    admin: UserDB = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Revoke a release due to defect or security issue (Owner only)."""
    ok, msg = update_service.revoke_release(db, version=version, reason=req.reason, admin_id=admin.id)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


@router.post("/releases/{version}/rollout")
def set_rollout(
    version: str,
    req: RolloutChangeRequest,
    admin: UserDB = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update release rollout percentage."""
    ok, msg = update_service.set_rollout_percentage(
        db, version=version, percentage=req.rollout_percentage, admin_id=admin.id
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}
