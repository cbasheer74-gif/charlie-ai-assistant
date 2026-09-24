"""
licensing_server/routes/license.py — License activation, transfer, deactivation endpoints.

All endpoints require authenticated user (JWT Bearer).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from licensing_server.database import UserDB, get_db
from licensing_server.middleware.auth_middleware import get_current_user
from licensing_server.middleware.rate_limiter import limit_activation, limit_transfer
from licensing_server.services.entitlement_signer import EntitlementSigner
from licensing_server.services.license_service import LicenseService

router = APIRouter(prefix="/license", tags=["License"])
signer = EntitlementSigner()
license_service = LicenseService(signer)


class ActivateRequest(BaseModel):
    device_id: str = Field(..., min_length=8)
    fingerprint_hash: str = Field(..., min_length=16)
    device_public_key: str
    device_name: str = "Unknown PC"
    os_type: str = "Windows"
    app_version: str = "1.0.0"


class TransferRequest(BaseModel):
    new_device_id: str = Field(..., min_length=8)
    new_fingerprint_hash: str = Field(..., min_length=16)
    new_device_public_key: str
    new_device_name: str = "New PC"
    os_type: str = "Windows"
    app_version: str = "1.0.0"


class DeactivateRequest(BaseModel):
    device_id: str


@router.post("/activate")
def activate_device(
    req: ActivateRequest,
    request: Request,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    limit_activation(request)
    ok, msg, data = license_service.activate_device(
        db=db,
        user_id=user.id,
        device_id=req.device_id,
        fingerprint_hash=req.fingerprint_hash,
        device_public_key=req.device_public_key,
        device_name=req.device_name,
        os_type=req.os_type,
        app_version=req.app_version,
    )
    if not ok:
        return {"success": False, "error": msg, "data": data}
    return {"success": True, "message": msg, "data": data}


@router.post("/transfer")
def transfer_license(
    req: TransferRequest,
    request: Request,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    limit_transfer(request)
    ok, msg, data = license_service.transfer_license(
        db=db,
        user_id=user.id,
        new_device_id=req.new_device_id,
        new_fingerprint_hash=req.new_fingerprint_hash,
        new_device_public_key=req.new_device_public_key,
        new_device_name=req.new_device_name,
        os_type=req.os_type,
        app_version=req.app_version,
    )
    if not ok:
        return {"success": False, "error": msg, "data": data}
    return {"success": True, "message": msg, "data": data}


@router.post("/deactivate")
def deactivate_device(
    req: DeactivateRequest,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ok, msg = license_service.deactivate_device(db, user.id, req.device_id)
    return {"success": ok, "message": msg}


@router.post("/revoke")
def revoke_device(
    req: DeactivateRequest,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ok, msg = license_service.revoke_device(db, user.id, req.device_id)
    return {"success": ok, "message": msg}
