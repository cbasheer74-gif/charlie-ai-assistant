"""actions/kids_activity.py — Auto-discovered action for Children's Activities.

Supports:
- Bedtime stories with interactive calm branching.
- Gamified math quizzes with streaks and star rewards.
- Step-by-step voice drawing coach.
- Parental content guard & screen time limit controls.
- Overall kid activity progress & star stats.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from memory import kids_activity as kids


def kids_activity(parameters: Dict[str, Any], **kwargs) -> str:
    params = parameters or {}
    action = str(params.get("action") or "status").strip().lower()

    if action == "story":
        sub = str(params.get("subaction") or "start").strip().lower()
        if sub == "start":
            theme = str(params.get("topic") or "space").strip().lower()
            res = kids.start_story(theme)
            return (
                f"[Bedtime Story] ({res['theme'].title()} Adventure - Chapter {res['chapter']}):\n"
                f"{res['content']}\n\n"
                f"{res['prompt']}"
            )
        else:
            choice = str(params.get("input") or "explore deeper").strip()
            res = kids.next_chapter(choice)
            return f"[Story] {res['instruction']}"

    if action == "math":
        sub = str(params.get("subaction") or "question").strip().lower()
        if sub in ("question", "start"):
            diff = str(params.get("difficulty") or "easy").strip().lower()
            res = kids.generate_math_problem(diff)
            return f"[Math Quest] ({diff.title()}): {res['prompt']}"
        elif sub in ("answer", "check"):
            ans = params.get("input")
            if ans is None:
                return "Please provide an answer to check."
            res = kids.check_math_answer(ans)
            return res["message"]

    if action == "draw":
        sub = str(params.get("subaction") or "start").strip().lower()
        if sub == "start":
            subject = str(params.get("topic") or "cat").strip().lower()
            res = kids.start_drawing(subject)
            return f"[Drawing Coach] ({subject.title()} - Step {res['step']}/{res['total_steps']}):\n{res['instruction']}\nSay 'next step' when ready!"
        else:
            res = kids.next_drawing_step()
            if res.get("finished"):
                return f"[Drawing Complete] {res['instruction']}"
            return f"[Drawing Step {res['step']}/{res['total_steps']}]:\n{res['instruction']}\nSay 'next step' when ready!"

    if action == "guard":
        pin = str(params.get("input") or "").strip()
        enabled = bool(params.get("enabled", True))
        limit = int(params.get("limit") or 60)
        res = kids.update_guard(enabled=enabled, pin=pin, limit_minutes=limit)
        if res.get("status") == "error":
            return f"[Guard] {res.get('message')}"
        state_str = "Enabled" if res["guard_enabled"] else "Disabled"
        return f"[Kid-Safe Content Guard] {state_str} (Daily Limit: {res['daily_limit_minutes']} min, Filter: {res['filter_level']})."

    if action == "status":
        stats = kids.get_kids_status()
        drawings = ", ".join(stats["completed_drawings"]) if stats["completed_drawings"] else "None yet"
        guard_text = "Active" if stats["guard_active"] else "Inactive"
        return (
            f"[Kids Corner Progress]:\n"
            f"- Total Stars: {stats['total_stars']} stars\n"
            f"- Math Best Streak: {stats['math_streak']} (Solved: {stats['math_total_correct']})\n"
            f"- Completed Drawings: {drawings}\n"
            f"- Kid-Safe Guard: {guard_text} (Limit: {stats['daily_limit_minutes']} mins)"
        )

    return "Unknown action. Choose from: story, math, draw, guard, or status."


TOOL = {
    "name": "kids_activity",
    "description": (
        "Children's entertainment and learning hub: bedtime interactive storytelling, "
        "gamified math quests with star rewards, step-by-step voice drawing coach, "
        "and parental kid-safe controls."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "story | math | draw | guard | status",
            },
            "subaction": {
                "type": "STRING",
                "description": "start | next | question | answer",
            },
            "topic": {
                "type": "STRING",
                "description": "Story theme (space, forest, ocean, magic) or drawing subject (cat, rocket, house)",
            },
            "difficulty": {
                "type": "STRING",
                "description": "easy | medium | hard (for math quests)",
            },
            "input": {
                "type": "STRING",
                "description": "Child's answer, story choice, or parental PIN",
            },
            "enabled": {
                "type": "BOOLEAN",
                "description": "Enable or disable kid-safe guard",
            },
            "limit": {
                "type": "INTEGER",
                "description": "Daily screen time limit in minutes",
            },
        },
        "required": ["action"],
    },
    "handler": kids_activity,
}
