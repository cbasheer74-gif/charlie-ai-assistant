"""Safe project-folder inspection plugin for CHARLIE.

This plugin is intentionally read-only. It gives the assistant a dependable
way to answer "what is in my project folder?" without replacing the existing
file-controller actions that handle requested changes.
"""
from __future__ import annotations

import os
from pathlib import Path

from memory.config_manager import get_plugin_config


PLUGIN = {
    "name": "workspace_helper",
    "description": (
        "Inspect the user's configured project workspace and report its files, "
        "folders, and basic size. Use when the user asks what is in their "
        "project folder, wants to inspect a workspace, or asks for a workspace "
        "summary. This plugin is read-only; use file_controller for changes."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "request": {
                "type": "STRING",
                "description": "What workspace information the user wants",
            },
        },
        "required": [],
    },
}


PLUGIN_SETTINGS = {
    "namespace": "workspace_helper",
    "title": "Workspace Helper",
    "fields": [
        {
            "key": "workspace_path",
            "label": "Project folder",
            "type": "text",
            "default": "",
            "placeholder": r"C:\Projects\MyApp (blank = current folder)",
        },
        {
            "key": "max_items",
            "label": "Maximum items to report",
            "type": "text",
            "default": "24",
        },
        {
            "key": "include_hidden",
            "label": "Include hidden files",
            "type": "toggle",
            "default": False,
        },
    ],
    "action": {"label": "TEST WORKSPACE", "run": lambda: _test_workspace()},
}


def _settings() -> tuple[Path, int, bool]:
    values = get_plugin_config("workspace_helper")
    raw_path = str(values.get("workspace_path") or "").strip().strip('"')
    root = Path(raw_path).expanduser() if raw_path else Path.cwd()
    try:
        limit = max(5, min(100, int(values.get("max_items", 24))))
    except (TypeError, ValueError):
        limit = 24
    return root, limit, bool(values.get("include_hidden", False))


def _test_workspace() -> str:
    root, _, _ = _settings()
    return f"Workspace is ready: {root}" if root.is_dir() else f"Folder not found: {root}"


def run(parameters: dict, player=None, session_memory=None) -> str:
    """Return a compact, spoken-friendly read-only workspace summary."""
    root, limit, include_hidden = _settings()
    try:
        if not root.is_dir():
            return f"I can't find the configured workspace folder: {root}"

        entries = []
        total_bytes = 0
        for entry in root.iterdir():
            if not include_hidden and entry.name.startswith("."):
                continue
            try:
                if entry.is_file():
                    total_bytes += entry.stat().st_size
                entries.append(entry)
            except OSError:
                continue
        entries.sort(key=lambda p: (not p.is_dir(), p.name.lower()))
        shown = entries[:limit]
        names = [f"{p.name}/" if p.is_dir() else p.name for p in shown]
        suffix = f" plus {len(entries) - limit} more" if len(entries) > limit else ""
        size_mb = total_bytes / (1024 * 1024)
        request = str(parameters.get("request") or "").strip()
        prefix = f"For {request}, " if request else ""
        result = (
            f"{prefix}the workspace {root.name or str(root)} has {len(entries)} items "
            f"and about {size_mb:.1f} megabytes of files. "
            f"Here are the first {len(names)}: {', '.join(names)}{suffix}."
        )
        if player:
            try:
                player.write_log(f"CHARLIE: Workspace inspected — {root}")
            except Exception:
                pass
        return result
    except (OSError, PermissionError) as exc:
        return f"I couldn't inspect that workspace folder: {exc}"
