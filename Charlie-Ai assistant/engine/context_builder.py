"""engine/context_builder.py — Dynamic Context Builder for JARVIS.

Constructs context dynamically before dispatching complex requests to the LLM:
Active Project + Relevant Memories + Checkpoint State + Procedures + Computer State.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.memory_manager import MemoryManager


class ContextBuilder:
    """Assembles rich, relevant, and deduplicated context for agent execution."""

    def __init__(self, memory_manager: MemoryManager):
        self.memory = memory_manager

    def build_context(
        self,
        user_request: str,
        active_project: Optional[str] = None,
        available_tools: Optional[List[str]] = None,
    ) -> str:
        """Assemble structured context for the current turn."""
        parts: List[str] = []

        # 1. Project Context
        if active_project:
            p_ctx = self.memory.get_project_context(active_project)
            if p_ctx and p_ctx.get("facts"):
                lines = [f"[ACTIVE PROJECT: {active_project.upper()}]"]
                for cat, kvs in p_ctx["facts"].items():
                    for k, v in kvs.items():
                        lines.append(f"- {cat}.{k}: {v}")
                parts.append("\n".join(lines))

        # 2. Semantic Memory Retrieval (Targeted, max 4 items to keep fast)
        recalled = self.memory.search(user_request, project_name=active_project, limit=4)
        if recalled:
            lines = ["[RELEVANT MEMORY]"]
            for item in recalled:
                lines.append(f"- ({item['category']}) {item['content']}")
            parts.append("\n".join(lines))

        # 3. Recent Task Checkpoint (if any active/recent)
        recent_task = self.memory.get_recent_task_context(project_name=active_project)
        if recent_task and recent_task.get("status") in ("RUNNING", "WAITING_USER"):
            lines = [
                "[IN-PROGRESS TASK CHECKPOINT]",
                f"Task: {recent_task.get('task_name', '')}",
                f"Goal: {recent_task.get('goal', '')}",
                f"Status: {recent_task.get('status', '')}",
                f"Last Checkpoint: {recent_task.get('last_checkpoint', '')}",
                f"Next Action: {recent_task.get('next_action', '')}",
            ]
            parts.append("\n".join(lines))

        # 4. Relevant Procedural Memory
        proc = self.memory.get_procedure(user_request)
        if proc:
            steps_str = " -> ".join(proc.get("steps", []))
            parts.append(f"[PROVEN PROCEDURE: {proc.get('name')}]\nWorkflow: {steps_str}")

        # 5. Error Memory Check
        err = self.memory.find_error_solution(user_request)
        if err and err.get("successful_fix"):
            parts.append(f"[KNOWN ERROR SOLUTION]\nIssue: {err.get('error_signature')}\nFix: {err.get('successful_fix')}")

        return "\n\n".join(parts)
