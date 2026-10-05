"""Persistent task control for CHARLIE's multi-step desktop work.

The Live model decides *how* to complete a user's goal, but without a durable
task record it can lose track after an app opens, a tool fails, or the screen
changes.  This action gives it a small, factual control loop: start a goal,
inspect the desktop, record verified steps, then complete or report a precise
blocker.  It never clicks, types, deletes, or sends anything itself; those
actions remain in their specialised tools and keep their confirmation gates.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from actions.computer_control import computer_control


from core.app_paths import get_memory_dir

_STORE = get_memory_dir() / "computer_operator.json"
_LOCK = threading.Lock()
_MAX_STEPS = 24
_MAX_TEXT = 700
_MAX_HISTORY = 40


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _clean(value, label: str, *, required: bool = False) -> tuple[str, str]:
    text = str(value or "").strip()
    if required and not text:
        return "", f"{label} is required."
    if len(text) > _MAX_TEXT:
        return "", f"{label} is too long (limit: {_MAX_TEXT} characters)."
    return text, ""


def _load() -> dict:
    try:
        data = json.loads(_STORE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(data: dict) -> None:
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="operator-", suffix=".json", dir=_STORE.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
        os.replace(name, _STORE)
    finally:
        try:
            if os.path.exists(name):
                os.unlink(name)
        except OSError:
            pass


def _active(data: dict) -> dict | None:
    task = data.get("active")
    return task if isinstance(task, dict) and task.get("state") == "active" else None


def _archive(data: dict, task: dict) -> None:
    """Retain completed, blocked, and cancelled task records for voice history."""
    history = data.setdefault("history", [])
    if not isinstance(history, list):
        history = data["history"] = []
    history.append(task)
    del history[:-_MAX_HISTORY]
    data["last"] = task


def _summary(task: dict) -> str:
    steps = task.get("steps", [])
    last = steps[-1] if steps else None
    result = [
        f"Task {task.get('id', '?')} — {task.get('state', 'unknown').upper()}",
        f"Goal: {task.get('goal', '')}",
        f"Started: {task.get('started', '')}",
        f"Progress: {len(steps)} recorded step(s)",
    ]
    if last:
        result.append(f"Last step [{last.get('state', 'unknown')}]: {last.get('step', '')}")
        if last.get("evidence"):
            result.append(f"Evidence: {last['evidence']}")
    if task.get("blocker"):
        result.append(f"Blocker: {task['blocker']}")
    return "\n".join(result)


def _history(data: dict, limit: int = 10) -> str:
    records = data.get("history", [])
    if not isinstance(records, list) or not records:
        return "No completed, blocked, or cancelled computer tasks yet."
    records = records[-max(1, min(limit, _MAX_HISTORY)):]
    lines = ["Computer task history (newest first):"]
    for index, task in enumerate(reversed(records), 1):
        steps = task.get("steps", [])
        last = steps[-1] if isinstance(steps, list) and steps else {}
        lines.append(
            f"{index}. [{task.get('state', 'unknown')}] {task.get('goal', '')} "
            f"— {len(steps)} step(s); {last.get('evidence') or last.get('step', '')}"
        )
    return "\n".join(lines)


def _record(task: dict, state: str, step: str, evidence: str = "") -> None:
    steps = task.setdefault("steps", [])
    steps.append({"at": _now(), "state": state, "step": step, "evidence": evidence})
    if len(steps) > _MAX_STEPS:
        del steps[:-_MAX_STEPS]
    task["updated"] = _now()


def _inspect() -> str:
    """Read native window state.  No screen action or data leaves the machine."""
    active = computer_control({"action": "active_window"})
    windows = computer_control({"action": "list_windows"})
    return f"{active}\n{windows}"


def computer_operator(parameters=None, player=None, **_unused) -> str:
    """Create and maintain an evidence-backed desktop task."""
    params = parameters if isinstance(parameters, dict) else {}
    action = str(params.get("action", "")).strip().lower()
    if action not in {"start", "inspect", "step", "complete", "fail", "status", "cancel", "history"}:
        return "action must be start, inspect, step, complete, fail, status, cancel, or history."

    goal, error = _clean(params.get("goal"), "goal", required=action == "start")
    if error:
        return error
    step, error = _clean(params.get("step"), "step", required=action in {"step", "complete", "fail"})
    if error:
        return error
    evidence, error = _clean(params.get("evidence"), "evidence")
    if error:
        return error

    with _LOCK:
        data = _load()
        task = _active(data)

        if action == "history":
            return _history(data, int(params.get("limit", 10)))

        if action == "start":
            if task:
                return ("A computer task is already active. Finish, fail, or cancel it first.\n"
                        + _summary(task))
            task = {
                "id": f"task-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                "goal": goal,
                "state": "active",
                "started": _now(),
                "updated": _now(),
                "steps": [],
            }
            _record(task, "planned", "Task accepted; inspect the current desktop before the first action.")
            data["active"] = task
            _save(data)
            if player:
                player.write_log(f"TASK: Started — {goal[:100]}")
            return ("TASK STARTED\n" + _summary(task) + "\n"
                    "Next: call computer_operator with action=inspect, then use the appropriate "
                    "specialised tool for one small action. Record its verified result with action=step.")

        if not task:
            return "No active computer task. Start one with the user's complete goal first."

        if action == "status":
            return _summary(task)

        if action == "inspect":
            snapshot = _inspect()
            _record(task, "inspected", "Inspected active and visible windows.", snapshot[:_MAX_TEXT])
            _save(data)
            if player:
                player.write_log("TASK: Desktop inspected.")
            return "DESKTOP INSPECTION\n" + snapshot

        if action == "step":
            _record(task, "verified", step, evidence)
            _save(data)
            if player:
                player.write_log(f"TASK: {step[:110]}")
            return "Step recorded. Continue with the next smallest verified action.\n" + _summary(task)

        if action == "complete":
            _record(task, "completed", step, evidence)
            task["state"] = "completed"
            task["completed"] = _now()
            _archive(data, task)
            data.pop("active", None)
            _save(data)
            if player:
                player.write_log(f"TASK: Completed — {task['goal'][:100]}")
            return "TASK COMPLETED\n" + _summary(task)

        if action == "fail":
            _record(task, "blocked", step, evidence)
            task["state"] = "blocked"
            task["blocker"] = evidence or step
            _archive(data, task)
            data.pop("active", None)
            _save(data)
            if player:
                player.write_log(f"TASK: Blocked — {task['blocker'][:110]}")
            return "TASK BLOCKED\n" + _summary(task)

        # cancel
        _record(task, "cancelled", "User cancelled the task.")
        task["state"] = "cancelled"
        _archive(data, task)
        data.pop("active", None)
        _save(data)
        if player:
            player.write_log("TASK: Cancelled.")
        return "TASK CANCELLED\n" + _summary(task)


TOOL = {
    "name": "computer_operator",
    "description": (
        "Controls a persistent, evidence-backed multi-step desktop task. Use start for a goal with "
        "multiple actions or a result that must be verified; then inspect before acting, record each "
        "verified step, and complete or fail with concrete evidence. This tool never performs clicks, "
        "typing, deletion, sending, installation, payment, or permission changes itself; use the "
        "specialised tool for that action so its confirmation safeguards still apply."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "start | inspect | step | complete | fail | status | cancel | history"},
            "limit": {"type": "INTEGER", "description": "Number of past tasks to show for history (default: 10)."},
            "goal": {"type": "STRING", "description": "Complete user goal; required for start."},
            "step": {"type": "STRING", "description": "Verified action, completion result, or exact blocker."},
            "evidence": {"type": "STRING", "description": "Observed window, screen, tool result, build output, or exact error."},
        },
        "required": ["action"],
    },
    "handler": computer_operator,
}
