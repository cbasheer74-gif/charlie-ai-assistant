"""
JARVIS Phase 10: Device Orchestrator
Master coordinator unifying multi-device identity, pairing, gateway routing,
presence, selective sync, handoff, file transfers, and remote notifications.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from .gateway import RemoteCommandGateway, RemoteCommandRouter
from .handoff_files import SecureFileTransferManager, TaskHandoffManager
from .identity_registry import DeviceRegistry, DeviceRevocationManager
from .models import DeviceIdentity, DeviceType, NotificationCategory, RemoteCommandEnvelope, RemotePermission, TrustState
from .notifications import NotificationManager
from .pairing import PairingManager
from .presence_session import MobileSessionManager, OfflineQueueManager, PresenceManager
from .sync_engine import ConflictResolver, SyncEngine

logger = logging.getLogger("jarvis.devices.core")


class DeviceOrchestrator:
    """Central manager for Phase 10 Multi-Device system."""

    def __init__(self, db_path: str = "devices.db", audit_engine: Optional[Any] = None):
        self.audit_engine = audit_engine
        self.registry = DeviceRegistry(db_path=db_path)
        self.session_manager = MobileSessionManager(registry=self.registry)
        self.revocation_manager = DeviceRevocationManager(
            registry=self.registry,
            session_manager=self.session_manager,
            audit_engine=self.audit_engine,
        )
        self.pairing_manager = PairingManager(registry=self.registry, host_device_id="host_windows_pc")
        self.presence_manager = PresenceManager(registry=self.registry)
        self.offline_queue = OfflineQueueManager()
        self.gateway = RemoteCommandGateway(
            registry=self.registry,
            session_manager=self.session_manager,
            audit_engine=self.audit_engine,
        )
        self.router = RemoteCommandRouter()
        self.sync_engine = SyncEngine()
        self.conflict_resolver = ConflictResolver()
        self.handoff_manager = TaskHandoffManager()
        self.file_transfer = SecureFileTransferManager(audit_engine=self.audit_engine)
        self.notifications = NotificationManager(audit_engine=self.audit_engine)

        logger.info("DeviceOrchestrator initialized.")

    def handle_remote_envelope(
        self, envelope: RemoteCommandEnvelope, raw_dict: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Receives an envelope from a companion, checks PC presence, validates via gateway,
        and routes or enqueues if PC is offline.
        """
        # 1. Gateway Security Check
        valid, msg, validation_data = self.gateway.process_envelope(envelope, raw_payload_dict=raw_dict)
        if not valid:
            return {
                "success": False,
                "command_id": envelope.command_id,
                "error": msg,
                "details": validation_data,
            }

        # 2. Presence Check
        pc_status = self.presence_manager.get_pc_status()
        if pc_status.value in ("OFFLINE", "SLEEPING"):
            # Attempt to enqueue if eligible
            enq_ok, enq_msg = self.offline_queue.enqueue_command(envelope)
            return {
                "success": enq_ok,
                "command_id": envelope.command_id,
                "status": "QUEUED_OFFLINE" if enq_ok else "REJECTED_OFFLINE",
                "message": enq_msg,
                "pc_status": pc_status.value,
            }

        # 3. Router Execution
        result = self.router.dispatch(envelope)
        return result
