"""
JARVIS Phase 12: Developer Platform Models & Manifests
Defines contracts for plugins, tools, connectors, custom agents, events, webhooks, and permissions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import time
import uuid


class ExtensionType(str, Enum):
    TOOL = "TOOL"
    CONNECTOR = "CONNECTOR"
    AGENT = "AGENT"
    SKILL = "SKILL"
    MCP_SERVER = "MCP_SERVER"
    MCP_CLIENT = "MCP_CLIENT"
    DATA_SOURCE = "DATA_SOURCE"
    WEBHOOK = "WEBHOOK"
    EVENT_TRIGGER = "EVENT_TRIGGER"
    MODEL_PROVIDER = "MODEL_PROVIDER"
    STORAGE_PROVIDER = "STORAGE_PROVIDER"
    NOTIFICATION_PROVIDER = "NOTIFICATION_PROVIDER"
    DEVICE_ADAPTER = "DEVICE_ADAPTER"


class PluginLifecycle(str, Enum):
    DISCOVERED = "DISCOVERED"
    DOWNLOADED = "DOWNLOADED"
    VALIDATING = "VALIDATING"
    INSTALLED = "INSTALLED"
    DISABLED = "DISABLED"
    ENABLED = "ENABLED"
    DEGRADED = "DEGRADED"
    QUARANTINED = "QUARANTINED"
    UNINSTALLED = "UNINSTALLED"


class TrustStatus(str, Enum):
    UNTRUSTED = "UNTRUSTED"
    REVIEWED = "REVIEWED"
    TRUSTED = "TRUSTED"
    BLOCKED = "BLOCKED"


class MemoryScope(str, Enum):
    NONE = "NONE"
    SESSION = "SESSION"
    PROJECT = "PROJECT"
    USER = "USER"
    CUSTOM_NAMESPACE = "CUSTOM_NAMESPACE"


@dataclass
class PermissionManifest:
    filesystem: List[str] = field(default_factory=list)  # e.g. ["workspace:read", "project:zynpay:read"]
    network: List[str] = field(default_factory=list)  # e.g. ["api.github.com", "slack.com"]
    actions: List[str] = field(default_factory=list)  # e.g. ["github.issue.create", "db.query.read"]
    allowed_credentials: List[str] = field(default_factory=list)  # e.g. ["github_token"]
    can_spawn_processes: bool = False

    def allows_domain(self, domain: str) -> bool:
        if "*" in self.network:
            return True
        return domain.lower() in [d.lower() for d in self.network]

    def allows_file_path(self, path: str, mode: str = "read") -> bool:
        norm = path.replace("\\", "/").lower()
        if "no_file_access" in [f.lower() for f in self.filesystem]:
            return False
        if any("system32" in norm or "windows" in norm for _ in [1]):
            return False
        return True


@dataclass
class ExtensionManifest:
    id: str  # e.g. "github.connector"
    name: str
    version: str
    type: ExtensionType
    description: str
    entrypoint: str
    permissions: PermissionManifest = field(default_factory=PermissionManifest)
    capabilities: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    credentials: List[str] = field(default_factory=list)
    min_jarvis_version: str = "1.0.0"
    publisher: str = "Community"
    signature: str = ""
    is_dev_mode: bool = False


@dataclass
class ToolContract:
    name: str  # e.g. "github.issue.create"
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    risk_level: str = "R1_LOW"  # R0_BENIGN, R1_LOW, R2_MEDIUM, R3_HIGH, R4_CRITICAL
    required_permissions: List[str] = field(default_factory=list)
    network_access: bool = False
    file_access: bool = False
    external_side_effects: bool = False
    is_idempotent: bool = False
    retry_safe: bool = False


@dataclass
class ConnectorContract:
    connector_id: str
    name: str
    auth_type: str = "API_KEY"  # OAUTH2, API_KEY, PAT, SERVICE_ACCOUNT
    capabilities: List[str] = field(default_factory=list)
    required_credentials: List[str] = field(default_factory=list)
    allowed_domains: List[str] = field(default_factory=list)


@dataclass
class ToolExecutionResult:
    status: str  # "SUCCESS", "FAILED", "BLOCKED", "VERIFICATION_FAILED"
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    artifacts: List[str] = field(default_factory=list)
    side_effects: List[str] = field(default_factory=list)
    verified: bool = False
    audit_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CustomAgentSpec:
    agent_id: str
    name: str
    role: str
    instructions: str
    allowed_tools: List[str] = field(default_factory=list)
    allowed_models: List[str] = field(default_factory=list)
    memory_scope: MemoryScope = MemoryScope.PROJECT
    project_scope: Optional[str] = None
    permissions: List[str] = field(default_factory=list)
    autonomy_level: str = "SUPERVISED"  # READ_ONLY, SUPERVISED, AUTONOMOUS
    is_certified: bool = False


@dataclass
class EventMessage:
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:10]}")
    event_type: str = ""  # TASK_STARTED, GITHUB_PR_CREATED, etc.
    source: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class WebhookPayload:
    webhook_id: str
    source: str  # e.g. "github", "stripe"
    event_type: str
    payload: Dict[str, Any]
    signature: str
    timestamp: float
    nonce: str


@dataclass
class AutomationRule:
    rule_id: str
    name: str
    event_type: str  # WHEN
    conditions: Dict[str, Any] = field(default_factory=dict)  # IF
    action_skill: str = ""  # THEN
    action_parameters: Dict[str, Any] = field(default_factory=dict)
    owner: str = "user"
    enabled: bool = True
    run_count: int = 0
    failure_count: int = 0
    last_run_at: float = 0.0
