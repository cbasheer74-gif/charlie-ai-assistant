"""actions/antigravity_bridge.py — Google Antigravity & IDE Integration Bridge.

Inspects open Antigravity/VS Code windows, extracts active project state,
and formulates targeted development prompts.
"""

from __future__ import annotations

from typing import Any, Dict

from engine.agents.antigravity_agent import AntigravityAgent
from engine.error_recovery import ErrorRecoveryEngine
from engine.memory_manager import MemoryManager
from engine.permissions import PermissionManager
from engine.rollback import RollbackManager
from engine.task_planner import TaskPlanner
from engine.verification import VerificationEngine

_mem = MemoryManager()
_perm = PermissionManager()
_ver = VerificationEngine()
_rec = ErrorRecoveryEngine(_mem)
_roll = RollbackManager()
_plan = TaskPlanner(_mem)
_agent = AntigravityAgent(_mem, _plan, _perm, _ver, _rec, _roll)


def antigravity_bridge(parameters: dict, **_unused) -> str:
    """Coordinate development context with Antigravity IDE."""
    params = parameters or {}
    action = str(params.get("action") or "inspect").strip().lower()
    project = str(params.get("project") or "").strip()
    goal = str(params.get("goal") or "").strip()

    if action == "inspect":
        windows = _agent.detect_ide_windows()
        if not windows:
            return "No active Google Antigravity or VS Code windows detected."
        return "Detected IDE Windows:\n" + "\n".join(f"- {w}" for w in windows)

    if action == "prepare_prompt":
        if not project or not goal:
            return "Please provide both project and goal."
        res = _agent.prepare_antigravity_prompt(project, goal)
        return (
            f"IDE Status: {res['ide_status']}\n\n"
            f"Generated Antigravity Instruction:\n"
            f"----------------------------------------\n"
            f"{res['generated_prompt']}\n"
            f"----------------------------------------"
        )

    return f"Unknown action: {action}. Supported: inspect, prepare_prompt."


TOOL = {
    "name": "antigravity_bridge",
    "description": (
        "Bridge with Google Antigravity IDE: detect open IDE windows, retrieve project phase, "
        "and formulate targeted non-regenerating development prompts."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["inspect", "prepare_prompt"],
                "description": "Action: inspect IDE windows or prepare Antigravity development prompt.",
            },
            "project": {"type": "STRING", "description": "Project name (e.g. ZynPay)."},
            "goal": {"type": "STRING", "description": "Specific task goal or feature to implement."},
        },
    },
    "handler": antigravity_bridge,
}
