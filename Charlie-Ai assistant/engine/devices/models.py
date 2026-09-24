"""
JARVIS Phase 10: Multi-Device Models & Envelopes
Defines device identities, permissions, trust states, protocol message formats.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import time
import uuid


class DeviceType(str, Enum):
    WINDOWS_DESKTOP = "WINDOWS_DESKTOP"
    WINDOWS_LAPTOP = "WINDOWS_LAPTOP"
    ANDROID = "ANDROID"
    IOS = "IOS"
    WEB_COMPANION = "WEB_COMPANION"
    FUTURE_DEVICE = "FUTURE_DEVICE"


class TrustState(str, Enum):
    UNPAIRED = "UNPAIRED"
    PAIRING = "PAIRING"
    TRUSTED = "TRUSTED"
    LIMITED = "LIMITED"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


class PresenceStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    CONNECTING = "CONNECTING"
    DEGRADED = "DEGRADED"
    SLEEPING = "SLEEPING"
    UNKNOWN = "UNKNOWN"


class RemotePermission(str, Enum):
    VIEW_STATUS = "VIEW_STATUS"
    VIEW_TASKS = "VIEW_TASKS"
    START_SAFE_TASK = "START_SAFE_TASK"
    VOICE_COMMAND = "VOICE_COMMAND"
    READ_PROJECT_STATUS = "READ_PROJECT_STATUS"
    VIEW_NOTIFICATIONS = "VIEW_NOTIFICATIONS"
    APPROVE_ACTIONS = "APPROVE_ACTIONS"
    PAUSE_RESUME = "PAUSE_RESUME"
    FILE_PREVIEW = "FILE_PREVIEW"
    LOCKDOWN = "LOCKDOWN"
    # Prohibited for mobile companions:
    SYSTEM_ADMIN = "SYSTEM_ADMIN"
    FILE_DELETE = "FILE_DELETE"
    SECURITY_SETTINGS = "SECURITY_SETTINGS"
    RAW_SHELL = "RAW_SHELL"


class MessageType(str, Enum):
    HELLO = "HELLO"
    HEARTBEAT = "HEARTBEAT"
    COMMAND_REQUEST = "COMMAND_REQUEST"
    COMMAND_ACCEPTED = "COMMAND_ACCEPTED"
    COMMAND_PROGRESS = "COMMAND_PROGRESS"
    COMMAND_RESULT = "COMMAND_RESULT"
    CONFIRMATION_REQUEST = "CONFIRMATION_REQUEST"
    CONFIRMATION_RESPONSE = "CONFIRMATION_RESPONSE"
    NOTIFICATION = "NOTIFICATION"
    SYNC_UPDATE = "SYNC_UPDATE"
    DEVICE_REVOKED = "DEVICE_REVOKED"
    ERROR = "ERROR"


class SyncScope(str, Enum):
    SETTINGS = "SETTINGS"
    PROJECT_METADATA = "PROJECT_METADATA"
    TASKS = "TASKS"
    MEMORY_SUMMARIES = "MEMORY_SUMMARIES"
    SKILLS = "SKILLS"
    KNOWLEDGE_GRAPH = "KNOWLEDGE_GRAPH"
    NOTIFICATIONS = "NOTIFICATIONS"


class NotificationCategory(str, Enum):
    TASK_COMPLETE = "TASK_COMPLETE"
    TASK_FAILED = "TASK_FAILED"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    SECURITY_ALERT = "SECURITY_ALERT"
    MEETING = "MEETING"
    BACKUP_FAILURE = "BACKUP_FAILURE"
    EXPORT_COMPLETE = "EXPORT_COMPLETE"
    PROJECT_BLOCKED = "PROJECT_BLOCKED"


@dataclass
class DeviceIdentity:
    device_id: str
    device_name: str
    device_type: DeviceType
    public_key: str  # Hex or base64 cryptographic public key
    capabilities: List[str] = field(default_factory=list)
    paired_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    trust_state: TrustState = TrustState.UNPAIRED
    permissions: List[RemotePermission] = field(default_factory=list)
    app_version: str = "1.0.0"
    os_info: str = "Unknown"
    is_revoked: bool = False

    def has_permission(self, perm: RemotePermission) -> bool:
        if self.trust_state != TrustState.TRUSTED:
            return False
        return perm in self.permissions


@dataclass
class PairingSession:
    session_id: str
    pairing_code: str
    ephemeral_public_key: str
    host_device_id: str
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    attempts: int = 0
    max_attempts: int = 3
    is_completed: bool = False

    def is_expired(self) -> bool:
        return time.time() > self.expires_at


@dataclass
class RemoteSession:
    session_id: str
    device_id: str
    auth_level: str = "STANDARD"  # STANDARD, ELEVATED
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    expires_at: float = 0.0
    is_locked: bool = False

    def is_valid(self) -> bool:
        if self.is_locked:
            return False
        return time.time() <= self.expires_at


@dataclass
class RemoteCommandEnvelope:
    command_id: str
    protocol_version: str = "v1"
    device_id: str = ""
    session_id: str = ""
    timestamp: float = field(default_factory=time.time)
    nonce: str = field(default_factory=lambda: uuid.uuid4().hex)
    intent: str = ""  # e.g., "START_PROJECT", "GET_STATUS", "PAUSE_TASK"
    parameters: Dict[str, Any] = field(default_factory=dict)
    ttl_seconds: float = 300.0  # 5 min default
    signature: str = ""
    raw_command_blocked: bool = False

    def is_expired(self) -> bool:
        return time.time() > (self.timestamp + self.ttl_seconds)


@dataclass
class NotificationPayload:
    notification_id: str
    category: NotificationCategory
    title: str
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)
    privacy_safe_text: str = ""
    created_at: float = field(default_factory=time.time)
    requires_approval: bool = False
    action_token: Optional[str] = None
    target_device_id: Optional[str] = None
    delivered: bool = False


@dataclass
class SyncRecord:
    record_id: str
    scope: SyncScope
    version: int
    data: Dict[str, Any]
    origin_device: str
    updated_at: float = field(default_factory=time.time)
    data_hash: str = ""


@dataclass
class TaskHandoffPayload:
    handoff_id: str
    task_id: str
    source_device: str
    target_device: str
    goal: str
    state_snapshot: Dict[str, Any]
    checkpoints: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
