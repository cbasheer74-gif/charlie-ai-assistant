"""engine/skills/models.py — Data Models for Reusable Procedural Skills.

Defines structural representation of learned workflows, variables, triggers,
decision branches, and execution metrics.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class SkillCategory(str, Enum):
    CODING = "CODING"
    VIDEO = "VIDEO"
    YOUTUBE = "YOUTUBE"
    SPREADSHEET = "SPREADSHEET"
    FILES = "FILES"
    BROWSER = "BROWSER"
    RESEARCH = "RESEARCH"
    WINDOWS = "WINDOWS"
    ANTIGRAVITY = "ANTIGRAVITY"
    DOCUMENTS = "DOCUMENTS"
    AUTOMATION = "AUTOMATION"
    PROJECT_MANAGEMENT = "PROJECT_MANAGEMENT"
    CUSTOM = "CUSTOM"


class SkillStatus(str, Enum):
    DRAFT = "DRAFT"          # Initial unverified extraction
    LEARNING = "LEARNING"    # Executed successfully 1-2 times
    STABLE = "STABLE"        # Consistently reliable
    TRUSTED = "TRUSTED"      # High repetition success
    DEGRADED = "DEGRADED"    # Recent tool or UI failures
    DISABLED = "DISABLED"    # Inactive / archived


@dataclass
class SkillVariable:
    name: str
    type: str = "string"  # string, integer, float, file_path, dir_path, boolean, choice
    default: Any = None
    description: str = ""
    required: bool = False
    choices: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SkillTrigger:
    phrase: str
    match_type: str = "semantic"  # semantic, exact, regex
    priority: int = 10

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SkillStep:
    id: str
    name: str
    description: str = ""
    action: str = ""           # Semantic action (e.g. locate_file, extract_audio, create_summary)
    adapter: str = "generic"   # ExcelAdapter, VideoAdapter, AntigravityAdapter, FileAdapter
    tool: Optional[str] = None
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    condition: Optional[str] = None      # Decision rule: e.g. "IF exists(source_media)"
    fallback_action: Optional[str] = None
    verification_rule: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SkillCorrection:
    id: str
    skill_id: str
    original_behavior: str
    user_correction: str
    corrected_behavior: str
    scope: str = "SKILL"  # ONE_TIME, PROJECT, SKILL, GLOBAL
    confidence: float = 1.0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Skill:
    id: str
    name: str
    description: str
    intent: str
    category: SkillCategory = SkillCategory.CUSTOM
    status: SkillStatus = SkillStatus.DRAFT
    version: int = 1
    triggers: List[SkillTrigger] = field(default_factory=list)
    variables: List[SkillVariable] = field(default_factory=list)
    steps: List[SkillStep] = field(default_factory=list)
    required_agents: List[str] = field(default_factory=list)
    required_tools: List[str] = field(default_factory=list)
    required_permissions: List[str] = field(default_factory=list)
    preconditions: List[str] = field(default_factory=list)
    verification_rules: List[str] = field(default_factory=list)
    recovery_rules: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)  # sub-skill IDs
    success_count: int = 0
    failure_count: int = 0
    confidence: float = 0.5
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_used_at: Optional[str] = None
    source: str = "manual"  # demonstration, task_promotion, manual, builtin

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value if isinstance(self.category, SkillCategory) else str(self.category)
        d["status"] = self.status.value if isinstance(self.status, SkillStatus) else str(self.status)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Skill:
        data_copy = dict(data)
        if "category" in data_copy and isinstance(data_copy["category"], str):
            data_copy["category"] = SkillCategory(data_copy["category"])
        if "status" in data_copy and isinstance(data_copy["status"], str):
            data_copy["status"] = SkillStatus(data_copy["status"])

        # Reconstruct sub-objects
        if "triggers" in data_copy:
            data_copy["triggers"] = [
                t if isinstance(t, SkillTrigger) else SkillTrigger(**t)
                for t in data_copy["triggers"]
            ]
        if "variables" in data_copy:
            data_copy["variables"] = [
                v if isinstance(v, SkillVariable) else SkillVariable(**v)
                for v in data_copy["variables"]
            ]
        if "steps" in data_copy:
            data_copy["steps"] = [
                s if isinstance(s, SkillStep) else SkillStep(**s)
                for s in data_copy["steps"]
            ]

        return cls(**data_copy)
