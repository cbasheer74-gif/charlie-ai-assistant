"""Shared runtime state for live Teach Mode recording.

The workflow compiler already knows how to turn semantic events into skills.
This module provides the missing bridge between that compiler and the live
action dispatcher while keeping recording state out of the UI and model.
"""

from __future__ import annotations

import copy
import re
import threading
from typing import Any, Dict

from engine.db import redact_secrets
from engine.skills.recorder import WorkflowRecorder


_LOCK = threading.RLock()
_RECORDER = WorkflowRecorder()
_MAX_VALUE_CHARS = 2_000
_SENSITIVE_PARTS = ("password", "passwd", "secret", "token", "api_key", "apikey")


def get_recorder() -> WorkflowRecorder:
    """Return the process-wide recorder used by the live action dispatcher."""
    return _RECORDER


def _safe_value(value: Any, key: str = "") -> Any:
    """Make recorded values bounded and ensure credentials never reach storage."""
    lowered = key.casefold()
    if any(part in lowered for part in _SENSITIVE_PARTS):
        variable = re.sub(r"[^A-Z0-9]+", "_", key.upper()).strip("_") or "REQUIRED_SECRET"
        return "{" + variable + "}"
    if isinstance(value, dict):
        return {str(k): _safe_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_value(item, key) for item in value[:100]]
    if isinstance(value, str):
        value = redact_secrets(value)
        if len(value) > _MAX_VALUE_CHARS:
            return value[:_MAX_VALUE_CHARS] + "..."
        return value
    try:
        return copy.deepcopy(value)
    except Exception:
        return str(value)[:_MAX_VALUE_CHARS]


def _adapter_for(tool_name: str) -> str:
    low = tool_name.casefold()
    if "excel" in low or "sheet" in low:
        return "ExcelAdapter"
    if "browser" in low or "web" in low or "youtube" in low:
        return "BrowserAdapter"
    if "file" in low:
        return "FileAdapter"
    if "code" in low or "dev" in low or "diagnose" in low:
        return "CodingAdapter"
    if "video" in low:
        return "VideoAdapter"
    return "JarvisActionAdapter"


def is_recording() -> bool:
    with _LOCK:
        return _RECORDER.is_recording()


def status() -> Dict[str, Any]:
    with _LOCK:
        session = _RECORDER.get_current_session()
        if not session:
            return {"recording": False, "event_count": 0}
        return {
            "recording": True,
            "session_id": session.session_id,
            "intent": session.intent,
            "name": session.skill_name_hint,
            "event_count": len(session.events),
            "started_at": session.started_at,
        }


def cancel() -> bool:
    with _LOCK:
        if not _RECORDER.is_recording():
            return False
        _RECORDER.stop_teach_mode()
        return True


def record_tool_call(tool_name: str, parameters: dict, result: Any, succeeded: bool) -> bool:
    """Capture one completed live tool call as a reusable semantic step."""
    if tool_name == "manage_skills" or not succeeded:
        return False
    with _LOCK:
        if not _RECORDER.is_recording():
            return False
        return _RECORDER.record_action(
            action=tool_name,
            adapter=_adapter_for(tool_name),
            tool=tool_name,
            target_element=tool_name.replace("_", " ").title(),
            inputs=_safe_value(parameters or {}),
            outputs={"result": _safe_value(result)},
            app_state={"status": "completed"},
        )
