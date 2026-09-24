"""
JARVIS Phase 15: Launch Operations Platform Models
Defines core data structures, enums, and records for UAT, pilot programs,
bug triage, incident management, launch readiness, and v1.0 go-live.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class FreezeState(str, Enum):
    OPEN_DEVELOPMENT = "OPEN_DEVELOPMENT"
    FEATURE_FREEZE = "FEATURE_FREEZE"
    CODE_FREEZE = "CODE_FREEZE"
    RELEASE_CANDIDATE = "RELEASE_CANDIDATE"
    GO_LIVE = "GO_LIVE"


class UATStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


class UATPersona(str, Enum):
    DEVELOPER = "DEVELOPER"
    GENERAL_USER = "GENERAL_USER"
    CONTENT_CREATOR = "CONTENT_CREATOR"
    OFFICE_USER = "OFFICE_USER"
    POWER_USER = "POWER_USER"
    BEGINNER = "BEGINNER"
    VOICE = "VOICE"


class PilotStage(str, Enum):
    DOGFOOD = "DOGFOOD"
    INTERNAL_ALPHA = "INTERNAL_ALPHA"
    CLOSED_BETA = "CLOSED_BETA"
    RELEASE_CANDIDATE_PILOT = "RELEASE_CANDIDATE_PILOT"


class IssueSeverity(str, Enum):
    P0_CRITICAL = "P0_CRITICAL"
    P1_HIGH = "P1_HIGH"
    P2_MEDIUM = "P2_MEDIUM"
    P3_LOW = "P3_LOW"


class IssueStatus(str, Enum):
    NEW = "NEW"
    TRIAGED = "TRIAGED"
    REPRODUCED = "REPRODUCED"
    IN_PROGRESS = "IN_PROGRESS"
    FIXED = "FIXED"
    VERIFIED = "VERIFIED"
    CLOSED = "CLOSED"
    WONT_FIX = "WONT_FIX"
    DEFERRED = "DEFERRED"


class IncidentSeverity(str, Enum):
    SEV0_CATASTROPHIC = "SEV0_CATASTROPHIC"
    SEV1_MAJOR_OUTAGE = "SEV1_MAJOR_OUTAGE"
    SEV2_FEATURE_DEGRADED = "SEV2_FEATURE_DEGRADED"
    SEV3_MINOR_ISSUE = "SEV3_MINOR_ISSUE"


class IncidentLifecycle(str, Enum):
    DETECTED = "DETECTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    CONTAINED = "CONTAINED"
    MITIGATING = "MITIGATING"
    RESOLVED = "RESOLVED"
    MONITORING = "MONITORING"
    POSTMORTEM = "POSTMORTEM"


class GoNoGoDecision(str, Enum):
    GO = "GO"
    CONDITIONAL_GO = "CONDITIONAL_GO"
    NO_GO = "NO_GO"


class RolloutStage(str, Enum):
    STAGE_1_INTERNAL = "STAGE_1_INTERNAL"
    STAGE_2_PILOT = "STAGE_2_PILOT"
    STAGE_3_CONTROLLED = "STAGE_3_CONTROLLED"
    STAGE_4_STABLE = "STAGE_4_STABLE"


@dataclass
class UATCase:
    uat_id: str
    user_persona: UATPersona
    scenario_name: str
    preconditions: List[str]
    steps: List[str]
    expected_behavior: str
    actual_behavior: str = ""
    status: UATStatus = UATStatus.NOT_STARTED
    severity: Optional[IssueSeverity] = None
    feedback: str = ""
    evidence_ref: str = ""
    environment: str = "Windows 10 x64"
    build_id: str = "v1.0.0-rc1"


@dataclass
class PilotRegistration:
    device_id: str
    cohort: PilotStage
    os_info: str
    ram_gb: float
    channel: str = "BETA"
    registered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_health_state: str = "HEALTHY"
    consent_confirmed: bool = True


@dataclass
class FeedbackItem:
    feedback_id: str
    category: str
    description: str
    timestamp: str
    component: Optional[str] = None
    rating: int = 5
    build_id: str = "v1.0.0-rc1"


@dataclass
class IssueRecord:
    issue_id: str
    title: str
    component: str
    severity: IssueSeverity
    status: IssueStatus = IssueStatus.NEW
    reproduction_steps: str = ""
    reproduced: bool = False
    evidence_ref: str = ""
    assigned_to: str = "unassigned"
    fix_version: str = "v1.0.0"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class IncidentTimelineEntry:
    timestamp: str
    action: str
    actor: str
    notes: str = ""


@dataclass
class IncidentRecord:
    incident_id: str
    title: str
    severity: IncidentSeverity
    lifecycle: IncidentLifecycle = IncidentLifecycle.DETECTED
    affected_subsystem: str = "core"
    timeline: List[IncidentTimelineEntry] = field(default_factory=list)
    mitigation_notes: str = ""
    contained_at: Optional[str] = None
    resolved_at: Optional[str] = None


@dataclass
class PostmortemReport:
    incident_id: str
    root_cause: str
    impact_summary: str
    what_worked: List[str]
    what_failed: List[str]
    corrective_actions: List[str]
    new_regression_tests: List[str]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class KnownIssue:
    issue_id: str
    title: str
    impact: str
    workaround: str
    target_fix_version: str = "1.0.1"


@dataclass
class ReleaseReadinessChecklist:
    scope_locked: bool = True
    feature_freeze: bool = True
    code_freeze: bool = True
    phase13_certified: bool = True
    installer_signed: bool = True
    backup_restore_tested: bool = True
    emergency_stop_tested: bool = True
    zero_open_p0: bool = True
    accepted_p1_count: int = 0
    runbooks_ready: bool = True
    release_notes_ready: bool = True


@dataclass
class GoNoGoReport:
    decision: GoNoGoDecision
    checklist_score: str
    open_blockers: List[str]
    accepted_limitations: List[str]
    release_candidate_build: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class RolloutCohort:
    stage: RolloutStage
    percentage: int
    active: bool = False
    started_at: Optional[str] = None
    failure_rate_percent: float = 0.0
    auto_paused: bool = False
