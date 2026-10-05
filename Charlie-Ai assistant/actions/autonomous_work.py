"""actions/autonomous_work.py — CHARLIE Autonomous Work Engine Action.

Exposes multi-agent autonomous task graph execution, dependency scheduling,
durable checkpointing, and self-recovery directly to Gemini Live.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from engine.autonomy.orchestrator import AutonomyLevel, AutonomyOrchestrator
from engine.error_recovery import ErrorRecoveryEngine
from engine.memory_manager import MemoryManager
from engine.permissions import PermissionManager
from engine.rollback import RollbackManager
from engine.router import AgentRouter
from engine.tool_registry import ToolRegistry
from engine.verification import VerificationEngine

_memory = MemoryManager()
_permissions = PermissionManager()
_verification = VerificationEngine()
_tools = ToolRegistry(_permissions, _verification)

_recovery = ErrorRecoveryEngine(_memory)
_rollback = RollbackManager()
_router = AgentRouter(
    memory=_memory,
    planner=None,  # Handled inside orchestrator
    permissions=_permissions,
    verification=_verification,
    recovery=_recovery,
    rollback=_rollback,
)

_orchestrator = AutonomyOrchestrator(
    memory_manager=_memory,
    agent_router=_router,
    tool_registry=_tools,
    permission_manager=_permissions,
    verification_engine=_verification,
    error_recovery=_recovery,
    rollback_manager=_rollback,
    autonomy_level=AutonomyLevel.LEVEL_3_AUTONOMOUS_WORKFLOW,
)


def autonomous_work(parameters: dict, **_unused) -> str:
    """Execute, pause, resume, or check complex multi-step autonomous tasks."""
    params = parameters or {}
    action = str(params.get("action") or "execute").strip().lower()
    goal = str(params.get("goal") or "").strip()
    project = str(params.get("project") or "").strip() or None
    lvl_int = int(params.get("autonomy_level") or 3)

    try:
        level = AutonomyLevel(lvl_int)
    except Exception:
        level = AutonomyLevel.LEVEL_3_AUTONOMOUS_WORKFLOW

    if action == "execute":
        if not goal:
            return "Please specify a goal to execute autonomously."
        result = _orchestrator.execute_goal(user_goal=goal, active_project=project)
        status = result.get("status", "UNKNOWN")
        prog = result.get("progress", {})
        artifacts = result.get("artifacts_created", [])

        art_summary = f", Artifacts: {len(artifacts)}" if artifacts else ""
        return (
            f"[AUTONOMY: {status}] Goal: {goal}\n"
            f"Progress: {prog.get('completed', 0)}/{prog.get('total', 0)} ({prog.get('percent', 0)}%){art_summary}\n"
            f"Details: {result.get('reason') or result.get('message') or 'Executed through task graph.'}"
        )

    elif action == "pause":
        _orchestrator.pause_task()
        return "Autonomous task execution paused."

    elif action == "resume":
        _orchestrator.resume_task()
        target_task_id = str(params.get("task_id") or "").strip() or None
        # If active graph is still running in memory, acknowledge unpause
        if _orchestrator._active_graph and not _orchestrator._active_graph.is_completed():
            return "Resumed active in-memory task loop."
        # Otherwise execute resumed workflow from durable checkpoint
        res = _orchestrator.resume_execution(task_id=target_task_id, project_id=project)
        if res.get("status") == "NOT_FOUND":
            return "No interrupted task found to resume."
        prog = res.get("progress", {})
        status = res.get("status", "UNKNOWN")
        stage = res.get("resumed_from_stage", "Checkpoint")
        return (
            f"[AUTONOMY RESUMED: {status}] Resumed from '{stage}'\n"
            f"Progress: {prog.get('completed', 0)}/{prog.get('total', 0)} ({prog.get('percent', 0)}%)\n"
            f"Details: {res.get('reason') or res.get('message') or 'Task execution continued to current state.'}"
        )

    elif action in ("list", "resumable"):
        tasks = _orchestrator.resumer.list_resumable_tasks(project_id=project)
        if not tasks:
            return "No resumable tasks found."
        lines = [f"Found {len(tasks)} resumable task(s):"]
        for t in tasks:
            prog = t.get("progress", {})
            lines.append(
                f"- Task ID: {t['task_id']} | Goal: {t.get('goal', 'Unknown')} | "
                f"Stage: {t.get('current_stage', 'Unknown')} | "
                f"Progress: {prog.get('completed', 0)}/{prog.get('total', 0)} ({prog.get('percent', 0)}%)"
            )
        return "\n".join(lines)

    elif action == "cancel":
        target_task_id = str(params.get("task_id") or "").strip()
        if target_task_id:
            _orchestrator.resumer.cancel_resumable_task(target_task_id)
        _orchestrator.cancel_task()
        return "Autonomous task cancelled and locks released."

    elif action == "status":
        if _orchestrator._active_graph:
            prog = _orchestrator._active_graph.get_progress()
            return f"Active Task: {_orchestrator._active_graph.goal} | Status: {prog['completed']}/{prog['total']} ({prog['percent']}%)"
        return "No autonomous task currently running."

    return f"Unknown autonomous action '{action}'."


TOOL = {
    "name": "autonomous_work",
    "description": (
        "Execute complex multi-step workflows autonomously using dependency task graphs, "
        "specialist agents, durable checkpointing, and verification. Use for requests like "
        "'make a YouTube Short', 'clean and summarize Excel file', 'continue my app', or multi-step goals."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["execute", "pause", "resume", "list", "cancel", "status"],
                "description": "Action to perform: 'execute' new goal, 'pause', 'resume', 'list', 'cancel', or 'status'.",
            },
            "goal": {
                "type": "STRING",
                "description": "The high-level user goal to plan and execute.",
            },
            "project": {
                "type": "STRING",
                "description": "Optional project context name (e.g. 'ZynPay').",
            },
            "autonomy_level": {
                "type": "INTEGER",
                "description": "Autonomy level: 0 (Chat), 1 (Assisted), 2 (Safe Single), 3 (Autonomous Workflow), 4 (Advanced). Default is 3.",
            },
        },
    },
    "handler": autonomous_work,
}
