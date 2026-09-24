"""
JARVIS Phase 10: Multi-Device Package
Exposes device orchestration, identity, pairing, gateway, presence, sync, and handoff modules.
"""

from .core import DeviceOrchestrator
from .gateway import RemoteCommandGateway, RemoteCommandRouter
from .handoff_files import SecureFileTransferManager, TaskHandoffManager
from .identity_registry import DeviceRegistry, DeviceRevocationManager
from .models import (
    DeviceIdentity,
    DeviceType,
    MessageType,
    NotificationCategory,
    NotificationPayload,
    PairingSession,
    PresenceStatus,
    RemoteCommandEnvelope,
    RemotePermission,
    RemoteSession,
    SyncRecord,
    SyncScope,
    TaskHandoffPayload,
    TrustState,
)
from .notifications import NotificationManager
from .pairing import PairingManager
from .presence_session import MobileSessionManager, OfflineQueueManager, PresenceManager
from .sync_engine import ConflictResolver, SyncEngine

__all__ = [
    "DeviceOrchestrator",
    "DeviceRegistry",
    "DeviceRevocationManager",
    "PairingManager",
    "PresenceManager",
    "MobileSessionManager",
    "OfflineQueueManager",
    "RemoteCommandGateway",
    "RemoteCommandRouter",
    "SyncEngine",
    "ConflictResolver",
    "TaskHandoffManager",
    "SecureFileTransferManager",
    "NotificationManager",
    "DeviceIdentity",
    "DeviceType",
    "TrustState",
    "PresenceStatus",
    "RemotePermission",
    "MessageType",
    "SyncScope",
    "NotificationCategory",
    "PairingSession",
    "RemoteSession",
    "RemoteCommandEnvelope",
    "NotificationPayload",
    "SyncRecord",
    "TaskHandoffPayload",
]
