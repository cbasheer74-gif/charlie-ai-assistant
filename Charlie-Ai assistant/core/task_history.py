"""Small, privacy-aware audit trail for actions performed by CHARLIE."""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_MAX_EVENTS = 200
_MAX_TEXT = 260
_SENSITIVE = re.compile(r"(?:api[_-]?key|token|secret|password|passphrase|authorization|cookie)\s*[:=]\s*\S+", re.I)


from core.app_paths import get_memory_dir

_LEGACY_STORE = get_memory_dir() / "task_history.json"
_STORE = _LEGACY_STORE  # kept patchable for existing tests


def _store() -> Path:
    """Use profile-private history while preserving test and legacy overrides."""
    if _STORE != _LEGACY_STORE:
        return _STORE
    try:
        from memory.profile_manager import profile_dir
        target = profile_dir() / "task_history.json"
        if not target.exists() and _LEGACY_STORE.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(_LEGACY_STORE, target)
        return target
    except Exception:
        return _LEGACY_STORE


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[private]" if any(word in str(key).lower() for word in
            ("password", "token", "secret", "key", "authorization", "cookie", "text", "content", "fields", "error", "workflow")) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value[:12]]
    text = _SENSITIVE.sub("[redacted]", str(value or ""))
    return text[:_MAX_TEXT] + ("…" if len(text) > _MAX_TEXT else "")


def _load() -> list[dict]:
    try:
        value = json.loads(_store().read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except Exception:
        return []


def _save(events: list[dict]) -> None:
    store = _store()
    store.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix="charlie-history-", suffix=".json", dir=store.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(events[-_MAX_EVENTS:], stream, ensure_ascii=False, indent=2)
        os.replace(temp, store)
    finally:
        if os.path.exists(temp):
            try:
                os.unlink(temp)
            except OSError:
                pass


def record(tool: str, parameters: dict | None, result: object, *, state: str = "completed") -> None:
    """Record a completed tool call. Never lets logging break the actual task."""
    if tool in {"action_history", "save_memory"}:
        return
    try:
        event = {
            "at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "tool": str(tool)[:80],
            "state": state,
            "parameters": _redact(parameters or {}),
            "result": _redact(result),
        }
        with _LOCK:
            events = _load()
            events.append(event)
            _save(events)
    except Exception:
        pass


def recent(limit: int = 20) -> list[dict]:
    with _LOCK:
        return list(reversed(_load()[-max(1, min(int(limit), _MAX_EVENTS)):]))


def summary(limit: int = 20) -> str:
    events = recent(limit)
    if not events:
        return "No recorded CHARLIE actions yet."
    lines = ["CHARLIE action history (newest first):"]
    for index, event in enumerate(events, 1):
        args = event.get("parameters", {})
        compact = ", ".join(f"{k}={v}" for k, v in args.items()) if isinstance(args, dict) else str(args)
        lines.append(f"{index}. [{event.get('state', 'completed')}] {event.get('tool', '?')} — {compact[:180]}")
    return "\n".join(lines)
