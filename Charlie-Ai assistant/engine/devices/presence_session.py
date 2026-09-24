"""
JARVIS Phase 10: Presence, Session & Offline Queue Management
Tracks device heartbeats, manages mobile sessions, and queues safe commands with TTL when offline.
"""

from __future__ import annotations

import logging
import secrets
import time
import uuid
from typing import Dict, List, Optional, Tuple

from .identity_registry import DeviceRegistry
from .models import DeviceIdentity, PresenceStatus, RemoteCommandEnvelope, RemoteSession, TrustState

logger = logging.getLogger("jarvis.devices.presence")


class MobileSessionManager:
    """Manages active sessions from paired mobile devices."""

    def __init__(self, registry: DeviceRegistry, session_ttl: float = 86400.0, elevated_ttl: float = 900.0):
        self.registry = registry
        self.session_ttl = session_ttl
        self.elevated_ttl = elevated_ttl
        self._sessions: Dict[str, RemoteSession] = {}

    def create_session(self, device_id: str, auth_level: str = "STANDARD") -> Optional[RemoteSession]:
        """Create a new session for a trusted device."""
        device = self.registry.get_device(device_id)
        if not device or device.trust_state != TrustState.TRUSTED or device.is_revoked:
            logger.warning(f"Rejected session creation for untrusted device {device_id}")
            return None

        ttl = self.elevated_ttl if auth_level == "ELEVATED" else self.session_ttl
        session_id = f"sess_{secrets.token_hex(16)}"
        session = RemoteSession(
            session_id=session_id,
            device_id=device_id,
            auth_level=auth_level,
            created_at=time.time(),
            last_active=time.time(),
            expires_at=time.time() + ttl,
            is_locked=False,
        )
        self._sessions[session_id] = session
        return session

    def validate_session(self, session_id: str) -> Tuple[bool, Optional[RemoteSession]]:
        """Validate if a session is active and not expired."""
        session = self._sessions.get(session_id)
        if not session:
            return False, None

        if not session.is_valid():
            del self._sessions[session_id]
            return False, None

        # Check if underlying device is still trusted
        device = self.registry.get_device(session.device_id)
        if not device or device.trust_state != TrustState.TRUSTED or device.is_revoked:
            del self._sessions[session_id]
            return False, None

        session.last_active = time.time()
        return True, session

    def lock_session(self, session_id: str):
        """Lock session on mobile background or screen lock."""
        if session_id in self._sessions:
            self._sessions[session_id].is_locked = True

    def unlock_session(self, session_id: str):
        """Unlock session after biometric or PIN authentication."""
        if session_id in self._sessions:
            self._sessions[session_id].is_locked = False
            self._sessions[session_id].last_active = time.time()

    def invalidate_device_sessions(self, device_id: str):
        """Invalidate all active sessions for a device (e.g., on revocation)."""
        to_delete = [s_id for s_id, s in self._sessions.items() if s.device_id == device_id]
        for s_id in to_delete:
            del self._sessions[s_id]
        logger.info(f"Invalidated {len(to_delete)} sessions for device {device_id}")


class PresenceManager:
    """Monitors heartbeat, online/offline/sleeping status of Windows PC and companions."""

    def __init__(self, registry: DeviceRegistry, heartbeat_timeout: float = 60.0):
        self.registry = registry
        self.heartbeat_timeout = heartbeat_timeout
        self.pc_status = PresenceStatus.ONLINE
        self._last_pc_heartbeat = time.time()

    def record_pc_heartbeat(self, status: PresenceStatus = PresenceStatus.ONLINE):
        self.pc_status = status
        self._last_pc_heartbeat = time.time()

    def set_pc_status(self, status: PresenceStatus):
        self.pc_status = status

    def get_pc_status(self) -> PresenceStatus:
        if self.pc_status == PresenceStatus.SLEEPING:
            return PresenceStatus.SLEEPING
        if time.time() - self._last_pc_heartbeat > self.heartbeat_timeout:
            return PresenceStatus.OFFLINE
        return self.pc_status

    def record_device_heartbeat(self, device_id: str):
        self.registry.update_last_seen(device_id)

    def get_device_status(self, device_id: str) -> PresenceStatus:
        device = self.registry.get_device(device_id)
        if not device or device.is_revoked:
            return PresenceStatus.UNKNOWN
        if time.time() - device.last_seen > self.heartbeat_timeout:
            return PresenceStatus.OFFLINE
        return PresenceStatus.ONLINE


class OfflineQueueManager:
    """
    Stores safe commands when PC is offline.
    Rejects high-risk actions (shutdown, delete, email, security changes) from being queued.
    Purges commands past TTL.
    """

    FORBIDDEN_OFFLINE_INTENTS = {
        "PC_SHUTDOWN",
        "PC_RESTART",
        "FILE_DELETE",
        "SEND_EMAIL",
        "PUBLISH",
        "SECURITY_CHANGE",
        "LOCKDOWN",
    }

    def __init__(self, max_queue_size: int = 50):
        self.max_queue_size = max_queue_size
        self._queue: List[RemoteCommandEnvelope] = []

    def enqueue_command(self, cmd: RemoteCommandEnvelope) -> Tuple[bool, str]:
        """Enqueue a command for later execution if eligible."""
        if cmd.intent in self.FORBIDDEN_OFFLINE_INTENTS:
            return False, f"High-risk intent '{cmd.intent}' cannot be queued offline. Real-time confirmation required."

        if cmd.is_expired():
            return False, "Command has already expired."

        if len(self._queue) >= self.max_queue_size:
            self.purge_expired()
            if len(self._queue) >= self.max_queue_size:
                return False, "Offline command queue is full."

        self._queue.append(cmd)
        logger.info(f"Enqueued offline command {cmd.command_id} ({cmd.intent}), TTL: {cmd.ttl_seconds}s")
        return True, "Command queued for PC reconnect."

    def drain_executable_commands(self) -> List[RemoteCommandEnvelope]:
        """Drains non-expired commands when PC comes back online."""
        now = time.time()
        executable = []
        for cmd in self._queue:
            if not cmd.is_expired():
                executable.append(cmd)
        self._queue.clear()
        return executable

    def purge_expired(self) -> int:
        initial = len(self._queue)
        self._queue = [cmd for cmd in self._queue if not cmd.is_expired()]
        purged = initial - len(self._queue)
        if purged > 0:
            logger.info(f"Purged {purged} expired commands from offline queue.")
        return purged

    def get_queued_count(self) -> int:
        return len(self._queue)
