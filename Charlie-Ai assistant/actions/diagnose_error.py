"""Evidence-first diagnostics for local projects, logs, and error messages."""

from __future__ import annotations

import os
import re
from pathlib import Path

_MAX_READ = 12_000
_MAX_ITEMS = 30
_SENSITIVE_NAME = re.compile(r"(?:^|[_-])(secret|token|password|credential|api[_-]?key)(?:[_-]|$)", re.I)
_SECRET_VALUE = re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)\s*([:=])\s*[^\s]+")
_TEXT_SUFFIXES = {".log", ".txt", ".md", ".json", ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".yaml", ".yml", ".toml", ".ini", ".xml", ".csv"}


def _safe_path(raw: object) -> Path | None:
    text = str(raw or "").strip().strip('"')
    if not text or text.startswith("\\\\"):
        return None
    try:
        path = Path(text).expanduser().resolve()
    except (OSError, RuntimeError):
        return None
    windows = Path(os.environ.get("WINDIR", r"C:\\Windows")).resolve()
    if path == windows or windows in path.parents:
        return None
    return path


def _redact(text: str) -> str:
    return _SECRET_VALUE.sub(lambda match: f"{match.group(1)}{match.group(2)} [redacted]", text)


def _tail(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"Could not read {path.name}: {exc}"
    text = _redact(text)
    return text[-_MAX_READ:] if len(text) > _MAX_READ else text


def _inspect_project(path: Path) -> str:
    if not path.exists():
        return f"Path not found: {path}"
    if path.is_file():
        if _SENSITIVE_NAME.search(path.stem):
            return "That file appears to contain credentials, so diagnosis will not read it."
        return f"File: {path.name}\n\n{_tail(path)}"

    interesting, logs, scanned = [], [], 0
    manifests = {"package.json", "pyproject.toml", "requirements.txt", "composer.json", "cargo.toml", "pom.xml", "go.mod"}
    try:
        for item in path.rglob("*"):
            scanned += 1
            if scanned > 2_500 or (len(interesting) >= _MAX_ITEMS and len(logs) >= 5):
                break
            if any(part in {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__"} for part in item.parts):
                continue
            if not item.is_file() or _SENSITIVE_NAME.search(item.stem):
                continue
            relative = item.relative_to(path)
            if item.name.lower() in manifests or item.suffix.lower() in {".py", ".js", ".ts", ".tsx", ".jsx"}:
                if len(interesting) < _MAX_ITEMS:
                    interesting.append(str(relative))
            if item.suffix.lower() in {".log", ".txt"} and ("error" in item.name.lower() or "log" in item.name.lower()):
                if len(logs) < 5:
                    logs.append(relative)
    except Exception as exc:
        return f"Could not inspect project: {exc}"
    result = [f"Project: {path}", "Relevant files:"]
    result.extend(f"- {item}" for item in interesting) if interesting else result.append("- No common source or manifest files found.")
    if logs:
        result.append("Possible logs:")
        result.extend(f"- {item}" for item in logs)
    return "\n".join(result)


def diagnose_error(parameters: dict | None = None, player=None, **_unused) -> str:
    params = parameters or {}
    action = str(params.get("action", "")).strip().lower()
    path = _safe_path(params.get("path"))
    error = _redact(str(params.get("error", "")).strip())

    if action == "inspect_project":
        if path is None:
            return "Provide a local project path. Network paths and Windows system folders are not inspected."
        result = _inspect_project(path)
    elif action == "read_log":
        if path is None or not path.is_file():
            return "Provide the local log file path to read."
        if _SENSITIVE_NAME.search(path.stem):
            return "That file appears to contain credentials, so diagnosis will not read it."
        result = f"Log tail: {path.name}\n\n{_tail(path)}"
    elif action == "analyze":
        if not error:
            return "Provide the exact error message or stack trace to analyze."
        context = _inspect_project(path) if path else "No project path was supplied."
        result = f"Exact error:\n{error[:_MAX_READ]}\n\nLocal context:\n{context}"
    else:
        return "action must be inspect_project, read_log, or analyze."

    if player:
        player.write_log(f"DIAGNOSIS: {action}")
    return result


TOOL = {
    "name": "diagnose_error",
    "description": "Read-only, evidence-first diagnosis for local projects, logs, and exact error messages. It redacts likely secrets and never changes code. Use it before suggesting or fixing a coding problem; after the user explicitly asks to fix it, use the evidence to make the smallest undoable change and verify it.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "inspect_project | read_log | analyze"},
            "path": {"type": "STRING", "description": "Local project directory or log file path."},
            "error": {"type": "STRING", "description": "Exact error text or stack trace for analyze."},
        },
        "required": ["action"],
    },
    "handler": diagnose_error,
}
