"""
JARVIS Phase 10: Device Registry & Revocation Manager
Stores paired device identities, public keys, trust states, and manages instant revocation.
"""

from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
import time
from typing import Dict, List, Optional

from .models import DeviceIdentity, DeviceType, RemotePermission, TrustState

logger = logging.getLogger("jarvis.devices.registry")


class DeviceRegistry:
    """Persistent registry for paired devices."""

    def __init__(self, db_path: str = "devices.db"):
        self.db_path = db_path
        self._init_db()

    @contextlib.contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    device_name TEXT NOT NULL,
                    device_type TEXT NOT NULL,
                    public_key TEXT NOT NULL,
                    capabilities TEXT,
                    paired_at REAL,
                    last_seen REAL,
                    trust_state TEXT,
                    permissions TEXT,
                    app_version TEXT,
                    os_info TEXT,
                    is_revoked INTEGER DEFAULT 0
                )
                """
            )
            conn.commit()

    def register_device(self, device: DeviceIdentity) -> bool:
        """Register or update a paired device."""
        capabilities_json = json.dumps(device.capabilities)
        perms_json = json.dumps([p.value if hasattr(p, 'value') else str(p) for p in device.permissions])
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO devices (
                    device_id, device_name, device_type, public_key,
                    capabilities, paired_at, last_seen, trust_state,
                    permissions, app_version, os_info, is_revoked
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device.device_id,
                    device.device_name,
                    device.device_type.value if hasattr(device.device_type, 'value') else str(device.device_type),
                    device.public_key,
                    capabilities_json,
                    device.paired_at,
                    device.last_seen,
                    device.trust_state.value if hasattr(device.trust_state, 'value') else str(device.trust_state),
                    perms_json,
                    device.app_version,
                    device.os_info,
                    1 if device.is_revoked else 0,
                ),
            )
            conn.commit()
            return True

    def get_device(self, device_id: str) -> Optional[DeviceIdentity]:
        """Retrieve device identity by device_id."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT device_id, device_name, device_type, public_key,
                       capabilities, paired_at, last_seen, trust_state,
                       permissions, app_version, os_info, is_revoked
                FROM devices WHERE device_id = ?
                """,
                (device_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_device(row)

    def list_devices(self, include_revoked: bool = False) -> List[DeviceIdentity]:
        """List all devices in the registry."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if include_revoked:
                cursor.execute("SELECT * FROM devices ORDER BY paired_at DESC")
            else:
                cursor.execute("SELECT * FROM devices WHERE is_revoked = 0 ORDER BY paired_at DESC")
            rows = cursor.fetchall()
            return [self._row_to_device(r) for r in rows]

    def update_last_seen(self, device_id: str, timestamp: Optional[float] = None):
        """Update last_seen timestamp for presence."""
        t = timestamp or time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE devices SET last_seen = ? WHERE device_id = ?", (t, device_id))
            conn.commit()

    def update_permissions(self, device_id: str, permissions: List[RemotePermission]) -> bool:
        """Update permissions granted to a device."""
        perms_json = json.dumps([p.value if hasattr(p, 'value') else str(p) for p in permissions])
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE devices SET permissions = ? WHERE device_id = ?", (perms_json, device_id))
            conn.commit()
            return cursor.rowcount > 0

    def rename_device(self, device_id: str, new_name: str) -> bool:
        """Rename an existing device."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE devices SET device_name = ? WHERE device_id = ?", (new_name, device_id))
            conn.commit()
            return cursor.rowcount > 0

    def set_trust_state(self, device_id: str, trust_state: TrustState) -> bool:
        """Update the trust state of a device."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            state_val = trust_state.value if hasattr(trust_state, 'value') else str(trust_state)
            is_rev = 1 if trust_state == TrustState.REVOKED else 0
            cursor.execute(
                "UPDATE devices SET trust_state = ?, is_revoked = ? WHERE device_id = ?",
                (state_val, is_rev, device_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_device(self, row) -> DeviceIdentity:
        capabilities = json.loads(row[4]) if row[4] else []
        trust_state = TrustState(row[7])
        raw_perms = json.loads(row[8]) if row[8] else []
        permissions = [RemotePermission(p) for p in raw_perms if p in RemotePermission.__members__]
        return DeviceIdentity(
            device_id=row[0],
            device_name=row[1],
            device_type=DeviceType(row[2]),
            public_key=row[3],
            capabilities=capabilities,
            paired_at=row[5] or 0.0,
            last_seen=row[6] or 0.0,
            trust_state=trust_state,
            permissions=permissions,
            app_version=row[9] or "1.0.0",
            os_info=row[10] or "Unknown",
            is_revoked=bool(row[11]),
        )


class DeviceRevocationManager:
    """Manages immediate revocation of devices, session termination, and audit logging."""

    def __init__(self, registry: DeviceRegistry, session_manager: Optional[Any] = None, audit_engine: Optional[Any] = None):
        self.registry = registry
        self.session_manager = session_manager
        self.audit_engine = audit_engine

    def revoke_device(self, device_id: str, reason: str = "User initiated revocation") -> bool:
        """Immediately revoke device, invalidate active sessions, and mark state as REVOKED."""
        device = self.registry.get_device(device_id)
        if not device:
            logger.warning(f"Device {device_id} not found for revocation.")
            return False

        # 1. Update registry state
        self.registry.set_trust_state(device_id, TrustState.REVOKED)

        # 2. Invalidate sessions in session manager
        if self.session_manager:
            self.session_manager.invalidate_device_sessions(device_id)

        # 3. Audit revocation
        if self.audit_engine:
            self.audit_engine.log_security_event(
                event_type="DEVICE_REVOKED",
                severity="HIGH",
                details={"device_id": device_id, "device_name": device.device_name, "reason": reason},
            )
        logger.info(f"Device {device_id} ({device.device_name}) revoked successfully.")
        return True

    def is_revoked(self, device_id: str) -> bool:
        device = self.registry.get_device(device_id)
        if not device:
            return True
        return device.is_revoked or device.trust_state == TrustState.REVOKED
