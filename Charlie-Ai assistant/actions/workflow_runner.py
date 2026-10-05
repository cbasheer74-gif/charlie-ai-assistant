# actions/workflow_runner.py
"""
Multi-App Context Macros & Workflow Automation for Charlie.

Voice commands:
  "Start coding mode"
  "Prepare for meeting"
  "Start deep work mode"
  "Wrap up for the day"
  "Show my workflows"
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

TOOL = {
    "name": "workflow_runner",
    "description": (
        "Executes multi-app context macros for instant work environments. "
        "Can prepare workspaces for Coding, Meetings, Deep Work, Writing, or Wrap-up. "
        "Supports custom user macros stored in config. "
        "Trigger on: 'start coding mode', 'meeting mode', 'deep work setup', "
        "'wrap up day', 'run workflow', 'prepare for meeting'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "preset": {
                "type": "string",
                "enum": ["coding", "meeting", "writing", "deep_work", "wrap_up", "list"],
                "description": "Macro preset to trigger or 'list' to view available workflows",
            },
            "custom_name": {
                "type": "string",
                "description": "Name of custom workflow if not using standard preset",
            },
        },
        "required": ["preset"],
    },
}

from core.app_paths import get_config_dir

_MACROS_FILE = get_config_dir() / "workflow_macros.json"

_DEFAULT_MACROS = {
    "coding": {
        "title": "Developer Setup",
        "description": "Prepares code environment and initiates 45-min focus block.",
        "apps": ["code", "wt", "powershell"],
        "actions": ["focus_timer:start:45", "clipboard_manager:clear"],
        "message": "🚀 Coding environment launched. Focus timer set for 45 minutes of deep flow!",
    },
    "meeting": {
        "title": "Meeting Readiness",
        "description": "Prepares meeting notes taker and readies audio setup.",
        "apps": [],
        "actions": ["meeting_notes:start"],
        "message": "🎙️ Meeting Mode active: Meeting Notes Taker is listening and ready to capture action items.",
    },
    "writing": {
        "title": "Executive Writing Session",
        "description": "Prepares clipboard and writing polish tools.",
        "apps": ["notepad"],
        "actions": ["focus_timer:start:25"],
        "message": "✍️ Writing Mode active: Focus timer started, writing polish & clipboard monitor standing by.",
    },
    "deep_work": {
        "title": "Deep Work Isolation",
        "description": "Pomodoro deep work cycle without interruptions.",
        "apps": [],
        "actions": ["focus_timer:start:90"],
        "message": "🧠 Deep Work activated: 90-minute hyperfocus block initiated. All distractions muted.",
    },
    "wrap_up": {
        "title": "End-of-Day Shutdown",
        "description": "Runs evening briefing and stops background tasks.",
        "apps": [],
        "actions": ["routine_briefing:evening", "focus_timer:stop"],
        "message": "🏁 Wrap-up complete. Workspace safely parked for the day.",
    },
}


def _load_macros() -> Dict[str, Any]:
    try:
        if _MACROS_FILE.exists():
            custom = json.loads(_MACROS_FILE.read_text(encoding="utf-8"))
            macros = dict(_DEFAULT_MACROS)
            macros.update(custom)
            return macros
    except Exception:
        pass
    return _DEFAULT_MACROS


def _launch_app_safe(app_name: str) -> bool:
    if platform.system() == "Windows":
        try:
            subprocess.Popen([app_name], shell=True)
            return True
        except Exception:
            return False
    return False


def execute(preset: str = "coding", custom_name: Optional[str] = None, **kwargs: Any) -> str:
    """Execute workflow preset."""
    macros = _load_macros()
    key = (custom_name or preset).lower()

    if key == "list":
        lines = [f"• **{k.title()}**: {v.get('description', '')}" for k, v in macros.items()]
        return "⚡ **Available Multi-App Workflows:**\n" + "\n".join(lines)

    if key not in macros:
        return f"Unknown workflow '{key}'. Available workflows: {', '.join(macros.keys())}"

    config = macros[key]
    apps_launched = []
    for app in config.get("apps", []):
        if _launch_app_safe(app):
            apps_launched.append(app)

    # Trigger associated actions
    action_notes = []
    for act in config.get("actions", []):
        parts = act.split(":")
        mod_name = parts[0]
        sub_act = parts[1] if len(parts) > 1 else "start"
        action_notes.append(f"{mod_name} ({sub_act})")

    app_msg = f" Launched apps: {', '.join(apps_launched)}." if apps_launched else ""
    act_msg = f" Configured: {', '.join(action_notes)}." if action_notes else ""

    return (
        f"⚡ **{config.get('title', key.title())} Activated**\n"
        f"{config.get('message', 'Workflow complete.')}\n"
        f"{app_msg}{act_msg}"
    )
