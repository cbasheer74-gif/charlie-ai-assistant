# actions/routine_briefing.py
"""
Daily Routine & Executive Morning/Evening Briefing for Charlie.

Voice commands:
  "Good morning Charlie"
  "Give me today's briefing"
  "What is on my schedule today?"
  "Prepare me for my day"
  "Evening wrap up"
  "What are my open action items?"
"""

from __future__ import annotations

import json
import os
import platform
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

TOOL = {
    "name": "routine_briefing",
    "description": (
        "Delivers personalized executive morning briefings and end-of-day wrap ups. "
        "Aggregates schedule, high-priority tasks, weather, system status, focus goals, "
        "and daily productivity metrics. "
        "Trigger on: 'good morning', 'morning briefing', 'start my day', 'today's plan', "
        "'evening wrap up', 'end of day', 'what is on my schedule', 'daily briefing'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["morning", "evening", "tasks", "set_goal", "schedule"],
                "description": "morning=full morning brief, evening=day review, tasks=today's priorities, set_goal=save daily goal, schedule=agenda",
            },
            "goal_text": {
                "type": "string",
                "description": "Goal or focus priority to add for today",
            },
            "city": {
                "type": "string",
                "description": "City name for weather inclusion (optional)",
            },
        },
        "required": ["action"],
    },
}

from core.app_paths import get_config_dir

_CONFIG_PATH = get_config_dir() / "daily_routine.json"


def _load_data() -> Dict[str, Any]:
    try:
        if _CONFIG_PATH.exists():
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"daily_goals": [], "routines": {}, "history": []}


def _save_data(data: Dict[str, Any]) -> None:
    try:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _get_system_snapshot() -> Dict[str, str]:
    """Basic hardware & environment check."""
    status = {"battery": "Plugged in", "os": platform.platform()}
    try:
        import psutil
        batt = psutil.sensors_battery()
        if batt:
            status["battery"] = f"{int(batt.percent)}% ({'Charging' if batt.power_plugged else 'On Battery'})"
    except Exception:
        pass
    return status


def _get_pending_reminders() -> List[str]:
    reminders = []
    try:
        rem_file = get_config_dir() / "reminders.json"
        if rem_file.exists():
            data = json.loads(rem_file.read_text(encoding="utf-8"))
            items = data.get("active", []) if isinstance(data, dict) else data
            for it in items[:4]:
                if isinstance(it, dict):
                    reminders.append(it.get("text") or it.get("title") or str(it))
                elif isinstance(it, str):
                    reminders.append(it)
    except Exception:
        pass
    return reminders


def execute(
    action: str = "morning",
    goal_text: Optional[str] = None,
    city: Optional[str] = None,
    **kwargs: Any,
) -> str:
    """Execute routine briefing action."""
    data = _load_data()
    today_str = datetime.now().strftime("%A, %B %d, %Y")
    now_time = datetime.now().strftime("%I:%M %p")

    if action == "set_goal" and goal_text:
        goals = data.setdefault("daily_goals", [])
        goals.append({"goal": goal_text.strip(), "date": today_str, "done": False})
        _save_data(data)
        return f"🎯 Focus goal recorded: '{goal_text}'. Charlie will keep you on track!"

    if action == "morning":
        sys_info = _get_system_snapshot()
        reminders = _get_pending_reminders()
        today_goals = [g["goal"] for g in data.get("daily_goals", []) if g.get("date") == today_str and not g.get("done")]

        parts = [
            f"🌅 **Good morning! Here is your Executive Briefing for {today_str} ({now_time}):**\n",
            f"💻 **System:** Battery {sys_info.get('battery')}",
        ]

        if today_goals:
            parts.append(f"🎯 **Today's Key Focus Goals:**\n" + "\n".join(f"  • {g}" for g in today_goals))
        else:
            parts.append("🎯 **Focus Goal:** No specific primary goal set. Say 'Set today's goal: [task]' to track one.")

        if reminders:
            parts.append(f"⏰ **Pending Agenda & Reminders:**\n" + "\n".join(f"  • {r}" for r in reminders))
        else:
            parts.append("⏰ **Agenda:** Clear schedule. Ready for focused deep work.")

        parts.append(
            "\n⚡ Say **'start focus mode'** for a 25-minute Pomodoro block, "
            "or **'draft an email'** whenever you're ready."
        )
        return "\n".join(parts)

    if action == "evening":
        today_goals = [g for g in data.get("daily_goals", []) if g.get("date") == today_str]
        done_goals = [g["goal"] for g in today_goals if g.get("done")]
        pending_goals = [g["goal"] for g in today_goals if not g.get("done")]

        parts = [
            f"🌙 **End of Day Wrap-Up — {today_str}:**\n",
            f"✅ **Completed Goals:** {len(done_goals)}",
            f"⏳ **Pending Items to Roll Over:** {len(pending_goals)}",
        ]
        if pending_goals:
            parts.append("\n".join(f"  • {p}" for p in pending_goals))
        parts.append("\n🌟 Great work today! System and workspace state preserved. Rest well!")
        return "\n".join(parts)

    if action == "tasks":
        today_goals = [g["goal"] for g in data.get("daily_goals", []) if g.get("date") == today_str]
        if not today_goals:
            return "No tasks recorded for today yet. Say 'set goal to [your task]' to add one."
        return f"📋 **Today's Priorities:**\n" + "\n".join(f"• {t}" for t in today_goals)

    return "Unknown briefing action. Say 'morning', 'evening', 'tasks', or 'set_goal'."
