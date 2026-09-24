"""
licensing_server/services/license_service.py — Core one-active-PC enforcement, device activation, and license transfer.

CRITICAL RULES:
  1. One subscription = ONE active device at a time
  2. Transfer requires fresh authentication
  3. Transfer is atomic: deactivate old → activate new → issue entitlement
  4. Transfer cooldown: MAX_TRANSFERS_PER_MONTH
  5. Copying EXE/data to another PC does NOT activate paid access
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from licensing_server.config import config
from licensing_server.database import (
    DeviceDB,
    DeviceStatusEnum,
    LicenseEventDB,
    LicenseEventType,
    PlanTier,
    SignedEntitlementDB,
    SubscriptionDB,
    SubscriptionStatus,
    TransferEventDB,
)
from licensing_server.services.entitlement_signer import EntitlementSigner


# Plan → feature list (matches desktop PlanRegistry)
PLAN_FEATURES = {
    PlanTier.STARTER.value: ["TEXT_CHAT", "VOICE_MALE", "COMPUTER_BASIC", "MEMORY_BASIC", "SKILLS_BASIC"],
    PlanTier.BASIC.value: ["TEXT_CHAT", "VOICE_MALE", "COMPUTER_BASIC", "MEMORY_BASIC", "SPREADSHEET_BASIC", "RESEARCH_BASIC", "SKILLS_BASIC", "OFFLINE_AI"],
    PlanTier.PREMIUM.value: ["TEXT_CHAT", "VOICE_MALE", "VOICE_FEMALE", "VOICE_MULTIPLE", "COMPUTER_BASIC", "MEMORY_BASIC", "MEMORY_ADVANCED", "KNOWLEDGE_GRAPH", "CODING", "SPREADSHEET_BASIC", "SPREADSHEET_ADVANCED", "GMAIL", "CALENDAR", "DRIVE", "MULTI_AGENT", "VIDEO_BASIC", "PLUGINS", "MULTI_DEVICE", "OFFLINE_AI"],
    PlanTier.ADVANCED.value: ["TEXT_CHAT", "VOICE_MALE", "VOICE_FEMALE", "VOICE_MULTIPLE", "COMPUTER_BASIC", "COMPUTER_ADVANCED", "MEMORY_BASIC", "MEMORY_ADVANCED", "KNOWLEDGE_GRAPH", "CODING", "AUTONOMY_ADVANCED", "RESEARCH_DEEP", "SPREADSHEET_BASIC", "SPREADSHEET_ADVANCED", "GMAIL", "CALENDAR", "DRIVE", "MULTI_AGENT", "VIDEO_BASIC", "VIDEO_FILMORA", "YOUTUBE_AUTOMATION", "PLUGINS", "SKILLS_BASIC", "SKILL_LEARNING", "MCP", "CUSTOM_AGENTS", "MULTI_DEVICE", "OFFLINE_AI", "PROACTIVE_INTELLIGENCE"],
    PlanTier.PRO.value: ["TEXT_CHAT", "VOICE_MALE", "VOICE_FEMALE", "VOICE_MULTIPLE", "COMPUTER_BASIC", "MEMORY_BASIC", "MEMORY_ADVANCED", "KNOWLEDGE_GRAPH", "CODING", "SPREADSHEET_BASIC", "SPREADSHEET_ADVANCED", "GMAIL", "CALENDAR", "DRIVE", "MULTI_AGENT", "VIDEO_BASIC", "PLUGINS", "MULTI_DEVICE", "OFFLINE_AI"],
    PlanTier.PRO_PLUS.value: ["TEXT_CHAT", "VOICE_MALE", "VOICE_FEMALE", "VOICE_MULTIPLE", "COMPUTER_BASIC", "COMPUTER_ADVANCED", "MEMORY_BASIC", "MEMORY_ADVANCED", "KNOWLEDGE_GRAPH", "CODING", "AUTONOMY_ADVANCED", "RESEARCH_DEEP", "SPREADSHEET_BASIC", "SPREADSHEET_ADVANCED", "GMAIL", "CALENDAR", "DRIVE", "MULTI_AGENT", "VIDEO_BASIC", "VIDEO_FILMORA", "YOUTUBE_AUTOMATION", "PLUGINS", "SKILLS_BASIC", "SKILL_LEARNING", "MCP", "CUSTOM_AGENTS", "MULTI_DEVICE", "OFFLINE_AI", "PROACTIVE_INTELLIGENCE"],
    PlanTier.ANNUAL_PRO.value: ["TEXT_CHAT", "VOICE_MALE", "VOICE_FEMALE", "VOICE_MULTIPLE", "COMPUTER_BASIC", "COMPUTER_ADVANCED", "MEMORY_BASIC", "MEMORY_ADVANCED", "KNOWLEDGE_GRAPH", "CODING", "RESEARCH_DEEP", "SPREADSHEET_BASIC", "SPREADSHEET_ADVANCED", "GMAIL", "CALENDAR", "DRIVE", "MULTI_AGENT", "VIDEO_BASIC", "PLUGINS", "SKILLS_BASIC", "SKILL_LEARNING", "MULTI_DEVICE", "OFFLINE_AI"],
    PlanTier.LIFETIME.value: ["TEXT_CHAT", "VOICE_MALE", "VOICE_FEMALE", "VOICE_MULTIPLE", "COMPUTER_BASIC", "COMPUTER_ADVANCED", "MEMORY_BASIC", "MEMORY_ADVANCED", "KNOWLEDGE_GRAPH", "CODING", "AUTONOMY_ADVANCED", "RESEARCH_DEEP", "SPREADSHEET_BASIC", "SPREADSHEET_ADVANCED", "GMAIL", "CALENDAR", "DRIVE", "MULTI_AGENT", "VIDEO_BASIC", "VIDEO_FILMORA", "YOUTUBE_AUTOMATION", "PLUGINS", "SKILLS_BASIC", "SKILL_LEARNING", "MCP", "CUSTOM_AGENTS", "MULTI_DEVICE", "OFFLINE_AI", "PROACTIVE_INTELLIGENCE"],
}


class LicenseService:
    """Authoritative license management: activation, transfer, deactivation, entitlement issuance."""

    def __init__(self, signer: EntitlementSigner):
        self.signer = signer

    def activate_device(
        self,
        db: Session,
        user_id: str,
        device_id: str,
        fingerprint_hash: str,
        device_public_key: str,
        device_name: str = "Unknown PC",
        os_type: str = "Windows",
        app_version: str = "1.0.0",
    ) -> Tuple[bool, str, Optional[dict]]:
        """Activate device for user's subscription. Returns (ok, message, entitlement_data)."""

        sub = db.query(SubscriptionDB).filter(SubscriptionDB.user_id == user_id).first()
        if not sub:
            return False, "No subscription found.", None

        # Check if subscription has a paid plan
        is_paid = sub.plan != PlanTier.STARTER.value and sub.status in (
            SubscriptionStatus.ACTIVE.value,
            SubscriptionStatus.LIFETIME_ACTIVE.value,
            SubscriptionStatus.GRACE_PERIOD.value,
            SubscriptionStatus.CANCEL_AT_PERIOD_END.value,
        )

        # If there's already an active device that's DIFFERENT
        if sub.active_device_id and sub.active_device_id != device_id and is_paid:
            active_device = db.query(DeviceDB).filter(DeviceDB.id == sub.active_device_id).first()
            return False, "DEVICE_CONFLICT", {
                "active_device_id": sub.active_device_id,
                "active_device_name": active_device.device_name if active_device else "Unknown",
                "active_device_last_seen": active_device.last_seen.isoformat() if active_device and active_device.last_seen else None,
            }

        # Register or update device
        device = db.query(DeviceDB).filter(DeviceDB.id == device_id).first()
        if not device:
            device = DeviceDB(
                id=device_id,
                user_id=user_id,
                device_public_key=device_public_key,
                fingerprint_hash=fingerprint_hash,
                device_name=device_name,
                os_type=os_type,
                app_version=app_version,
                status=DeviceStatusEnum.ACTIVE.value,
                activated_at=datetime.now(timezone.utc),
                last_seen=datetime.now(timezone.utc),
            )
            db.add(device)
        else:
            # Verify fingerprint matches (prevent cloned device IDs)
            if device.fingerprint_hash != fingerprint_hash:
                return False, "Device fingerprint mismatch. Possible clone detected.", None
            device.status = DeviceStatusEnum.ACTIVE.value
            device.last_seen = datetime.now(timezone.utc)
            device.device_public_key = device_public_key
            device.app_version = app_version

        # Set as active device
        sub.active_device_id = device_id
        db.commit()

        # Audit
        self._log_event(db, user_id, device_id, LicenseEventType.DEVICE_ACTIVATED, {"plan": sub.plan})

        # Issue signed entitlement
        features = PLAN_FEATURES.get(sub.plan, PLAN_FEATURES[PlanTier.STARTER.value])
        license_type = "LIFETIME" if sub.plan == PlanTier.LIFETIME.value else "MONTHLY"
        ent_data = self.signer.sign_entitlement(
            user_id=user_id,
            subscription_id=sub.id,
            plan=sub.plan,
            device_id=device_id,
            features=features,
            license_type=license_type,
        )

        # Persist entitlement
        ent_record = SignedEntitlementDB(
            id=ent_data["entitlement_id"],
            user_id=user_id,
            subscription_id=sub.id,
            device_id=device_id,
            plan=sub.plan,
            features_json=json.dumps(features),
            expires_at=datetime.fromisoformat(ent_data["expires_at"]),
            revalidation_at=datetime.fromisoformat(ent_data["revalidation_at"]),
            license_type=license_type,
            signature=ent_data["signature_b64"],
        )
        db.add(ent_record)
        db.commit()

        return True, "Device activated.", {
            "plan": sub.plan,
            "status": sub.status,
            "token": ent_data["token"],
            "expires_at": ent_data["expires_at"],
            "revalidation_at": ent_data["revalidation_at"],
        }

    def transfer_license(
        self,
        db: Session,
        user_id: str,
        new_device_id: str,
        new_fingerprint_hash: str,
        new_device_public_key: str,
        new_device_name: str = "New PC",
        os_type: str = "Windows",
        app_version: str = "1.0.0",
    ) -> Tuple[bool, str, Optional[dict]]:
        """Atomic license transfer: deactivate old PC → activate new PC → issue new entitlement.

        Returns (ok, message, entitlement_data).
        """
        sub = db.query(SubscriptionDB).filter(SubscriptionDB.user_id == user_id).first()
        if not sub:
            return False, "No subscription found.", None

        # Check transfer cooldown
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        recent_transfers = (
            db.query(TransferEventDB)
            .filter(
                TransferEventDB.user_id == user_id,
                TransferEventDB.transferred_at >= thirty_days_ago,
            )
            .count()
        )
        if recent_transfers >= config.MAX_TRANSFERS_PER_MONTH:
            return False, f"Transfer limit reached ({config.MAX_TRANSFERS_PER_MONTH}/month). Contact support.", None

        old_device_id = sub.active_device_id

        # Deactivate old device
        if old_device_id:
            old_device = db.query(DeviceDB).filter(DeviceDB.id == old_device_id).first()
            if old_device:
                old_device.status = DeviceStatusEnum.INACTIVE.value
            self._log_event(db, user_id, old_device_id, LicenseEventType.DEVICE_DEACTIVATED, {"reason": "transfer"})

        # Register/update new device
        new_device = db.query(DeviceDB).filter(DeviceDB.id == new_device_id).first()
        if not new_device:
            new_device = DeviceDB(
                id=new_device_id,
                user_id=user_id,
                device_public_key=new_device_public_key,
                fingerprint_hash=new_fingerprint_hash,
                device_name=new_device_name,
                os_type=os_type,
                app_version=app_version,
                status=DeviceStatusEnum.ACTIVE.value,
                activated_at=datetime.now(timezone.utc),
                last_seen=datetime.now(timezone.utc),
            )
            db.add(new_device)
        else:
            new_device.status = DeviceStatusEnum.ACTIVE.value
            new_device.activated_at = datetime.now(timezone.utc)
            new_device.last_seen = datetime.now(timezone.utc)
            new_device.device_public_key = new_device_public_key

        # Atomic: set new active device
        sub.active_device_id = new_device_id

        # Record transfer event
        transfer = TransferEventDB(
            id=f"xfer_{uuid.uuid4().hex[:16]}",
            user_id=user_id,
            from_device_id=old_device_id or "none",
            to_device_id=new_device_id,
        )
        db.add(transfer)
        db.commit()

        self._log_event(db, user_id, new_device_id, LicenseEventType.LICENSE_TRANSFERRED, {
            "from": old_device_id,
            "to": new_device_id,
        })

        # Issue fresh signed entitlement for new device
        features = PLAN_FEATURES.get(sub.plan, PLAN_FEATURES[PlanTier.STARTER.value])
        license_type = "LIFETIME" if sub.plan == PlanTier.LIFETIME.value else "MONTHLY"
        ent_data = self.signer.sign_entitlement(
            user_id=user_id,
            subscription_id=sub.id,
            plan=sub.plan,
            device_id=new_device_id,
            features=features,
            license_type=license_type,
        )

        ent_record = SignedEntitlementDB(
            id=ent_data["entitlement_id"],
            user_id=user_id,
            subscription_id=sub.id,
            device_id=new_device_id,
            plan=sub.plan,
            features_json=json.dumps(features),
            expires_at=datetime.fromisoformat(ent_data["expires_at"]),
            revalidation_at=datetime.fromisoformat(ent_data["revalidation_at"]),
            license_type=license_type,
            signature=ent_data["signature_b64"],
        )
        db.add(ent_record)
        db.commit()

        return True, "License transferred successfully.", {
            "plan": sub.plan,
            "status": sub.status,
            "token": ent_data["token"],
            "old_device_id": old_device_id,
            "new_device_id": new_device_id,
            "expires_at": ent_data["expires_at"],
        }

    def deactivate_device(self, db: Session, user_id: str, device_id: str) -> Tuple[bool, str]:
        """Deactivate a specific device. Subscription becomes unbound."""
        sub = db.query(SubscriptionDB).filter(SubscriptionDB.user_id == user_id).first()
        if not sub:
            return False, "No subscription found."

        device = db.query(DeviceDB).filter(DeviceDB.id == device_id, DeviceDB.user_id == user_id).first()
        if not device:
            return False, "Device not found."

        device.status = DeviceStatusEnum.INACTIVE.value
        if sub.active_device_id == device_id:
            sub.active_device_id = None
        db.commit()

        self._log_event(db, user_id, device_id, LicenseEventType.DEVICE_DEACTIVATED, {"reason": "manual"})
        return True, "Device deactivated. You can activate another PC."

    def revoke_device(self, db: Session, user_id: str, device_id: str) -> Tuple[bool, str]:
        """Revoke a device (stolen/lost). Stronger than deactivation."""
        device = db.query(DeviceDB).filter(DeviceDB.id == device_id, DeviceDB.user_id == user_id).first()
        if not device:
            return False, "Device not found."

        device.status = DeviceStatusEnum.REVOKED.value
        sub = db.query(SubscriptionDB).filter(SubscriptionDB.user_id == user_id).first()
        if sub and sub.active_device_id == device_id:
            sub.active_device_id = None
        db.commit()

        self._log_event(db, user_id, device_id, LicenseEventType.LICENSE_REVOKED, {"reason": "remote_revoke"})
        return True, "Device revoked. Activate a new device anytime."

    def refresh_entitlement(self, db: Session, user_id: str, device_id: str, fingerprint_hash: str) -> Tuple[bool, str, Optional[dict]]:
        """Reissue signed entitlement if device is currently active."""
        sub = db.query(SubscriptionDB).filter(SubscriptionDB.user_id == user_id).first()
        if not sub:
            return False, "No subscription found.", None

        # Verify device is the active one
        if sub.active_device_id != device_id:
            return False, "This device is not the active device for this subscription.", None

        # Verify fingerprint
        device = db.query(DeviceDB).filter(DeviceDB.id == device_id).first()
        if not device or device.fingerprint_hash != fingerprint_hash:
            self._log_event(db, user_id, device_id, LicenseEventType.TAMPER_DETECTED, {"reason": "fingerprint_mismatch"})
            return False, "Device fingerprint mismatch.", None

        if device.status == DeviceStatusEnum.REVOKED.value:
            return False, "This device has been revoked.", None

        # Check subscription expiry
        if sub.status in (SubscriptionStatus.EXPIRED.value, SubscriptionStatus.CANCELLED.value, SubscriptionStatus.SUSPENDED.value):
            return False, f"Subscription {sub.status}. Renew to continue.", None

        # Update last seen
        device.last_seen = datetime.now(timezone.utc)
        db.commit()

        # Issue fresh entitlement
        features = PLAN_FEATURES.get(sub.plan, PLAN_FEATURES[PlanTier.STARTER.value])
        license_type = "LIFETIME" if sub.plan == PlanTier.LIFETIME.value else "MONTHLY"
        ent_data = self.signer.sign_entitlement(
            user_id=user_id,
            subscription_id=sub.id,
            plan=sub.plan,
            device_id=device_id,
            features=features,
            license_type=license_type,
        )

        self._log_event(db, user_id, device_id, LicenseEventType.LICENSE_REFRESH, {"plan": sub.plan})

        return True, "Entitlement refreshed.", {
            "plan": sub.plan,
            "status": sub.status,
            "token": ent_data["token"],
            "expires_at": ent_data["expires_at"],
            "revalidation_at": ent_data["revalidation_at"],
        }

    def get_user_devices(self, db: Session, user_id: str) -> List[dict]:
        """List all devices for a user."""
        devices = db.query(DeviceDB).filter(DeviceDB.user_id == user_id).all()
        sub = db.query(SubscriptionDB).filter(SubscriptionDB.user_id == user_id).first()
        active_id = sub.active_device_id if sub else None

        return [
            {
                "device_id": d.id,
                "device_name": d.device_name,
                "os_type": d.os_type,
                "status": d.status,
                "is_active": d.id == active_id,
                "activated_at": d.activated_at.isoformat() if d.activated_at else None,
                "last_seen": d.last_seen.isoformat() if d.last_seen else None,
                "app_version": d.app_version,
            }
            for d in devices
        ]

    @staticmethod
    def _log_event(db: Session, user_id: str, device_id: Optional[str], event_type: LicenseEventType, details: dict) -> None:
        event = LicenseEventDB(
            id=f"evt_{uuid.uuid4().hex[:16]}",
            user_id=user_id,
            device_id=device_id,
            event_type=event_type.value,
            details_json=json.dumps(details),
        )
        db.add(event)
        db.commit()
