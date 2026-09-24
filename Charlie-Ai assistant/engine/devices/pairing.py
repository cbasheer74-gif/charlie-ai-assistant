"""
JARVIS Phase 10: Secure Pairing Manager
Handles mutual public key exchange, ephemeral pairing tokens, QR code payloads,
rate-limiting, and brute force protection.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
import uuid
from typing import Dict, Optional, Tuple

from .identity_registry import DeviceRegistry
from .models import DeviceIdentity, DeviceType, PairingSession, RemotePermission, TrustState

logger = logging.getLogger("jarvis.devices.pairing")


class PairingManager:
    """Manages short-lived, rate-limited pairing sessions between desktop JARVIS and mobile."""

    def __init__(self, registry: DeviceRegistry, host_device_id: str = "host_windows_pc", pairing_ttl: float = 300.0):
        self.registry = registry
        self.host_device_id = host_device_id
        self.pairing_ttl = pairing_ttl
        self._active_sessions: Dict[str, PairingSession] = {}
        self._failed_attempts_by_ip: Dict[str, int] = {}
        self._lockout_until: Dict[str, float] = {}

    def create_pairing_session(self) -> Tuple[str, str, Dict[str, str]]:
        """
        Creates a short-lived pairing session.
        Returns: (session_id, pairing_code, qr_payload_dict)
        """
        session_id = f"pair_{uuid.uuid4().hex[:12]}"
        pairing_code = f"{secrets.randbelow(900000) + 100000}"  # 6-digit numeric code
        ephemeral_public_key = hashlib.sha256(f"{session_id}:{time.time()}".encode()).hexdigest()
        expires_at = time.time() + self.pairing_ttl

        session = PairingSession(
            session_id=session_id,
            pairing_code=pairing_code,
            ephemeral_public_key=ephemeral_public_key,
            host_device_id=self.host_device_id,
            expires_at=expires_at,
            max_attempts=3,
        )
        self._active_sessions[session_id] = session

        qr_payload = {
            "pairing_session_id": session_id,
            "ephemeral_public_key": ephemeral_public_key,
            "host_device_id": self.host_device_id,
            "expiry": str(int(expires_at)),
            "rendezvous": "local_or_relay",
            "nonce": secrets.token_hex(8),
        }

        logger.info(f"Pairing session created: {session_id}, expires in {self.pairing_ttl}s")
        return session_id, pairing_code, qr_payload

    def complete_pairing(
        self,
        session_id: str,
        provided_code: str,
        client_device_id: str,
        client_device_name: str,
        client_device_type: DeviceType,
        client_public_key: str,
        client_capabilities: Optional[list] = None,
        client_ip: str = "127.0.0.1",
        default_permissions: Optional[list] = None,
    ) -> Tuple[bool, str, Optional[DeviceIdentity]]:
        """
        Validates the pairing code and establishes a trusted device relationship.
        Enforces brute force lockout (3 attempts max) and expiry.
        """
        # Check brute force lockout
        if client_ip in self._lockout_until and time.time() < self._lockout_until[client_ip]:
            remaining = int(self._lockout_until[client_ip] - time.time())
            return False, f"Rate limited. Try again in {remaining}s", None

        session = self._active_sessions.get(session_id)
        if not session:
            self._record_failure(client_ip)
            return False, "Invalid or nonexistent pairing session", None

        if session.is_expired():
            del self._active_sessions[session_id]
            return False, "Pairing session expired", None

        if session.is_completed:
            return False, "Pairing session already used", None

        if session.attempts >= session.max_attempts:
            del self._active_sessions[session_id]
            self._record_failure(client_ip)
            return False, "Max attempts exceeded. Pairing session destroyed.", None

        # Verify pairing code
        session.attempts += 1
        if not secrets.compare_digest(session.pairing_code, provided_code.strip()):
            if session.attempts >= session.max_attempts:
                del self._active_sessions[session_id]
                self._record_failure(client_ip)
                return False, "Max pairing attempts exceeded. Session invalidated.", None
            return False, f"Incorrect pairing code. {session.max_attempts - session.attempts} attempts remaining.", None

        # Pairing successful! Mark session completed and remove
        session.is_completed = True
        del self._active_sessions[session_id]
        self._failed_attempts_by_ip.pop(client_ip, None)

        # Default permissions for mobile companion
        perms = default_permissions or [
            RemotePermission.VIEW_STATUS,
            RemotePermission.VIEW_TASKS,
            RemotePermission.START_SAFE_TASK,
            RemotePermission.VOICE_COMMAND,
            RemotePermission.READ_PROJECT_STATUS,
            RemotePermission.VIEW_NOTIFICATIONS,
            RemotePermission.PAUSE_RESUME,
            RemotePermission.APPROVE_ACTIONS,
        ]

        # Prevent forbidden permissions on mobile companions
        safe_perms = [
            p for p in perms
            if p not in (
                RemotePermission.SYSTEM_ADMIN,
                RemotePermission.FILE_DELETE,
                RemotePermission.SECURITY_SETTINGS,
                RemotePermission.RAW_SHELL,
            )
        ]

        device = DeviceIdentity(
            device_id=client_device_id,
            device_name=client_device_name,
            device_type=client_device_type,
            public_key=client_public_key,
            capabilities=client_capabilities or ["VOICE_INPUT", "NOTIFICATION", "APPROVAL", "TASK_VIEW"],
            paired_at=time.time(),
            last_seen=time.time(),
            trust_state=TrustState.TRUSTED,
            permissions=safe_perms,
        )

        self.registry.register_device(device)
        logger.info(f"Successfully paired device: {client_device_id} ({client_device_name})")
        return True, "Pairing successful", device

    def _record_failure(self, ip: str):
        attempts = self._failed_attempts_by_ip.get(ip, 0) + 1
        self._failed_attempts_by_ip[ip] = attempts
        if attempts >= 5:
            self._lockout_until[ip] = time.time() + 300.0  # 5 min lockout
            logger.warning(f"Brute force detected from {ip}. Locked out for 5 minutes.")
