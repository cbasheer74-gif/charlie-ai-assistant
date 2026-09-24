"""
licensing_server/services/update_service.py — Automatic update management, staged rollouts, and SemVer checking.

Ensures desktop clients receive RSA-2048 cryptographically signed, checksum-verified update manifests.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from licensing_server.config import config
from licensing_server.database import (
    AuditLogDB,
    ReleaseChannelEnum,
    ReleaseStatus,
    UpdateReleaseDB,
    UpdateTelemetryDB,
    _utcnow,
)
from licensing_server.services.entitlement_signer import EntitlementSigner


def parse_semver(version_str: str) -> Tuple[int, int, int]:
    """Parse 'x.y.z' string into tuple of ints. Defaults to (0, 0, 0) on error."""
    clean = version_str.strip().lstrip("v")
    # Strip any prerelease tags like -beta or -rc for numerical comparison
    if "-" in clean:
        clean = clean.split("-")[0]
    parts = clean.split(".")
    try:
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        return major, minor, patch
    except (ValueError, IndexError):
        return (0, 0, 0)


def is_newer_version(candidate: str, current: str) -> bool:
    """True if candidate version is strictly greater than current version."""
    return parse_semver(candidate) > parse_semver(current)


class UpdateService:
    """Authoritative release server catalog, RSA-2048 manifest signer, and staged rollout engine."""

    def __init__(self):
        self.signer = EntitlementSigner()

    def check_update(
        self,
        db: Session,
        client_version: str,
        channel: str = "STABLE",
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Check if an update is available for the given client version, channel, and device cohort."""
        channel_upper = channel.upper()

        # Channel isolation filter
        if channel_upper == "STABLE":
            allowed_channels = ["STABLE", "stable"]
        elif channel_upper == "BETA":
            allowed_channels = ["STABLE", "stable", "BETA", "beta"]
        else:  # INTERNAL / DEV
            allowed_channels = ["STABLE", "stable", "BETA", "beta", "INTERNAL", "internal", "DEV", "dev"]

        releases = (
            db.query(UpdateReleaseDB)
            .filter(UpdateReleaseDB.channel.in_(allowed_channels))
            .order_by(UpdateReleaseDB.released_at.desc())
            .all()
        )

        latest_eligible_release = None
        for r in releases:
            # 1. Skip non-published releases (DRAFT, PAUSED, REVOKED)
            status = getattr(r, "status", ReleaseStatus.PUBLISHED.value)
            if status not in (ReleaseStatus.PUBLISHED.value, "PUBLISHED", None):
                continue

            # 2. Check if strictly newer
            if not is_newer_version(r.version, client_version):
                continue

            # 3. Check staged rollout percentage
            rollout_pct = getattr(r, "rollout_percentage", 100) or 100
            if rollout_pct < 100:
                if device_id:
                    # Deterministic hash of device_id + version
                    seed = f"{device_id}:{r.version}".encode("utf-8")
                    cohort = int(hashlib.sha256(seed).hexdigest()[:8], 16) % 100
                    if cohort >= rollout_pct:
                        continue  # Device not in this rollout percentage cohort
                else:
                    # Unidentified device deferred if not 100% rollout
                    continue

            latest_eligible_release = r
            break

        if not latest_eligible_release:
            return {
                "update_available": False,
                "current_version": client_version,
                "latest_version": client_version,
                "message": "JARVIS is up to date.",
            }

        r = latest_eligible_release
        manifest = self._build_canonical_manifest(r)

        return {
            "update_available": True,
            "current_version": client_version,
            "latest_version": r.version,
            "channel": r.channel,
            "download_url": r.download_url,
            "sha256": r.sha256,
            "signature": r.signature,
            "mandatory": getattr(r, "mandatory", False),
            "security_update": getattr(r, "security_update", False),
            "rollback_supported": getattr(r, "rollback_supported", True),
            "database_schema_version": getattr(r, "database_schema_version", 1),
            "release_notes": r.release_notes or "",
            "min_supported_version": r.min_supported_version or "1.0.0",
            "minimum_os_version": getattr(r, "minimum_os_version", "10.0"),
            "file_size": getattr(r, "file_size", 0),
            "released_at": r.released_at.isoformat() if r.released_at else None,
            "manifest": manifest,
        }

    def _build_canonical_manifest(self, r: UpdateReleaseDB) -> Dict[str, Any]:
        """Construct canonical manifest dictionary for verification."""
        if getattr(r, "manifest_json", None):
            try:
                return json.loads(r.manifest_json)
            except Exception:
                pass
        return {
            "version": r.version,
            "build_number": getattr(r, "build_number", 100),
            "channel": str(r.channel).upper(),
            "download_url": r.download_url,
            "file_size": getattr(r, "file_size", 0),
            "sha256": r.sha256,
            "release_notes": r.release_notes or "",
            "mandatory_update": bool(getattr(r, "mandatory", False)),
            "security_update": bool(getattr(r, "security_update", False)),
            "rollback_supported": bool(getattr(r, "rollback_supported", True)),
            "database_schema_version": getattr(r, "database_schema_version", 1),
            "minimum_os_version": getattr(r, "minimum_os_version", "10.0"),
            "min_supported_version": r.min_supported_version or "1.0.0",
            "released_at": r.released_at.isoformat() if r.released_at else _utcnow().isoformat(),
        }

    def sign_manifest(self, manifest_dict: Dict[str, Any]) -> str:
        """Signs canonical JSON manifest with server's RSA-PSS private key."""
        canonical_json = json.dumps(manifest_dict, sort_keys=True, separators=(",", ":"))
        return self.signer.sign_payload(canonical_json)

    def register_release(
        self,
        db: Session,
        version: str,
        download_url: str,
        sha256: str,
        channel: str = "STABLE",
        build_number: int = 100,
        file_size: int = 0,
        release_notes: str = "",
        mandatory: bool = False,
        security_update: bool = False,
        rollback_supported: bool = True,
        database_schema_version: int = 1,
        min_supported_version: str = "1.0.0",
        minimum_os_version: str = "10.0",
        rollout_percentage: int = 100,
        admin_id: str = "SYSTEM",
    ) -> Tuple[bool, str, Optional[UpdateReleaseDB]]:
        """Publish a cryptographically signed release to the catalog."""
        existing = db.query(UpdateReleaseDB).filter(UpdateReleaseDB.version == version).first()
        if existing:
            return False, f"Version {version} already registered.", None

        channel_upper = channel.upper()
        now = _utcnow()

        manifest_proto = {
            "version": version,
            "build_number": build_number,
            "channel": channel_upper,
            "download_url": download_url,
            "file_size": file_size,
            "sha256": sha256,
            "release_notes": release_notes,
            "mandatory_update": mandatory,
            "security_update": security_update,
            "rollback_supported": rollback_supported,
            "database_schema_version": database_schema_version,
            "minimum_os_version": minimum_os_version,
            "min_supported_version": min_supported_version,
            "released_at": now.isoformat(),
        }

        signature = self.sign_manifest(manifest_proto)

        release = UpdateReleaseDB(
            id=f"rel_{version.replace('.', '_')}",
            version=version,
            build_number=build_number,
            channel=channel_upper,
            status=ReleaseStatus.PUBLISHED.value,
            rollout_percentage=max(0, min(100, rollout_percentage)),
            download_url=download_url,
            file_size=file_size,
            sha256=sha256,
            signature=signature,
            manifest_json=json.dumps(manifest_proto, sort_keys=True),
            release_notes=release_notes,
            mandatory=mandatory,
            security_update=security_update,
            rollback_supported=rollback_supported,
            database_schema_version=database_schema_version,
            min_supported_version=min_supported_version,
            minimum_os_version=minimum_os_version,
            created_by=admin_id,
            released_at=now,
        )

        db.add(release)

        # Audit event
        audit = AuditLogDB(
            id=f"aud_rel_{hashlib.md5(f'{version}{now}'.encode()).hexdigest()[:12]}",
            actor_id=admin_id,
            action="RELEASE_PUBLISHED",
            target_user_id=None,
            target_device_id=None,
            details_json=json.dumps({
                "version": version,
                "channel": channel_upper,
                "rollout_percentage": rollout_percentage,
                "sha256": sha256,
            }),
            timestamp=now,
        )
        db.add(audit)

        db.commit()
        db.refresh(release)
        return True, "Release registered and signed successfully.", release

    def pause_release(self, db: Session, version: str, admin_id: str = "SYSTEM") -> Tuple[bool, str]:
        """Pauses release rollout immediately."""
        rel = db.query(UpdateReleaseDB).filter(UpdateReleaseDB.version == version).first()
        if not rel:
            return False, f"Release {version} not found."
        rel.status = ReleaseStatus.PAUSED.value
        audit = AuditLogDB(
            id=f"aud_rel_p_{hashlib.md5(f'{version}{_utcnow()}'.encode()).hexdigest()[:12]}",
            actor_id=admin_id,
            action="RELEASE_PAUSED",
            details_json=json.dumps({"version": version}),
            timestamp=_utcnow(),
        )
        db.add(audit)
        db.commit()
        return True, f"Release {version} paused."

    def revoke_release(self, db: Session, version: str, reason: str = "", admin_id: str = "SYSTEM") -> Tuple[bool, str]:
        """Revokes a release due to critical defect or vulnerability."""
        rel = db.query(UpdateReleaseDB).filter(UpdateReleaseDB.version == version).first()
        if not rel:
            return False, f"Release {version} not found."
        rel.status = ReleaseStatus.REVOKED.value
        audit = AuditLogDB(
            id=f"aud_rel_r_{hashlib.md5(f'{version}{_utcnow()}'.encode()).hexdigest()[:12]}",
            actor_id=admin_id,
            action="RELEASE_REVOKED",
            details_json=json.dumps({"version": version, "reason": reason}),
            timestamp=_utcnow(),
        )
        db.add(audit)
        db.commit()
        return True, f"Release {version} revoked."

    def set_rollout_percentage(
        self, db: Session, version: str, percentage: int, admin_id: str = "SYSTEM"
    ) -> Tuple[bool, str]:
        """Adjusts rollout percentage (0-100%)."""
        rel = db.query(UpdateReleaseDB).filter(UpdateReleaseDB.version == version).first()
        if not rel:
            return False, f"Release {version} not found."
        pct = max(0, min(100, percentage))
        rel.rollout_percentage = pct
        audit = AuditLogDB(
            id=f"aud_rel_pct_{hashlib.md5(f'{version}{_utcnow()}'.encode()).hexdigest()[:12]}",
            actor_id=admin_id,
            action="ROLLOUT_CHANGED",
            details_json=json.dumps({"version": version, "rollout_percentage": pct}),
            timestamp=_utcnow(),
        )
        db.add(audit)
        db.commit()
        return True, f"Release {version} rollout set to {pct}%."

    def record_telemetry(
        self,
        db: Session,
        event_type: str,
        client_version: str,
        target_version: str,
        channel: str = "STABLE",
        device_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Records anonymous update telemetry event."""
        dev_hash = hashlib.sha256(device_id.encode("utf-8")).hexdigest()[:16] if device_id else None
        event = UpdateTelemetryDB(
            id=f"tel_{hashlib.md5(f'{event_type}{_utcnow()}'.encode()).hexdigest()[:16]}",
            event_type=event_type,
            client_version=client_version,
            target_version=target_version,
            channel=channel.upper(),
            device_id_hash=dev_hash,
            details_json=json.dumps(details or {}),
            timestamp=_utcnow(),
        )
        db.add(event)
        db.commit()
        return True
