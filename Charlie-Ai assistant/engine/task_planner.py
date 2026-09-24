"""engine/task_planner.py — Task Planner and Durable Checkpointing for JARVIS.

Decomposes complex requests into stateful steps, persists checkpoints to SQLite,
and supports resuming from interruptions ("continue", "resume", "where did we stop").
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from engine.memory_manager import MemoryManager


@dataclass
class PlanStep:
    index: int
    name: str
    tool: str
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, SKIPPED
    evidence: str = ""
    error: str = ""


@dataclass
class TaskPlan:
    id: str
    goal: str
    project_name: Optional[str]
    steps: List[PlanStep] = field(default_factory=list)
    status: str = "PENDING"  # PENDING, RUNNING, WAITING_USER, FAILED, RECOVERING, COMPLETED
    current_step: int = 0
    created_at: str = ""
    updated_at: str = ""


class TaskPlanner:
    """Creates, persists, advances, and resumes multi-step goal plans."""

    def __init__(self, memory_manager: MemoryManager):
        self.memory = memory_manager
        self._active_plan: Optional[TaskPlan] = None

    def plan_goal(self, goal: str, project_name: Optional[str] = None) -> TaskPlan:
        """Decompose user goal into structured steps based on domain templates."""
        now = datetime.now().isoformat()
        plan_id = f"plan_{uuid.uuid4().hex[:12]}"
        low = goal.lower()

        steps: List[PlanStep] = []

        if any(w in low for w in ("short", "reel", "video", "youtube short")):
            # Video workflow template
            steps = [
                PlanStep(0, "Research trending topic & concept", "research_agent"),
                PlanStep(1, "Formulate script & hook", "dev_agent"),
                PlanStep(2, "Select and inspect source media", "file_processor"),
                PlanStep(3, "Composite vertical 1080x1920 video & burn captions", "video_studio"),
                PlanStep(4, "Verify video resolution, duration, and audio", "verification_engine"),
            ]
        elif any(w in low for w in ("excel", "sheet", "xlsx", "spreadsheet", "clean excel")):
            # Excel workflow template
            steps = [
                PlanStep(0, "Locate recent workbook in file catalog", "file_catalog"),
                PlanStep(1, "Inspect workbook sheets and formulas", "excel_worker"),
                PlanStep(2, "Create safe copy-first backup", "rollback_manager"),
                PlanStep(3, "Apply data transformation or summary report", "excel_worker"),
                PlanStep(4, "Verify formulas and cell totals", "verification_engine"),
            ]
        elif any(w in low for w in ("code", "bug", "fix", "app", "feature", "build", "run")):
            # Coding workflow template
            steps = [
                PlanStep(0, "Inspect repository root and Git status", "dev_agent"),
                PlanStep(1, "Locate target source file & reproduce error", "diagnose_error"),
                PlanStep(2, "Create minimal targeted code modification", "code_helper"),
                PlanStep(3, "Run syntax check & automated verification", "verification_engine"),
                PlanStep(4, "Update project and error memory", "memory_engine"),
            ]
        else:
            # Generic multi-step template
            steps = [
                PlanStep(0, f"Analyze goal: {goal[:50]}", "computer_operator"),
                PlanStep(1, "Inspect relevant system and files", "computer_control"),
                PlanStep(2, "Execute core action", "computer_operator"),
                PlanStep(3, "Verify final outcome", "verification_engine"),
            ]

        plan = TaskPlan(
            id=plan_id,
            goal=goal,
            project_name=project_name,
            steps=steps,
            status="RUNNING",
            current_step=0,
            created_at=now,
            updated_at=now,
        )
        self._active_plan = plan

        # Persist task in database
        self.memory.create_task(
            task_name=f"Plan: {goal[:40]}",
            goal=goal,
            project_name=project_name,
        )
        self._checkpoint_active_plan("Plan initialized")
        return plan

    def get_active_plan(self) -> Optional[TaskPlan]:
        return self._active_plan

    def advance_step(self, evidence: str = "") -> Optional[PlanStep]:
        """Mark current step completed with evidence and advance to next."""
        if not self._active_plan:
            return None

        plan = self._active_plan
        idx = plan.current_step
        if 0 <= idx < len(plan.steps):
            plan.steps[idx].status = "COMPLETED"
            plan.steps[idx].evidence = evidence

        plan.current_step += 1
        if plan.current_step >= len(plan.steps):
            plan.status = "COMPLETED"
            self._checkpoint_active_plan("Task completed successfully", status="COMPLETED")
            return None

        next_step = plan.steps[plan.current_step]
        next_step.status = "RUNNING"
        self._checkpoint_active_plan(f"Advanced to step: {next_step.name}")
        return next_step

    def fail_step(self, error: str) -> None:
        """Mark current step failed and update state."""
        if not self._active_plan:
            return

        plan = self._active_plan
        idx = plan.current_step
        if 0 <= idx < len(plan.steps):
            plan.steps[idx].status = "FAILED"
            plan.steps[idx].error = error
        plan.status = "FAILED"
        self._checkpoint_active_plan(f"Failed at step {idx}: {error[:60]}", status="FAILED")

    def resume_task(self, project_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve recent durable task from database and return its resume state."""
        task = self.memory.get_recent_task_context(project_name=project_name)
        if not task:
            return None

        return {
            "task_id": task.get("id"),
            "goal": task.get("goal"),
            "status": task.get("status"),
            "last_checkpoint": task.get("last_checkpoint"),
            "next_action": task.get("next_action"),
            "project": task.get("project_name") or project_name,
        }

    def _checkpoint_active_plan(self, checkpoint_desc: str, status: str = "RUNNING") -> None:
        if not self._active_plan:
            return
        curr = self._active_plan.current_step
        total = len(self._active_plan.steps)
        next_act = self._active_plan.steps[curr].name if curr < total else "Done"
        summary = f"Step {curr+1}/{total}: {checkpoint_desc}"

        self.memory.store_task_checkpoint(
            task_id=self._active_plan.id,
            checkpoint_name=checkpoint_desc,
            summary=summary,
            next_action=next_act,
            status=status,
        )
