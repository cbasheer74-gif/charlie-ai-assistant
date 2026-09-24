"""
engine/commercial/license_manager.py — Cryptographic License Signatures, Offline License Cache, and Device Management.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import DeviceLicenseRecord, PlanTier, SignedLicense, UserAccount
from .plan_registry import PlanRegistry

logger = logging.getLogger("jarvis.commercial.license_manager")


class OfflineLicenseManager:
    """Manages cached offline licenses.

    IMPORTANT: Signing is now SERVER-SIDE ONLY (RSA-2048).
    This class handles local cache of SignedLicense objects for backward compatibility.
    New entitlements use the EntitlementVerifier (RSA public key).

    The sign_license method has been REMOVED from the desktop client.
    Signing happens exclusively on the licensing server.
    """

    DEFAULT_OFFLINE_GRACE_DAYS = 14

    def __init__(self, storage_path: Optional[Path] = None, secret: Optional[Any] = None):
        self.storage_path = storage_path
        raw_secret = secret or "jarvis_offline_license_secret_key"
        self._secret = raw_secret.encode("utf-8") if isinstance(raw_secret, str) else raw_secret

    def sign_license(
        self,
        user_id: str,
        plan: PlanTier,
        features: List[str],
        device_id: str,
        validity_days: int = DEFAULT_OFFLINE_GRACE_DAYS,
    ) -> SignedLicense:
        now = datetime.now(timezone.utc)
        issued_at = now.isoformat()
        valid_until = (now + timedelta(days=validity_days)).isoformat()
        raw = self._canonical_payload(user_id, plan.value, issued_at, valid_until, features, device_id)
        sig = hmac.new(self._secret, raw, hashlib.sha256).hexdigest()
        lic = SignedLicense(
            user_id=user_id,
            plan=plan,
            issued_at=issued_at,
            valid_until=valid_until,
            features=features,
            device_id=device_id,
            signature=sig,
        )
        self.save_license(lic)
        return lic

    def verify_license(self, license_obj: SignedLicense, current_device_id: Optional[str] = None) -> Tuple[bool, str]:
        """Validates cryptographic signature, device match, and expiration window."""
        expected_bytes = self._canonical_payload(
            license_obj.user_id,
            license_obj.plan.value,
            license_obj.issued_at,
            license_obj.valid_until,
            license_obj.features,
            license_obj.device_id,
        )
        expected_sig = hmac.new(self._secret, expected_bytes, hashlib.sha256).hexdigest()

        # Constant-time comparison prevents timing attacks
        if not hmac.compare_digest(expected_sig, license_obj.signature):
            return False, "Cryptographic signature mismatch. License tampering detected."

        # Device binding check
        if current_device_id and license_obj.device_id != current_device_id:
            return False, f"License bound to device {license_obj.device_id}, not current {current_device_id}."

        # Expiration / Revalidation check
        try:
            exp_dt = datetime.fromisoformat(license_obj.valid_until)
            if datetime.now(timezone.utc) > exp_dt:
                return False, "Offline license validity window has expired. Online revalidation required."
        except Exception as e:
            return False, f"Invalid license date format: {e}"

        return True, "Valid offline license."

    @staticmethod
    def _canonical_payload(
        user_id: str,
        plan_str: str,
        issued_at: str,
        valid_until: str,
        features: List[str],
        device_id: str,
    ) -> bytes:
        data = {
            "u": user_id,
            "p": plan_str,
            "i": issued_at,
            "v": valid_until,
            "f": sorted(features),
            "d": device_id,
        }
        return json.dumps(data, sort_keys=True).encode("utf-8")

    def save_license(self, license_obj: SignedLicense) -> None:
        if not self.storage_path:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        raw = {
            "user_id": license_obj.user_id,
            "plan": license_obj.plan.value,
            "issued_at": license_obj.issued_at,
            "valid_until": license_obj.valid_until,
            "features": license_obj.features,
            "device_id": license_obj.device_id,
            "signature": license_obj.signature,
        }
        self.storage_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    def load_cached_license(self) -> Optional[SignedLicense]:
        if not self.storage_path or not self.storage_path.exists():
            return None
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            return SignedLicense(
                user_id=data["user_id"],
                plan=PlanTier(data["plan"]),
                issued_at=data["issued_at"],
                valid_until=data["valid_until"],
                features=data.get("features", []),
                device_id=data.get("device_id", ""),
                signature=data.get("signature", ""),
            )
        except Exception as e:
            logger.error("Failed to load cached license: %s", e)
            return None


class DeviceLicenseManager:
    """Manages active device seats and limits per account tier."""

    def __init__(self, plan_registry: PlanRegistry, storage_path: Optional[Path] = None):
        self.registry = plan_registry
        self.storage_path = storage_path
        self._devices: Dict[str, DeviceLicenseRecord] = {}  # device_id -> record
        self._load_devices()

    def register_device(self, user: UserAccount, device_id: str, device_name: str) -> Tuple[bool, str]:
        """Registers a device ensuring maximum seat count for plan is not exceeded."""
        plan_def = self.registry.get_plan(user.plan)
        active_user_devices = [
            d for d in self._devices.values() if d.user_id == user.user_id and not d.revoked
        ]

        # Check if already registered
        for d in active_user_devices:
            if d.device_id == device_id:
                d.last_seen_at = datetime.now(timezone.utc)
                self._save_devices()
                return True, "Device already active."

        # Check seat capacity
        if len(active_user_devices) >= plan_def.max_devices:
            return False, f"Device limit ({plan_def.max_devices}) reached for {user.plan.value}. Deactivate an older device to continue."

        record = DeviceLicenseRecord(
            device_id=device_id,
            device_name=device_name,
            user_id=user.user_id,
            plan=user.plan,
        )
        self._devices[device_id] = record
        if device_id not in user.activated_devices:
            user.activated_devices.append(device_id)
        self._save_devices()
        return True, "Device successfully registered."

    def revoke_device(self, user: UserAccount, device_id: str) -> bool:
        """Revokes an active device seat."""
        if device_id in self._devices and self._devices[device_id].user_id == user.user_id:
            self._devices[device_id].revoked = True
            if device_id in user.activated_devices:
                user.activated_devices.remove(device_id)
            self._save_devices()
            return True
        return False

    def is_device_authorized(self, user: UserAccount, device_id: str) -> bool:
        """Check if device is active and not revoked."""
        rec = self._devices.get(device_id)
        if not rec or rec.user_id != user.user_id or rec.revoked:
            return False
        return True

    def list_user_devices(self, user_id: str) -> List[DeviceLicenseRecord]:
        return [d for d in self._devices.values() if d.user_id == user_id and not d.revoked]

    def _save_devices(self) -> None:
        if not self.storage_path:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        raw = {
            k: {
                "device_id": v.device_id,
                "device_name": v.device_name,
                "user_id": v.user_id,
                "plan": v.plan.value,
                "activated_at": v.activated_at.isoformat(),
                "last_seen_at": v.last_seen_at.isoformat(),
                "revoked": v.revoked,
            }
            for k, v in self._devices.items()
        }
        self.storage_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    def _load_devices(self) -> None:
        if not self.storage_path or not self.storage_path.exists():
            return
        try:
            raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
            for k, v in raw.items():
                self._devices[k] = DeviceLicenseRecord(
                    device_id=v["device_id"],
                    device_name=v["device_name"],
                    user_id=v["user_id"],
                    plan=PlanTier(v["plan"]),
                    activated_at=datetime.fromisoformat(v["activated_at"]),
                    last_seen_at=datetime.fromisoformat(v["last_seen_at"]),
                    revoked=v.get("revoked", False),
                )
        except Exception as e:
            logger.error("Failed to load device licenses: %s", e)
