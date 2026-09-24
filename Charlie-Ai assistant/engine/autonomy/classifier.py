"""engine/autonomy/classifier.py — Task Complexity Classification & Goal Interpretation.

Transforms natural language instructions into structured execution specifications
while enforcing the Minimum-Question Policy.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from engine.memory_manager import MemoryManager


class TaskComplexity(str, Enum):
    SIMPLE = "SIMPLE"                # "Open Chrome", "List files" (1-2 atomic actions)
    MODERATE = "MODERATE"            # "Clean this Excel file", "Read PDF" (3-5 actions)
    COMPLEX = "COMPLEX"              # "Fix backend login bug and run tests" (6-15 actions)
    LONG_WORKFLOW = "LONG_WORKFLOW"  # "Research today's trend and make a 30s Short" (15-50 actions)


@dataclass
class InterpretedGoal:
    primary_goal: str
    expected_output: str
    complexity: TaskComplexity
    constraints: List[str] = field(default_factory=list)
    known_context: Dict[str, Any] = field(default_factory=dict)
    missing_information: List[str] = field(default_factory=list)
    assumptions_allowed: bool = True
    tools_required: List[str] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)
    risk_level: str = "SAFE_WRITE"
    inferred_defaults: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["complexity"] = self.complexity.value
        return d


class TaskComplexityClassifier:
    """Classifies user requests into appropriate planning depth tiers."""

    @staticmethod
    def classify(goal: str, context: Optional[Dict[str, Any]] = None) -> TaskComplexity:
        low = goal.lower()

        # LONG_WORKFLOW keywords: full content creation, multi-stage pipelines
        if any(w in low for w in ("youtube short", "create short", "trend", "reel", "bana do", "full workflow", "end to end")):
            if any(w in low for w in ("short", "video", "pipeline", "marketing", "content")):
                return TaskComplexity.LONG_WORKFLOW

        # COMPLEX keywords: debugging, refactoring, building, multi-tool coding/app workflows
        if any(w in low for w in ("fix", "debug", "refactor", "continue app", "continue project", "antigravity", "backend", "test and fix")):
            return TaskComplexity.COMPLEX

        # MODERATE keywords: document cleaning, summarizing, data processing
        if any(w in low for w in ("excel", "sheet", "summary", "clean", "report", "convert", "transcode", "search and summarize")):
            return TaskComplexity.MODERATE

        # SIMPLE: single window/app launch, quick lookup, simple read
        word_count = len(goal.strip().split())
        if word_count <= 4 and any(w in low for w in ("open", "launch", "show", "read", "status", "port", "who")):
            return TaskComplexity.SIMPLE

        if word_count <= 6:
            return TaskComplexity.MODERATE

        return TaskComplexity.COMPLEX


class GoalInterpreter:
    """Interprets raw natural language instructions into structured goals with minimum questions."""

    def __init__(self, memory_manager: Optional[MemoryManager] = None):
        self.memory = memory_manager

    def interpret(self, user_instruction: str, active_project: Optional[str] = None) -> InterpretedGoal:
        complexity = TaskComplexityClassifier.classify(user_instruction)
        low = user_instruction.lower()

        known: Dict[str, Any] = {}
        inferred: Dict[str, Any] = {}
        constraints: List[str] = []
        tools: List[str] = []
        criteria: List[str] = []
        missing: List[str] = []
        risk = "SAFE_WRITE"

        # 1. Project Context Recovery
        if active_project:
            known["project"] = active_project
        elif self.memory:
            # Query recent project memory
            recent_proj = self.memory.get_project_context()
            if recent_proj and recent_proj.get("project_name"):
                known["project"] = recent_proj["project_name"]

        # 2. Domain-Specific Interpretation & Minimum-Question Defaults
        if any(w in low for w in ("short", "video", "reel")):
            primary = "Create vertical Short video"
            expected = "1080x1920 MP4 video file with verified audio and captions"
            tools = ["search_web", "video_studio", "verification_engine"]
            inferred["aspect_ratio"] = "9:16 (1080x1920)"
            inferred["duration_seconds"] = 30
            inferred["format"] = "mp4"
            inferred["output_dir"] = "output/shorts"
            constraints = ["Must be 9:16 vertical", "Duration under 60 seconds", "AAC audio stream required"]
            criteria = ["Video file exists", "FFprobe validates 1080x1920 resolution", "Audio stream present"]
            # Extract duration if explicitly stated
            dur_match = re.search(r"(\d+)\s*(?:sec|second|s)", low)
            if dur_match:
                inferred["duration_seconds"] = int(dur_match.group(1))

        elif any(w in low for w in ("excel", "sheet", "xlsx", "spreadsheet")):
            primary = "Inspect, clean, and summarize Excel workbook"
            expected = "Safe updated XLSX workbook or summary sheet with verified formulas"
            tools = ["file_catalog", "excel_worker", "verification_engine", "rollback_manager"]
            inferred["backup_first"] = True
            inferred["preserve_formulas"] = True
            constraints = ["Do not overwrite without backup", "Preserve existing formulas", "Verify cell totals"]
            criteria = ["Workbook opens cleanly in openpyxl", "Sheet structure intact", "Summary calculations non-empty"]

        elif any(w in low for w in ("code", "bug", "continue", "zynpay", "antigravity", "app", "feature")):
            primary = f"Advance development and test codebase ({known.get('project', 'active project')})"
            expected = "Tested repository changes with passing verification and saved checkpoint"
            tools = ["dev_agent", "diagnose_error", "code_helper", "verification_engine", "antigravity_bridge"]
            constraints = ["Minimal diff only", "Syntax verification before commit", "Do not regenerate existing files"]
            criteria = ["No syntax errors", "Target tests or entrypoints pass", "Task checkpoint saved"]

        elif any(w in low for w in ("clean my pc", "delete", "format", "remove all")):
            primary = "Clean temporary files and logs safely"
            expected = "Report of freed space without deleting critical user assets"
            tools = ["file_processor", "verification_engine"]
            risk = "HIGH_IMPACT"
            constraints = ["Strictly target temp directories only", "No permanent deletion of user folders"]
            criteria = ["Only cache and temp files touched", "Destructive operations gated"]

        else:
            primary = user_instruction
            expected = "Completed user command"
            tools = ["computer_operator", "verification_engine"]
            criteria = ["Expected action verified"]

        return InterpretedGoal(
            primary_goal=primary,
            expected_output=expected,
            complexity=complexity,
            constraints=constraints,
            known_context=known,
            missing_information=missing,
            assumptions_allowed=True,
            tools_required=tools,
            success_criteria=criteria,
            risk_level=risk,
            inferred_defaults=inferred,
        )
