"""Two-stage tool discovery gateway for CHARLIE and Gemini Live.

Provides:
- discover_tools: search and return 1-5 candidate specialized tools based on user intent.
- invoke_discovered_tool: securely execute authorized discovered tools via existing dispatch.
- Session-scoped authorization and TTL enforcement.
- Feature flag & pilot mode controls (default disabled for safety).
- Telemetry, readiness validation, and circuit breaker.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from core.tool_groups import (
    TOOL_GROUPS,
    TOOL_TO_GROUP,
    get_core_tools,
    get_tool_group,
    resolve_groups_for_intent,
)

# Feature flags: Discovery is production default; FULL mode is manual override or emergency fallback
TOOL_FORCE_FULL: bool = False
TOOL_DISCOVERY_DEFAULT: bool = True
TOOL_DISCOVERY_GATEWAY_ENABLED: bool = True
TOOL_DISCOVERY_PILOT: bool = True

_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")
_DISCOVERY_TTL_SECONDS: float = 300.0  # 5 minutes bounded authorization window
_MAX_CANDIDATES: int = 5
_MAX_SESSION_ENTRIES: int = 50

# Block recursive or internal gateway calls
_FORBIDDEN_TOOLS: set[str] = {
    "discover_tools",
    "invoke_discovered_tool",
}

# Developer tools requiring explicit developer intent
_RESTRICTED_DEV_TOOLS: set[str] = {
    "antigravity_bridge",
    "ollama_agent",
    "dev_agent",
}

# Destructive tools that require user confirmation via core.confirm
_DESTRUCTIVE_TOOLS: set[str] = {
    "shutdown_charlie",
    "computer_settings",
    "computer_control",
    "file_controller",
    "browser_control",
    "desktop_control",
}

# Domain keyword associations for provider-specific plugin matching
_PLUGIN_KEYWORDS: dict[str, set[str]] = {
    "github_integration": {"github", "repo", "repository", "repositories", "issue", "issues", "pr", "pull"},
    "jira_integration": {"jira", "ticket", "tickets", "sprint"},
    "slack_integration": {"slack", "channel", "channels"},
    "discord_integration": {"discord", "server", "servers"},
    "telegram_integration": {"telegram"},
    "spotify_integration": {"spotify", "music", "song", "playlist", "track"},
    "notion_integration": {"notion", "page", "pages", "database"},
    "trello_integration": {"trello", "board", "boards", "card", "cards"},
    "zoom_integration": {"zoom", "meeting", "meetings", "call", "calls"},
    "google_workspace": {"google", "drive", "docs", "doc", "sheets", "sheet", "gmail", "calendar", "workspace"},
    "microsoft365_integration": {"microsoft", "microsoft365", "office", "office365", "outlook", "onedrive", "teams", "365"},
    "workspace_helper": {"workspace", "helper", "layout"},
    "whatsapp_integration": {"whatsapp"},
}


def is_full_mode_forced() -> bool:
    """Return True if explicit FULL 73-tool mode override is enabled."""
    if TOOL_FORCE_FULL:
        return True
    return os.getenv("CHARLIE_TOOL_FULL", "").strip().lower() in ("1", "true", "yes", "on") or \
           os.getenv("CHARLIE_FULL_TOOLS", "").strip().lower() in ("1", "true", "yes", "on")


def is_discovery_enabled() -> bool:
    """Return True if 17-tool discovery mode is active (production default).

    Precedence:
    1. Explicit manual FULL override (CHARLIE_TOOL_FULL=1) -> False
    2. Default -> True (17-tool DISCOVERY mode)
    """
    if is_full_mode_forced():
        return False
    return TOOL_DISCOVERY_DEFAULT


def is_gateway_enabled() -> bool:
    """Compatibility check: True unless FULL mode is explicitly forced."""
    return is_discovery_enabled()


def is_pilot_enabled() -> bool:
    """Compatibility alias. Returns True unless FULL mode is explicitly forced."""
    return is_discovery_enabled()


# ── Focused In-Memory Telemetry Counters (No Sensitive Data) ───────────────
_TELEMETRY: dict[str, int] = {
    "tool_mode_discovery_sessions": 0,
    "tool_mode_full_sessions": 0,
    "discovery_requests": 0,
    "discovery_successes": 0,
    "discovery_no_match": 0,
    "gateway_invocations": 0,
    "gateway_failures": 0,
    "gateway_security_rejections": 0,
    "discovery_fallback_to_full": 0,
    # Backward compatibility aliases:
    "tool_mode_pilot_sessions": 0,
    "pilot_fallback_to_full": 0,
}


def record_telemetry(metric: str, count: int = 1) -> None:
    """Increment an in-memory telemetry counter safely."""
    if metric in _TELEMETRY:
        _TELEMETRY[metric] += count
    # Synchronize backward compatibility aliases
    if metric == "tool_mode_discovery_sessions":
        _TELEMETRY["tool_mode_pilot_sessions"] += count
    elif metric == "tool_mode_pilot_sessions":
        _TELEMETRY["tool_mode_discovery_sessions"] += count
    elif metric == "discovery_fallback_to_full":
        _TELEMETRY["pilot_fallback_to_full"] += count
    elif metric == "pilot_fallback_to_full":
        _TELEMETRY["discovery_fallback_to_full"] += count


def get_telemetry() -> dict[str, int]:
    """Return a snapshot of current telemetry counters."""
    return dict(_TELEMETRY)


def reset_telemetry() -> None:
    """Reset all in-memory telemetry counters."""
    for k in _TELEMETRY:
        _TELEMETRY[k] = 0


# ── Circuit Breaker for Gateway Infrastructure ────────────────────────────
class GatewayCircuitBreaker:
    """Tracks infrastructure failures and triggers graceful fallback to FULL mode."""

    def __init__(self, max_failures: int = 3) -> None:
        self.max_failures = max_failures
        self.failure_count = 0
        self.fallback_triggered = False

    def record_failure(self, is_infrastructure: bool = True) -> bool:
        """Record an infrastructure failure.

        Returns True if threshold reached and fallback should be initiated.
        """
        if not is_infrastructure:
            return False
        self.failure_count += 1
        if self.failure_count >= self.max_failures and not self.fallback_triggered:
            self.fallback_triggered = True
            return True
        return False

    def reset(self) -> None:
        self.failure_count = 0
        self.fallback_triggered = False


def validate_discovery_readiness(action_registry: Any, plugin_registry: Any = None) -> tuple[bool, str]:
    """Validate prerequisites before connecting Gemini Live in production DISCOVERY mode.

    Returns (True, '') if all prerequisites pass, or (False, reason).
    """
    try:
        # 1. Verify confirmation layer available
        import core.confirm as _confirm
        if not hasattr(_confirm, "request"):
            return False, "Confirmation layer missing request() method"

        # 2. Verify all 15 canonical CORE tools
        core_tools = get_core_tools()
        if len(core_tools) != 15:
            return False, f"Expected 15 CORE tools, got {len(core_tools)}"

        # 3. Verify action registry has the CORE actions
        if action_registry is None:
            return False, "Action registry is not initialized"

        core_actions = {
            "quick_calc", "open_app", "computer_settings", "media_control",
            "voice_control", "file_controller", "web_search", "reminder"
        }
        for act in core_actions:
            if not action_registry.has(act):
                return False, f"Missing critical core action in registry: {act}"

        # 4. Verify gateway declarations
        if not DISCOVERY_TOOL_DECLARATION or not INVOCATION_TOOL_DECLARATION:
            return False, "Discovery/invocation declarations uninitialized"

        # 5. Verify DiscoverySession initialization probe
        probe_session = get_discovery_session("_readiness_probe")
        if probe_session is None:
            return False, "DiscoverySession initialization failed"
        clear_discovery_session("_readiness_probe")

        return True, ""
    except Exception as e:
        return False, f"Validation exception: {e}"


# Backward compatibility alias
validate_pilot_readiness = validate_discovery_readiness


# ── Declarations for Gemini Live ───────────────────────────────────────────
DISCOVERY_TOOL_DECLARATION: dict[str, Any] = {
    "name": "discover_tools",
    "description": (
        "Find specialized tools for a specific task or request that are not in the default core set. "
        "Call this with the user's intent when core tools (open_app, file_controller, web_search, etc.) "
        "do not cover the request. Returns up to 3-5 relevant candidate tools that can be invoked via invoke_discovered_tool."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "intent": {
                "type": "STRING",
                "description": "The specific user task or goal (e.g. 'send WhatsApp message', 'summarize meeting notes', 'fix Python code').",
            },
            "category": {
                "type": "STRING",
                "description": "Optional category hint: FILES | DESKTOP | WEB_EXTENDED | VISION_EXTENDED | DEVELOPER | PRODUCTIVITY | COMMUNICATION | LEISURE | PLUGINS",
            },
        },
        "required": ["intent"],
    },
    "behavior": "BLOCKING",
}

INVOCATION_TOOL_DECLARATION: dict[str, Any] = {
    "name": "invoke_discovered_tool",
    "description": (
        "Execute a specialized tool that was discovered via discover_tools. "
        "Pass the exact tool_name and a JSON-encoded string of arguments. "
        "Only recently discovered tools in this active session or core tools can be invoked."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "tool_name": {
                "type": "STRING",
                "description": "The exact name of the tool to execute.",
            },
            "arguments_json": {
                "type": "STRING",
                "description": "JSON-encoded string of arguments matching the tool's parameter schema (e.g. '{\"message\": \"Hello\", \"recipient\": \"Mom\"}').",
            },
        },
        "required": ["tool_name", "arguments_json"],
    },
    "behavior": "BLOCKING",
}


# ── Session-Scoped Authorization State ─────────────────────────────────────
class DiscoverySession:
    """Tracks session-scoped discovered tool authorizations with bounded TTL."""

    def __init__(self, session_id: str, ttl: float = _DISCOVERY_TTL_SECONDS) -> None:
        self.session_id = session_id
        self.ttl = ttl
        self._authorized: dict[str, float] = {}  # tool_name -> expiry_monotonic

    def authorize(self, tool_name: str) -> None:
        """Authorize a discovered tool for the duration of its TTL."""
        if tool_name in _FORBIDDEN_TOOLS:
            return
        now = time.monotonic()
        self._cleanup(now)
        # Bound entries
        if len(self._authorized) >= _MAX_SESSION_ENTRIES:
            oldest = min(self._authorized.items(), key=lambda x: x[1])[0]
            self._authorized.pop(oldest, None)
        self._authorized[tool_name] = now + self.ttl

    def is_authorized(self, tool_name: str) -> bool:
        """Check if tool is currently authorized (core tools are always authorized)."""
        if tool_name in _FORBIDDEN_TOOLS:
            return False
        if tool_name in get_core_tools():
            return True
        now = time.monotonic()
        expiry = self._authorized.get(tool_name)
        if expiry is None:
            return False
        if now > expiry:
            self._authorized.pop(tool_name, None)
            return False
        return True

    def _cleanup(self, now: float) -> None:
        expired = [k for k, exp in self._authorized.items() if now > exp]
        for k in expired:
            self._authorized.pop(k, None)

    def authorized_list(self) -> list[str]:
        now = time.monotonic()
        self._cleanup(now)
        return list(self._authorized.keys())


_SESSIONS: dict[str, DiscoverySession] = {}


def get_discovery_session(session_id: str = "default") -> DiscoverySession:
    """Obtain or initialize the discovery session for a given session ID."""
    sid = str(session_id or "default")
    session = _SESSIONS.get(sid)
    if session is None:
        session = DiscoverySession(sid)
        _SESSIONS[sid] = session
    return session


def clear_discovery_session(session_id: str = "default") -> None:
    """Clear discovery state on session disconnect or reset."""
    sid = str(session_id or "default")
    _SESSIONS.pop(sid, None)


# ── Discovery Gateway Logic ────────────────────────────────────────────────
def discover_candidates(
    intent: str,
    category: Optional[str] = None,
    session_id: str = "default",
    action_registry: Any = None,
    plugin_registry: Any = None,
    max_results: int = _MAX_CANDIDATES,
) -> list[dict[str, Any]]:
    """Resolve user intent into 1-5 specialized tool candidates.

    Excludes unconfigured plugins, restricted developer tools (unless developer intent),
    and forbidden recursion tools. Authorizes returned candidates for the session.
    """
    record_telemetry("discovery_requests")
    clean_intent = str(intent or "").strip()
    if not clean_intent:
        record_telemetry("discovery_no_match")
        return []

    # 1. Determine relevant tool groups
    groups = resolve_groups_for_intent(clean_intent)
    if category:
        cat_norm = str(category).strip().upper()
        if cat_norm in TOOL_GROUPS:
            groups.add(cat_norm)

    is_dev_intent = "DEVELOPER" in groups

    # 2. Gather candidates from target groups (excluding CORE since CORE is already declared)
    candidates: list[str] = []
    target_groups = groups - {"CORE"}

    for grp in target_groups:
        tools = TOOL_GROUPS.get(grp, set())
        for tool_name in sorted(tools):
            if tool_name in _FORBIDDEN_TOOLS:
                continue
            if tool_name in _RESTRICTED_DEV_TOOLS and not is_dev_intent:
                continue

            # Verify availability in runtime registries if provided
            if plugin_registry is not None and plugin_registry.has(tool_name):
                # Plugins must be enabled AND configured
                if hasattr(plugin_registry, "is_configured") and not plugin_registry.is_configured(tool_name):
                    continue
            elif action_registry is not None and not action_registry.has(tool_name):
                # Skip if not actually installed in action_registry
                continue

            candidates.append(tool_name)

    # 3. Score & filter candidates
    scored: list[tuple[float, str]] = []
    intent_words = set(re.findall(r"\w+", clean_intent.lower()))

    for tool_name in candidates:
        score = 1.0
        # Match name tokens
        name_parts = set(tool_name.lower().split("_"))
        overlap = len(intent_words & name_parts)
        score += overlap * 2.0
        # Boost provider-specific plugins using curated domain keywords
        if tool_name in _PLUGIN_KEYWORDS:
            kw_overlap = len(intent_words & _PLUGIN_KEYWORDS[tool_name])
            score += kw_overlap * 1.5
        scored.append((score, tool_name))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_candidates = [item[1] for item in scored[:max_results]]

    # 4. Authorize in session and build descriptor dicts
    session = get_discovery_session(session_id)
    results: list[dict[str, Any]] = []

    for name in top_candidates:
        session.authorize(name)

        desc = ""
        params: dict = {}
        # Fetch metadata from registry if available
        if action_registry is not None and action_registry.has(name):
            rec = action_registry._actions.get(name)
            if rec:
                desc = rec.description
                params = rec.parameters
        elif plugin_registry is not None and plugin_registry.has(name):
            rec = plugin_registry._plugins.get(name)
            if rec:
                desc = rec.description
                params = rec.parameters

        results.append({
            "tool_name": name,
            "category": get_tool_group(name) or "SPECIALIZED",
            "description": (desc[:180] + "...") if len(desc) > 180 else desc,
            "requires_confirmation": name in _DESTRUCTIVE_TOOLS,
            "parameters": params.get("properties", {}),
        })

    if results:
        record_telemetry("discovery_successes")
    else:
        record_telemetry("discovery_no_match")

    return results


# ── Invocation Gateway Logic ───────────────────────────────────────────────
def execute_discovered_tool(
    tool_name: str,
    arguments_json: str,
    session_id: str = "default",
    action_registry: Any = None,
    plugin_registry: Any = None,
    ctx: Optional[dict] = None,
) -> str:
    """Securely execute a discovered tool through existing dispatch pathways.

    Validates:
    - Recursion blocking
    - Tool name format and path safety
    - Session-scoped discovery authorization (or CORE membership)
    - Valid JSON arguments matching parameter expectations
    - Delegates to action_registry.run / plugin_registry.run
    """
    record_telemetry("gateway_invocations")
    clean_name = str(tool_name or "").strip()

    # 1. Anti-recursion check
    if clean_name in _FORBIDDEN_TOOLS:
        record_telemetry("gateway_security_rejections")
        record_telemetry("gateway_failures")
        return f"Error: Tool '{clean_name}' cannot be invoked via gateway."

    # 2. Syntax & traversal safety
    if not _NAME_RE.match(clean_name) or ".." in clean_name or "/" in clean_name or "\\" in clean_name:
        record_telemetry("gateway_security_rejections")
        record_telemetry("gateway_failures")
        return f"Error: Invalid tool name format: '{clean_name}'."

    # 3. Session authorization check
    session = get_discovery_session(session_id)
    if not session.is_authorized(clean_name):
        record_telemetry("gateway_security_rejections")
        record_telemetry("gateway_failures")
        return f"Error: Tool '{clean_name}' has not been discovered in this session or authorization expired."

    # 4. JSON parsing & validation
    if isinstance(arguments_json, dict):
        args = arguments_json
    else:
        raw_str = str(arguments_json or "").strip()
        if not raw_str:
            args = {}
        else:
            try:
                parsed = json.loads(raw_str)
                if not isinstance(parsed, dict):
                    record_telemetry("gateway_failures")
                    return "Error: arguments_json must be a JSON object dictionary."
                args = parsed
            except Exception as json_err:
                record_telemetry("gateway_failures")
                return f"Error: Failed to parse arguments_json: {json_err}"

    # 5. Schema check against declaration if available
    target_rec = None
    if action_registry is not None and action_registry.has(clean_name):
        target_rec = action_registry._actions.get(clean_name)
    elif plugin_registry is not None and plugin_registry.has(clean_name):
        target_rec = plugin_registry._plugins.get(clean_name)

    if target_rec:
        required_fields = target_rec.parameters.get("required", [])
        for req in required_fields:
            if req not in args:
                record_telemetry("gateway_failures")
                return f"Error: Missing required argument '{req}' for tool '{clean_name}'."

    # 6. Delegate execution directly to existing execution layer
    try:
        if action_registry is not None and action_registry.has(clean_name):
            return str(action_registry.run(clean_name, args, ctx or {}) or "Done.")
        if plugin_registry is not None and plugin_registry.has(clean_name):
            player = (ctx or {}).get("player")
            session_mem = (ctx or {}).get("session_memory")
            return str(plugin_registry.run(clean_name, args, player=player, session_memory=session_mem) or "Done.")
        if clean_name == "system_status":
            try:
                from actions.system_monitor import get_system_status
                return json.dumps(get_system_status(), indent=2)
            except Exception as e:
                return f"Error getting system status: {e}"
        record_telemetry("gateway_failures")
        return f"Error: Discovered tool '{clean_name}' is not currently available in runtime."
    except Exception as exec_err:
        record_telemetry("gateway_failures")
        return f"Tool '{clean_name}' execution failed: {exec_err}"
