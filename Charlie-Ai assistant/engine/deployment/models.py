"""
JARVIS Phase 14: Deployment Platform Models
Defines core data structures, enums, and manifests for production deployment,
runtime management, auto-update, installer, and user onboarding.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class EnvironmentType(str, Enum):
    DEVELOPMENT = "DEVELOPMENT"
    TEST = "TEST"
    STAGING = "STAGING"
    PRODUCTION = "PRODUCTION"


class ReleaseChannel(str, Enum):
    STABLE = "STABLE"
    BETA = "BETA"
    INTERNAL = "INTERNAL"
    DEV = "DEV"
    CANARY = "CANARY"


class InstallMode(str, Enum):
    PER_USER = "PER_USER"
    PER_MACHINE = "PER_MACHINE"


class UpdatePolicy(str, Enum):
    AUTO_SECURITY = "AUTO_SECURITY"
    AUTO_FULL = "AUTO_FULL"
    NOTIFY = "NOTIFY"
    MANUAL = "MANUAL"


class AppHealthState(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    SAFE_MODE = "SAFE_MODE"


class UpdateStatus(str, Enum):
    IDLE = "IDLE"
    CHECKING = "CHECKING"
    AVAILABLE = "AVAILABLE"
    DOWNLOADING = "DOWNLOADING"
    VERIFYING = "VERIFYING"
    READY_TO_INSTALL = "READY_TO_INSTALL"
    INSTALLING = "INSTALLING"
    VALIDATING = "VALIDATING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class OnboardingStep(str, Enum):
    WELCOME = "WELCOME"
    PRIVACY = "PRIVACY"
    AI_PROVIDER = "AI_PROVIDER"
    LOCAL_AI = "LOCAL_AI"
    VOICE = "VOICE"
    COMPUTER_CONTROL = "COMPUTER_CONTROL"
    ACCOUNTS = "ACCOUNTS"
    STARTUP = "STARTUP"
    BACKUP = "BACKUP"
    COMPLETE = "COMPLETE"


class TelemetryLevel(str, Enum):
    OFF = "OFF"
    CRASH_ONLY = "CRASH_ONLY"
    ANONYMOUS_METRICS = "ANONYMOUS_METRICS"
    FULL = "FULL"


@dataclass
class BuildInfo:
    app_version: str
    build_number: int
    git_commit: str = "unknown"
    build_date: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    schema_version: int = 1
    protocol_version: str = "1.0.0"
    plugin_sdk_version: str = "1.0.0"
    environment: EnvironmentType = EnvironmentType.PRODUCTION


@dataclass
class EnvironmentCheckResult:
    os_name: str
    os_version: str
    architecture: str
    ram_gb: float
    disk_free_gb: float
    has_microphone: bool = True
    has_gpu: bool = False
    python_version: str = ""
    is_supported: bool = True
    blocking_issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class OnboardingProfile:
    completed_steps: List[str] = field(default_factory=list)
    skipped_steps: List[str] = field(default_factory=list)
    privacy_mode: str = "HYBRID"
    ai_provider: str = "LOCAL"
    voice_enabled: bool = True
    backup_dir: str = ""
    start_with_windows: bool = False
    first_task_verified: bool = False
    is_finished: bool = False


@dataclass
class ReleaseManifest:
    version: str
    build: int
    channel: ReleaseChannel
    download_url: str
    size_bytes: int
    checksum_sha256: str
    signature: str
    min_supported_version: str = "1.0.0"
    minimum_os_version: str = "10.0"
    release_notes: str = ""
    release_date: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    mandatory_update: bool = False
    security_update: bool = False
    rollback_supported: bool = True
    database_schema_version: int = 1
    requires_migration: bool = False


@dataclass
class CrashReport:
    report_id: str
    timestamp: str
    component: str
    error_type: str
    error_message: str
    stack_trace: str
    build_info: Dict[str, Any]
    recovery_state: str = "SAFE"
    is_safe_mode_triggered: bool = False


@dataclass
class DiagnosticBundle:
    bundle_id: str
    created_at: str
    build_info: Dict[str, Any]
    health_summary: Dict[str, Any]
    service_status: Dict[str, Any]
    redacted_logs: List[str] = field(default_factory=list)
    active_channel: str = "STABLE"


@dataclass
class ServiceConfig:
    port: int = 3008
    ipc_pipe_name: str = "JARVIS_IPC_PIPE"
    auth_token: str = ""
    log_level: str = "INFO"
    data_dir: str = ""
