"""Central tool-group registry and contextual exposure infrastructure for CHARLIE.

Defines tool groups across all core, action, and plugin tools.
Provides safe group resolution, validation, schema measurement, and shadow-mode helpers
without modifying existing tool schemas or changing production behavior.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

# Master toggle for contextual tool filtering (defaults to False: Shadow Mode)
CONTEXTUAL_TOOLS_ENABLED: bool = False


def is_contextual_tools_enabled() -> bool:
    """Return True if contextual tool filtering is active in production.
    Defaults to False (Shadow Mode) unless explicitly set in environment or config.
    """
    if CONTEXTUAL_TOOLS_ENABLED:
        return True
    env_val = os.getenv("CHARLIE_CONTEXTUAL_TOOLS", "").strip().lower()
    return env_val in ("1", "true", "yes", "on")


# ── Canonical Tool Groups ──────────────────────────────────────────────────
# All 73 registered tools mapped to exactly one primary group.
TOOL_GROUPS: dict[str, set[str]] = {
    "CORE": {
        "system_status",
        "undo",
        "save_memory",
        "recall_memory",
        "quick_calc",
        "open_app",
        "computer_settings",
        "media_control",
        "voice_control",
        "screen_process",
        "close_camera",
        "file_controller",
        "web_search",
        "reminder",
        "shutdown_charlie",
    },
    "FILES": {
        "file_catalog",
        "file_organizer",
        "file_processor",
        "excel_worker",
    },
    "DESKTOP": {
        "computer_control",
        "computer_operator",
        "desktop_control",
        "clipboard_manager",
    },
    "WEB_EXTENDED": {
        "browser_control",
        "page_summarizer",
        "flight_finder",
    },
    "VISION_EXTENDED": {
        "camera_scanner",
        "screen_ocr",
        "screen_explainer",
    },
    "DEVELOPER": {
        "dev_agent",
        "code_helper",
        "antigravity_bridge",
        "ollama_agent",
        "workflow_runner",
    },
    "PRODUCTIVITY": {
        "meeting_notes",
        "personal_hub",
        "pro_tasks",
        "writing_polish",
        "task_planner",
        "routine_briefing",
        "focus_timer",
        "rag_search",
        "resume_builder",
    },
    "COMMUNICATION": {
        "send_message",
        "email_dictation",
    },
    "SYSTEM_EXTENDED": {
        "security_control",
        "voice_speed",
    },
    "LEISURE": {
        "game_room",
        "game_updater",
        "kids_activity",
        "video_studio",
        "youtube_video",
        "weather_report",
    },
    "ADMIN_DIAGNOSTICS": {
        "manage_monitor",
        "action_history",
        "diagnose_error",
        "manage_skills",
        "learning_brain",
        "remember_correction",
        "autonomous_work",
    },
    "PLUGINS": {
        "discord_integration",
        "github_integration",
        "google_workspace",
        "jira_integration",
        "microsoft365_integration",
        "notion_integration",
        "slack_integration",
        "spotify_integration",
        "telegram_integration",
        "trello_integration",
        "whatsapp_integration",
        "workspace_helper",
        "zoom_integration",
    },
}

# Reverse lookup: tool_name -> group_name
TOOL_TO_GROUP: dict[str, str] = {}
for _group, _tools in TOOL_GROUPS.items():
    for _t in _tools:
        TOOL_TO_GROUP[_t] = _group


def get_tool_group(tool_name: str) -> Optional[str]:
    """Return the group name for a given tool, or None if unmapped."""
    return TOOL_TO_GROUP.get(tool_name)


def get_tools_for_group(group: str) -> set[str]:
    """Return all tool names assigned to a given group (case-insensitive)."""
    norm = str(group or "").strip().upper()
    return set(TOOL_GROUPS.get(norm, set()))


def get_core_tools() -> set[str]:
    """Return the 15 canonical always-available CORE tools."""
    return set(TOOL_GROUPS["CORE"])


def get_tools_for_groups(groups: Iterable[str], include_core: bool = True) -> set[str]:
    """Combine tool names across multiple groups, optionally including CORE."""
    result: set[str] = set()
    if include_core:
        result.update(get_core_tools())
    for g in groups:
        norm = str(g or "").strip().upper()
        if norm in TOOL_GROUPS:
            result.update(TOOL_GROUPS[norm])
    return result


# ── Deterministic Intent / Group Resolver (Shadow Mode) ────────────────────
# Lightweight keyword & regex patterns to detect domain intents without replacing LLM.
_INTENT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("FILES", re.compile(
        r"\b(pdf|docx?|xlsx?|csv|spreadsheet|sheets?|organize\s+downloads|tidy\s+desktop|"
        r"rename\s+file|find\s+invoice|invoice|documents?|files?|folders?|directory|"
        r"clean\s+up\s+files|delete\s+file|move\s+file)\b",
        re.IGNORECASE,
    )),
    ("DESKTOP", re.compile(
        r"\b(open\s+chrome|open\s+app|click|mouse|drag|windows?|switch\s+window|"
        r"focus\s+window|active\s+window|keyboard\s+shortcut|type\s+text|"
        r"paste\s+clipboard|clipboard|hotkeys?)\b",
        re.IGNORECASE,
    )),
    ("WEB_EXTENDED", re.compile(
        r"\b(browse|websites?|web\s*pages?|new\s+tab|close\s+tab|summarize\s+page|"
        r"flights?|book\s+flight|search\s+the\s+web|web\s+search)\b",
        re.IGNORECASE,
    )),
    ("VISION_EXTENDED", re.compile(
        r"\b(screenshots?|read\s+screen|read\s+this\s+screenshot|ocr|scan\s+camera|"
        r"camera\s+scanner|read\s+text\s+on\s+screen|screen\s+explainer|describe\s+screen)\b",
        re.IGNORECASE,
    )),
    ("DEVELOPER", re.compile(
        r"\b(python|code|debug|errors?|tracebacks?|git|github\s+issue|scripts?|"
        r"terminals?|compile|fix\s+this\s+error|developer|syntax\s+error|pull\s+request)\b",
        re.IGNORECASE,
    )),
    ("COMMUNICATION", re.compile(
        r"\b(whats?app|telegram|slack|discord|emails?|dictate\s+email|"
        r"send\s+message|messages?|chats?|send\s+email)\b",
        re.IGNORECASE,
    )),
    ("LEISURE", re.compile(
        r"\b(games?|steam|update\s+game|trivia|kids?|story\s+for\s+kids|"
        r"video\s+studio|video\s+edit|youtube)\b",
        re.IGNORECASE,
    )),
    ("PRODUCTIVITY", re.compile(
        r"\b(meetings?|meeting\s+notes|resumes?|polish\s+writing|routine|planner|"
        r"focus\s+timer|pomodoro|task\s+planner)\b",
        re.IGNORECASE,
    )),
    ("SYSTEM_EXTENDED", re.compile(
        r"\b(antivirus|security\s+scan|voice\s+speed|talk\s+faster|talk\s+slower)\b",
        re.IGNORECASE,
    )),
    ("ADMIN_DIAGNOSTICS", re.compile(
        r"\b(diagnos(?:e|is|tics?)|error\s+logs?|debug\s+logs?|action\s+history|manage\s+skills)\b",
        re.IGNORECASE,
    )),
    ("PLUGINS", re.compile(
        r"\b(github|repo|repositories|repository|"
        r"slack|discord|telegram|"
        r"spotify|"
        r"notion|"
        r"jira|"
        r"trello|"
        r"zoom\s+meetings?|zoom\s+calls?|\bzoom\b|"
        r"google\s+workspace|google\s+drive|google\s+docs?|google\s+sheets?|google\s+calendar|gmail|"
        r"microsoft\s*365|office\s*365|onedrive|ms\s*teams|"
        r"workspace\s+helpers?|workspace\s+layouts?|"
        r"whatsapp\s+(?:cloud|api|plugin|integration|business))\b",
        re.IGNORECASE,
    )),
]


def resolve_groups_for_intent(text: str) -> set[str]:
    """Predict likely tool groups needed for a user utterance in shadow mode.

    Returns:
        Set of group names. Always includes 'CORE'.
        If no specialized domain pattern is confidently identified, returns {'CORE'}.
    """
    clean_text = str(text or "").strip()
    if not clean_text:
        return {"CORE"}

    matched: set[str] = {"CORE"}
    for group_name, pattern in _INTENT_PATTERNS:
        if pattern.search(clean_text):
            matched.add(group_name)

    return matched


# ── Validation & Integrity Checks ──────────────────────────────────────────
def validate_tool_registry(all_available_tool_names: Iterable[str]) -> dict[str, Any]:
    """Validate runtime tools against the central group registry.

    Checks:
    - unmapped: runtime tools missing from any group.
    - missing_tools: tools registered in group registry but absent from runtime.
    - core_intact: all 15 canonical CORE tools are available.
    - is_valid: True if no unmapped tools and CORE is intact.
    """
    available_set = set(all_available_tool_names)
    registry_tools: set[str] = set()
    for tools in TOOL_GROUPS.values():
        registry_tools.update(tools)

    unmapped = sorted(list(available_set - registry_tools))
    missing_tools = sorted(list(registry_tools - available_set))
    core_missing = sorted(list(TOOL_GROUPS["CORE"] - available_set))

    warnings: list[str] = []
    if unmapped:
        warnings.append(f"Tools missing from group registry: {unmapped}")
    if missing_tools:
        warnings.append(f"Tools declared in registry but not present in runtime: {missing_tools}")
    if core_missing:
        warnings.append(f"CRITICAL: CORE tools missing from runtime: {core_missing}")

    return {
        "is_valid": len(unmapped) == 0 and len(core_missing) == 0,
        "unmapped": unmapped,
        "missing_tools": missing_tools,
        "core_missing": core_missing,
        "warnings": warnings,
        "total_available": len(available_set),
        "total_registered": len(registry_tools),
    }


# ── Schema Measurement Helper ──────────────────────────────────────────────
def measure_schema_size(declarations: list[dict]) -> dict[str, int]:
    """Measure serialized JSON schema size in characters and bytes without inventing token counts."""
    count = len(declarations)
    try:
        raw_json = json.dumps(declarations, ensure_ascii=False)
        chars = len(raw_json)
        bytes_count = len(raw_json.encode("utf-8"))
    except Exception:
        chars = 0
        bytes_count = 0
    return {
        "count": count,
        "json_chars": chars,
        "json_bytes": bytes_count,
    }
