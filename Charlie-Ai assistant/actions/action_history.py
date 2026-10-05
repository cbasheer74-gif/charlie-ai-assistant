"""Voice-accessible view of CHARLIE's persistent, redacted action timeline."""

from __future__ import annotations

from core import undo
from core.task_history import summary


def action_history(parameters: dict | None = None, **_unused) -> str:
    params = parameters or {}
    action = str(params.get("action", "list")).strip().lower()
    if action == "list":
        return summary(params.get("limit", 20))
    if action == "undoable":
        items = undo.history()
        if not items:
            return "There are no supported changes available to undo in this session."
        return "Supported undo actions (newest first):\n" + "\n".join(
            f"{index}. {item}" for index, item in enumerate(items, 1)
        )
    return "action must be list or undoable."


TOOL = {
    "name": "action_history",
    "description": "Shows CHARLIE's persistent, privacy-redacted action history or the actions currently available to undo. Use when the user asks what CHARLIE did, task history, activity history, or what can be undone.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "list (default) | undoable"},
            "limit": {"type": "INTEGER", "description": "Number of recent actions to show, 1-200 (default: 20)."},
        },
        "required": [],
    },
    "handler": action_history,
}
