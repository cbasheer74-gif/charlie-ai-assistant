"""
licensing_server/routes/entitlement.py — Entitlement refresh and verification endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from licensing_server.database import UserDB, get_db
from licensing_server.middleware.auth_middleware import get_current_user
from licensing_server.services.entitlement_signer import EntitlementSigner
from licensing_server.services.license_service import LicenseService

router = APIRouter(prefix="/entitlement", tags=["Entitlement"])
signer = EntitlementSigner()
license_service = LicenseService(signer)


class RefreshEntitlementRequest(BaseModel):
    device_id: str
    fingerprint_hash: str


@router.post("/refresh")
def refresh_entitlement(
    req: RefreshEntitlementRequest,
    user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ok, msg, data = license_service.refresh_entitlement(db, user.id, req.device_id, req.fingerprint_hash)
    if not ok:
        return {"success": False, "error": msg}
    return {"success": True, "message": msg, "data": data}


@router.get("/public-key")
def get_public_key():
    """Returns the RSA public key for desktop client entitlement verification."""
    return {"success": True, "public_key": signer.public_key_pem}
