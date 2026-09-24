"""engine/intelligence/models.py — Data Models and Enums for JARVIS Phase 8 Intelligence Core."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class EntityType(str, Enum):
    USER = "USER"
    PROJECT = "PROJECT"
    PERSON = "PERSON"
    COMPANY = "COMPANY"
    APPLICATION = "APPLICATION"
    DEVICE = "DEVICE"
    FILE = "FILE"
    DOCUMENT = "DOCUMENT"
    EMAIL_THREAD = "EMAIL_THREAD"
    MEETING = "MEETING"
    TASK = "TASK"
    SKILL = "SKILL"
    WORKFLOW = "WORKFLOW"
    ERROR = "ERROR"
    SOLUTION = "SOLUTION"
    COMMAND = "COMMAND"
    TOOL = "TOOL"
    REPOSITORY = "REPOSITORY"
    DATABASE = "DATABASE"
    SERVICE = "SERVICE"
    PORT = "PORT"
    API = "API"
    CONTENT = "CONTENT"
    VIDEO = "VIDEO"
    SPREADSHEET = "SPREADSHEET"
    DEADLINE = "DEADLINE"
    DECISION = "DECISION"
    GOAL = "GOAL"
    ARTIFACT = "ARTIFACT"


class RelationType(str, Enum):
    USES_APPLICATION = "USES_APPLICATION"
    PREFERS_TOOL = "PREFERS_TOOL"
    USES_TECH = "USES_TECH"
    CONTAINS_FILE = "CONTAINS_FILE"
    HAS_TASK = "HAS_TASK"
    HAS_DEADLINE = "HAS_DEADLINE"
    USES_DATABASE = "USES_DATABASE"
    RUNS_ON_PORT = "RUNS_ON_PORT"
    ASSOCIATED_WITH_PERSON = "ASSOCIATED_WITH_PERSON"
    ATTENDS_MEETING = "ATTENDS_MEETING"
    RELATES_TO_PROJECT = "RELATES_TO_PROJECT"
    BELONGS_TO = "BELONGS_TO"
    WORKS_ON = "WORKS_ON"
    DEPENDS_ON_TASK = "DEPENDS_ON_TASK"
    PRODUCES_ARTIFACT = "PRODUCES_ARTIFACT"
    OCCURRED_IN_PROJECT = "OCCURRED_IN_PROJECT"
    SOLVED_BY_SOLUTION = "SOLVED_BY_SOLUTION"
    USES_TOOL = "USES_TOOL"
    APPLIES_TO_PROJECT = "APPLIES_TO_PROJECT"
    USES_RESEARCH = "USES_RESEARCH"
    CREATED_BY_TASK = "CREATED_BY_TASK"
    AFFECTS_PROJECT = "AFFECTS_PROJECT"
    CAUSED_BY = "CAUSED_BY"


class FactCertainty(str, Enum):
    CONFIRMED = "CONFIRMED"
    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    UNCERTAIN = "UNCERTAIN"
    SUPERSEDED = "SUPERSEDED"


class ProposalStatus(str, Enum):
    DETECTED = "DETECTED"
    PROPOSED = "PROPOSED"
    TESTING = "TESTING"
    APPROVED = "APPROVED"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"
    ROLLED_BACK = "ROLLED_BACK"


class InterventionAction(str, Enum):
    IGNORE = "IGNORE"
    LOG = "LOG"
    SURFACE_IN_UI = "SURFACE_IN_UI"
    NOTIFY = "NOTIFY"
    ASK = "ASK"
    PREPARE_DRAFT = "PREPARE_DRAFT"
    EXECUTE_SAFE_SKILL = "EXECUTE_SAFE_SKILL"


@dataclass
class Entity:
    id: str
    type: EntityType
    canonical_name: str
    aliases: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source: str = "user_interaction"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_verified_at: float = field(default_factory=time.time)
    expiry: Optional[float] = None


@dataclass
class Relationship:
    id: str
    source_id: str
    target_id: str
    relation_type: RelationType
    source_provenance: str = "verified_configuration"
    confidence: float = 1.0
    created_at: float = field(default_factory=time.time)
    valid_from: float = field(default_factory=time.time)
    valid_to: Optional[float] = None
    is_active: bool = True
    is_superseded: bool = False
    superseded_by: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Goal:
    id: str
    title: str
    subgoals: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    deadlines: Optional[float] = None
    success_criteria: List[str] = field(default_factory=list)
    priority: int = 1  # 1 = Highest
    project_id: Optional[str] = None
    current_status: str = "IN_PROGRESS"  # PENDING, IN_PROGRESS, COMPLETED, BLOCKED
    blockers: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class Pattern:
    id: str
    pattern_type: str  # BEHAVIOR, WORKFLOW, ERROR, TIME, PREFERENCE
    description: str
    event_count: int = 1
    time_span_sec: float = 0.0
    consistency_score: float = 1.0
    confidence: float = 0.5
    trigger_conditions: Dict[str, Any] = field(default_factory=dict)
    recommended_action: Optional[str] = None
    last_detected_at: float = field(default_factory=time.time)


@dataclass
class ImprovementProposal:
    id: str
    problem: str
    evidence: str
    proposed_change: str
    scope: str  # "INTERNAL_RANKING", "ALIAS_MAP", "WORKFLOW_STEP", "SOURCE_CODE"
    expected_benefit: str
    risk_level: str  # "LOW", "MEDIUM", "HIGH"
    test_plan: str
    rollback_plan: str
    status: ProposalStatus = ProposalStatus.DETECTED
    before_metrics: Dict[str, Any] = field(default_factory=dict)
    after_metrics: Dict[str, Any] = field(default_factory=dict)
    requires_code_modification: bool = False
    created_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None


@dataclass
class ProactiveEvent:
    id: str
    trigger_type: str  # "MEETING_UPCOMING", "DEADLINE_APPROACHING", "BUILD_FAILURES", "EXPORT_COMPLETE"
    importance: float  # 0.0 to 1.0
    urgency: float     # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    risk: float        # 0.0 to 1.0
    target_project: Optional[str] = None
    title: str = ""
    message: str = ""
    suggested_action: Optional[str] = None
    action_taken: InterventionAction = InterventionAction.LOG
    created_at: float = field(default_factory=time.time)
    delivered_at: Optional[float] = None


@dataclass
class ReflectionSummary:
    goal: str
    outcome: str
    what_worked: List[str] = field(default_factory=list)
    what_failed: List[str] = field(default_factory=list)
    user_corrections: List[str] = field(default_factory=list)
    new_knowledge: List[str] = field(default_factory=list)
    reusable_procedure: Optional[str] = None
    possible_improvement: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
