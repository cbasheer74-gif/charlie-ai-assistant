"""engine/security/models.py — Data Models, Enums, and Security Tokens for JARVIS Phase 9."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class RiskLevel(str, Enum):
    R0_READ_ONLY = "R0_READ_ONLY"
    R1_SAFE_WRITE = "R1_SAFE_WRITE"
    R2_REVERSIBLE_CHANGE = "R2_REVERSIBLE_CHANGE"
    R3_HIGH_IMPACT = "R3_HIGH_IMPACT"
    R4_CRITICAL = "R4_CRITICAL"


class PolicyVerdict(str, Enum):
    ALLOW = "ALLOW"
    ALLOW_WITH_BACKUP = "ALLOW_WITH_BACKUP"
    ALLOW_WITH_CONFIRMATION = "ALLOW_WITH_CONFIRMATION"
    DENY = "DENY"
    ESCALATE = "ESCALATE"


class InstructionOrigin(str, Enum):
    SYSTEM = "SYSTEM"
    USER = "USER"
    TRUSTED_INTERNAL = "TRUSTED_INTERNAL"
    TOOL_RESULT = "TOOL_RESULT"
    EMAIL = "EMAIL"
    WEB = "WEB"
    DOCUMENT = "DOCUMENT"
    PLUGIN = "PLUGIN"
    FILE = "FILE"
    IMPORTED_SKILL = "IMPORTED_SKILL"


class SecuritySeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SecurityEventType(str, Enum):
    BLOCKED_COMMAND = "BLOCKED_COMMAND"
    UNTRUSTED_INSTRUCTION = "UNTRUSTED_INSTRUCTION"
    CREDENTIAL_EXPOSURE_ATTEMPT = "CREDENTIAL_EXPOSURE_ATTEMPT"
    SUSPICIOUS_DOWNLOAD = "SUSPICIOUS_DOWNLOAD"
    PERMISSION_VIOLATION = "PERMISSION_VIOLATION"
    MASS_DELETE_ATTEMPT = "MASS_DELETE_ATTEMPT"
    PLUGIN_POLICY_VIOLATION = "PLUGIN_POLICY_VIOLATION"
    BACKUP_FAILURE = "BACKUP_FAILURE"
    INTEGRITY_FAILURE = "INTEGRITY_FAILURE"
    TAMPER_DETECTED = "TAMPER_DETECTED"


@dataclass
class CapabilityToken:
    id: str
    target_resource: str
    allowed_operations: List[str]  # e.g. ["READ", "WRITE"]
    granted_by: str = "USER"
    expires_at: float = field(default_factory=lambda: time.time() + 300.0)
    revoked: bool = False

    def is_valid(self, operation: str) -> bool:
        if self.revoked:
            return False
        if time.time() > self.expires_at:
            return False
        return operation.upper() in [op.upper() for op in self.allowed_operations]


@dataclass
class SecurityPolicyDecision:
    verdict: PolicyVerdict
    reason: str
    risk_level: RiskLevel
    backup_required: bool = False
    confirmation_required: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditEvent:
    id: str
    prev_hash: str
    timestamp: float
    initiator: str  # USER, AGENT, SYSTEM
    agent_name: str
    tool_name: str
    action: str
    target: str
    risk_level: str
    verdict: str
    details: Dict[str, Any] = field(default_factory=dict)
    event_hash: str = ""


@dataclass
class SecurityEvent:
    id: str
    event_type: SecurityEventType
    severity: SecuritySeverity
    source: str
    description: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BackupRecord:
    id: str
    backup_path: str
    timestamp: float
    backup_type: str  # "FULL", "INCREMENTAL", "CONFIG", "DATABASE"
    size_bytes: int
    content_hash: str
    verified: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DownloadRecord:
    id: str
    url: str
    domain: str
    file_path: str
    file_hash: str
    mime_type: str
    size_bytes: int
    is_trusted_origin: bool
    quarantined: bool = False
    timestamp: float = field(default_factory=time.time)
