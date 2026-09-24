"""
licensing_server/routes/device.py — Device management endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from licensing_server.database import UserDB, get_db
from licensing_server.middleware.auth_middleware import get_current_user
from licensing_server.services.entitlement_signer import EntitlementSigner
from licensing_server.services.license_service import LicenseService

router = APIRouter(prefix="/devices", tags=["Devices"])
signer = EntitlementSigner()
license_service = LicenseService(signer)


@router.get("/")
def list_devices(
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    devices = license_service.get_user_devices(db, user.id)
    return {"success": True, "devices": devices}
