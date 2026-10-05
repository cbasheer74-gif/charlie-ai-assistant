"""Comprehensive tests for Phase 3 Step 15: Controlled 17-tool pilot workflows,
startup validation, circuit breaker fallback, and security guarantees.
"""

from __future__ import annotations

import json
import time
import unittest
from unittest.mock import MagicMock, patch

from core.action_loader import ActionRecord, ActionRegistry
from core.plugin_loader import PluginRecord, PluginRegistry
from core.tool_gateway import (
    DISCOVERY_TOOL_DECLARATION,
    INVOCATION_TOOL_DECLARATION,
    DiscoverySession,
    GatewayCircuitBreaker,
    clear_discovery_session,
    discover_candidates,
    execute_discovered_tool,
    get_discovery_session,
    get_telemetry,
    record_telemetry,
    reset_telemetry,
    validate_pilot_readiness,
)
from core.tool_groups import get_core_tools


class TestPilotGatewayWorkflows(unittest.TestCase):
    """Test all pilot real-session workflows A through N."""

    def setUp(self):
        reset_telemetry()
        clear_discovery_session("session_alpha")
        clear_discovery_session("session_beta")

        self.mock_actions = {
            "open_app": ActionRecord(
                name="open_app",
                description="Launch or switch to any desktop application.",
                parameters={"type": "OBJECT", "properties": {"app_name": {"type": "STRING"}}, "required": ["app_name"]},
                handler=lambda app_name, **kw: f"Opened {app_name}",
                valid=True,
            ),
            "web_search": ActionRecord(
                name="web_search",
                description="Search the web for real-time information.",
                parameters={"type": "OBJECT", "properties": {"query": {"type": "STRING"}}, "required": ["query"]},
                handler=lambda query, **kw: f"Search results for: {query}",
                valid=True,
            ),
            "send_message": ActionRecord(
                name="send_message",
                description="Send a message on WhatsApp or Telegram to a contact.",
                parameters={"type": "OBJECT", "properties": {"message": {"type": "STRING"}}, "required": ["message"]},
                handler=lambda message, **kw: f"Message sent: {message}",
                valid=True,
            ),
            "code_helper": ActionRecord(
                name="code_helper",
                description="Analyze, fix, or review code in Python, JavaScript, etc.",
                parameters={"type": "OBJECT", "properties": {"code": {"type": "STRING"}}, "required": ["code"]},
                handler=lambda code, **kw: f"Code fixed: {code}",
                valid=True,
            ),
            "meeting_notes": ActionRecord(
                name="meeting_notes",
                description="Generate structured summary, action items, and key decisions from meeting transcript.",
                parameters={"type": "OBJECT", "properties": {"transcript": {"type": "STRING"}}, "required": ["transcript"]},
                handler=lambda transcript, **kw: f"Meeting notes created: {transcript[:20]}",
                valid=True,
            ),
            "file_controller": ActionRecord(
                name="file_controller",
                description="Manage local files and folders. Delete requires confirmation.",
                parameters={"type": "OBJECT", "properties": {"action": {"type": "STRING"}}, "required": ["action"]},
                handler=lambda action, **kw: "[CONFIRMATION_PENDING] Delete file?" if action == "delete" else f"File action: {action}",
                valid=True,
            ),
            "computer_settings": ActionRecord(
                name="computer_settings",
                description="Control system settings. Shutdown and restart put a confirmation on screen.",
                parameters={"type": "OBJECT", "properties": {"action": {"type": "STRING"}}, "required": ["action"]},
                handler=lambda action, **kw: "[CONFIRMATION_PENDING] Confirm shutdown" if action == "shutdown" else f"Setting: {action}",
                valid=True,
            ),
            "quick_calc": ActionRecord(name="quick_calc", description="calc", parameters={"type": "OBJECT"}, valid=True),
            "media_control": ActionRecord(name="media_control", description="media", parameters={"type": "OBJECT"}, valid=True),
            "voice_control": ActionRecord(name="voice_control", description="voice", parameters={"type": "OBJECT"}, valid=True),
            "reminder": ActionRecord(name="reminder", description="reminder", parameters={"type": "OBJECT"}, valid=True),
        }
        self.action_registry = ActionRegistry(self.mock_actions, logger=lambda _: None)

        self.mock_plugins = {
            "spotify_integration": PluginRecord(
                name="spotify_integration",
                description="Control Spotify music.",
                parameters={"type": "OBJECT", "properties": {"command": {"type": "STRING"}}},
                run=lambda **kw: "Spotify playing",
                valid=True,
                settings={"namespace": "spotify_integration", "fields": [{"key": "client_id"}]},
            ),
            "github_integration": PluginRecord(
                name="github_integration",
                description="Manage GitHub repositories and issues.",
                parameters={"type": "OBJECT", "properties": {"action": {"type": "STRING"}}},
                run=lambda **kw: "GitHub action",
                valid=True,
                settings={"namespace": "github_integration", "fields": [{"key": "token"}]},
            ),
        }
        self.plugin_registry = PluginRegistry(self.mock_plugins, logger=lambda _: None)

    def tearDown(self):
        clear_discovery_session("session_alpha")
        clear_discovery_session("session_beta")

    # TEST A: CORE Direct (open_app)
    def test_core_direct_open_app(self):
        session = get_discovery_session("session_alpha")
        self.assertTrue(session.is_authorized("open_app"))
        res = execute_discovered_tool(
            "open_app",
            json.dumps({"app_name": "Chrome"}),
            session_id="session_alpha",
            action_registry=self.action_registry,
        )
        self.assertEqual(res, "Opened Chrome")

    # TEST B: CORE Direct Web Search
    def test_core_direct_web_search(self):
        session = get_discovery_session("session_alpha")
        self.assertTrue(session.is_authorized("web_search"))
        res = execute_discovered_tool(
            "web_search",
            json.dumps({"query": "Python 3.14 features"}),
            session_id="session_alpha",
            action_registry=self.action_registry,
        )
        self.assertEqual(res, "Search results for: Python 3.14 features")

    # TEST C: Specialized Communication Discovery + Invocation
    def test_specialized_communication_discovery_and_invocation(self):
        candidates = discover_candidates(
            intent="Send a WhatsApp message",
            session_id="session_alpha",
            action_registry=self.action_registry,
            plugin_registry=self.plugin_registry,
        )
        names = [c["tool_name"] for c in candidates]
        self.assertIn("send_message", names)

        # Invoke
        res = execute_discovered_tool(
            "send_message",
            json.dumps({"message": "Hello from pilot test"}),
            session_id="session_alpha",
            action_registry=self.action_registry,
        )
        self.assertEqual(res, "Message sent: Hello from pilot test")

    # TEST D: Developer Discovery + Invocation
    def test_developer_discovery_and_invocation(self):
        candidates = discover_candidates(
            intent="Help diagnose this Python error",
            session_id="session_alpha",
            action_registry=self.action_registry,
        )
        names = [c["tool_name"] for c in candidates]
        self.assertIn("code_helper", names)

        res = execute_discovered_tool(
            "code_helper",
            json.dumps({"code": "def foo(): pass"}),
            session_id="session_alpha",
            action_registry=self.action_registry,
        )
        self.assertEqual(res, "Code fixed: def foo(): pass")

    # TEST E: Productivity Discovery + Invocation
    def test_productivity_discovery_and_invocation(self):
        candidates = discover_candidates(
            intent="Create meeting notes",
            session_id="session_alpha",
            action_registry=self.action_registry,
        )
        names = [c["tool_name"] for c in candidates]
        self.assertIn("meeting_notes", names)

        res = execute_discovered_tool(
            "meeting_notes",
            json.dumps({"transcript": "Discussed roadmap items for Q4."}),
            session_id="session_alpha",
            action_registry=self.action_registry,
        )
        self.assertIn("Meeting notes created", res)

    # TEST F & G: Configured vs Unconfigured Plugin Filtering
    def test_plugin_configured_filtering(self):
        with patch.object(self.plugin_registry, "is_configured") as mock_conf:
            mock_conf.side_effect = lambda name: name == "spotify_integration"

            # Spotify is configured -> should appear on music intent
            candidates_music = discover_candidates(
                intent="play music on spotify",
                session_id="session_alpha",
                plugin_registry=self.plugin_registry,
            )
            self.assertIn("spotify_integration", [c["tool_name"] for c in candidates_music])

            # GitHub is unconfigured -> must NOT appear
            candidates_git = discover_candidates(
                intent="check github repository issues",
                session_id="session_alpha",
                plugin_registry=self.plugin_registry,
            )
            self.assertNotIn("github_integration", [c["tool_name"] for c in candidates_git])

    # TEST H: Destructive File Operation (Requires Confirmation)
    def test_destructive_file_operation_requires_confirmation(self):
        res = execute_discovered_tool(
            "file_controller",
            json.dumps({"action": "delete"}),
            session_id="session_alpha",
            action_registry=self.action_registry,
        )
        self.assertIn("[CONFIRMATION_PENDING]", res)

    # TEST I: Destructive System Operation (Requires Confirmation)
    def test_destructive_system_operation_requires_confirmation(self):
        res = execute_discovered_tool(
            "computer_settings",
            json.dumps({"action": "shutdown"}),
            session_id="session_alpha",
            action_registry=self.action_registry,
        )
        self.assertIn("[CONFIRMATION_PENDING]", res)

    # TEST J & K: Malicious / Invalid Tool Rejection
    def test_malicious_and_invalid_tool_names_rejected(self):
        res_trav = execute_discovered_tool("../../os.system", "{}", session_id="session_alpha")
        self.assertIn("Error: Invalid tool name format", res_trav)

        res_eval = execute_discovered_tool("eval", "{}", session_id="session_alpha")
        self.assertIn("Error: Tool 'eval' has not been discovered", res_eval)

    # TEST L: Cross-Session Isolation
    def test_cross_session_isolation(self):
        discover_candidates(
            intent="Send a WhatsApp message",
            session_id="session_alpha",
            action_registry=self.action_registry,
        )
        # Authorized in session_alpha
        session_a = get_discovery_session("session_alpha")
        self.assertTrue(session_a.is_authorized("send_message"))

        # NOT authorized in session_beta
        session_b = get_discovery_session("session_beta")
        self.assertFalse(session_b.is_authorized("send_message"))

        res_b = execute_discovered_tool(
            "send_message",
            json.dumps({"message": "hijack"}),
            session_id="session_beta",
            action_registry=self.action_registry,
        )
        self.assertIn("Error: Tool 'send_message' has not been discovered", res_b)

    # TEST M: TTL Expiration
    def test_ttl_expiration(self):
        session = DiscoverySession("session_ttl", ttl=0.1)
        session.authorize("send_message")
        self.assertTrue(session.is_authorized("send_message"))

        time.sleep(0.15)
        self.assertFalse(session.is_authorized("send_message"))

    # TEST N: Reconnect Authorization Reset
    def test_reconnect_authorization_reset(self):
        discover_candidates(
            intent="Send a WhatsApp message",
            session_id="session_alpha",
            action_registry=self.action_registry,
        )
        session = get_discovery_session("session_alpha")
        self.assertTrue(session.is_authorized("send_message"))

        # Reconnect event clears discovery session
        clear_discovery_session("session_alpha")
        fresh_session = get_discovery_session("session_alpha")
        self.assertFalse(fresh_session.is_authorized("send_message"))

    # Multi-Tool Workflow Test
    def test_multi_tool_workflow_preserves_authorizations(self):
        # 1. Discover file tools
        cand_files = discover_candidates(
            intent="find my invoice PDF",
            session_id="session_alpha",
            action_registry=self.action_registry,
        )
        # 2. Discover messaging tools
        cand_msg = discover_candidates(
            intent="prepare it to send on WhatsApp",
            session_id="session_alpha",
            action_registry=self.action_registry,
        )

        session = get_discovery_session("session_alpha")
        # send_message should remain authorized
        self.assertTrue(session.is_authorized("send_message"))
        self.assertTrue(session.is_authorized("file_controller"))

        res = execute_discovered_tool(
            "send_message",
            json.dumps({"message": "Attached invoice.pdf"}),
            session_id="session_alpha",
            action_registry=self.action_registry,
        )
        self.assertEqual(res, "Message sent: Attached invoice.pdf")


class TestStartupValidationAndCircuitBreaker(unittest.TestCase):
    """Test automatic startup validation, circuit breaker threshold, and fallback."""

    def setUp(self):
        reset_telemetry()

    def test_validate_pilot_readiness_success(self):
        mock_actions = MagicMock()
        mock_actions.has.return_value = True
        valid, reason = validate_pilot_readiness(mock_actions)
        self.assertTrue(valid)
        self.assertEqual(reason, "")

    def test_validate_pilot_readiness_fails_if_core_action_missing(self):
        mock_actions = MagicMock()
        mock_actions.has.side_effect = lambda name: name != "open_app"
        valid, reason = validate_pilot_readiness(mock_actions)
        self.assertFalse(valid)
        self.assertIn("open_app", reason)

    def test_circuit_breaker_trips_after_3_infrastructure_failures(self):
        cb = GatewayCircuitBreaker(max_failures=3)
        self.assertFalse(cb.record_failure(is_infrastructure=False))  # user err ignored
        self.assertFalse(cb.record_failure(is_infrastructure=True))   # 1
        self.assertFalse(cb.record_failure(is_infrastructure=True))   # 2
        self.assertTrue(cb.record_failure(is_infrastructure=True))    # 3 -> trips!
        self.assertTrue(cb.fallback_triggered)
        # Subsequent failures don't re-trip
        self.assertFalse(cb.record_failure(is_infrastructure=True))

    def test_telemetry_counters_recorded_safely(self):
        record_telemetry("discovery_requests")
        record_telemetry("discovery_successes")
        record_telemetry("gateway_invocations")
        telemetry = get_telemetry()
        self.assertEqual(telemetry["discovery_requests"], 1)
        self.assertEqual(telemetry["discovery_successes"], 1)
        self.assertEqual(telemetry["gateway_invocations"], 1)


    def test_step20_production_default_and_declarations(self):
        import os
        from core.tool_gateway import is_full_mode_forced, is_discovery_enabled, validate_discovery_readiness

        # Default without env flags: discovery is enabled
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(is_full_mode_forced())
            self.assertTrue(is_discovery_enabled())

            mock_actions = MagicMock()
            mock_actions.has.return_value = True
            valid, reason = validate_discovery_readiness(mock_actions)
            self.assertTrue(valid)

    def test_step20_manual_full_override(self):
        import os
        from core.tool_gateway import is_full_mode_forced, is_discovery_enabled

        with patch.dict(os.environ, {"CHARLIE_TOOL_FULL": "1"}, clear=True):
            self.assertTrue(is_full_mode_forced())
            self.assertFalse(is_discovery_enabled())

    def test_step20_validation_failure_auto_fallback(self):
        from core.tool_gateway import validate_discovery_readiness

        mock_actions = MagicMock()
        mock_actions.has.side_effect = lambda name: name != "file_controller"
        valid, reason = validate_discovery_readiness(mock_actions)
        self.assertFalse(valid)
        self.assertIn("file_controller", reason)

    def test_step20_telemetry_discovery_counters(self):
        reset_telemetry()
        record_telemetry("tool_mode_discovery_sessions")
        record_telemetry("discovery_fallback_to_full")
        t = get_telemetry()
        self.assertEqual(t["tool_mode_discovery_sessions"], 1)
        self.assertEqual(t["tool_mode_pilot_sessions"], 1)
        self.assertEqual(t["discovery_fallback_to_full"], 1)
        self.assertEqual(t["pilot_fallback_to_full"], 1)


class TestTypedProChatDiscoveryGateway(unittest.TestCase):
    """Test suite for Phase 3 Step 21: Typed ProChat 17-tool Discovery Gateway integration."""

    def setUp(self):
        import io
        from core import confirm
        from engine.pro_chat import ProChatAssistant

        self.mock_actions = {
            "open_app": ActionRecord(
                name="open_app",
                description="Opens any application on the computer.",
                parameters={"type": "OBJECT", "properties": {"app_name": {"type": "STRING"}}, "required": ["app_name"]},
                handler=lambda parameters=None, **kwargs: f"Opened {(parameters or kwargs).get('app_name', '')}.",
                valid=True,
            ),
            "quick_calc": ActionRecord(
                name="quick_calc",
                description="Performs instant arithmetic calculations.",
                parameters={"type": "OBJECT", "properties": {"query": {"type": "STRING"}}, "required": ["query"]},
                handler=lambda parameters=None, **kwargs: "6000" if "125 * 48" in (parameters or kwargs).get("query", "") else "42",
                valid=True,
            ),
            "web_search": ActionRecord(
                name="web_search",
                description="Searches the web.",
                parameters={"type": "OBJECT", "properties": {"query": {"type": "STRING"}}, "required": ["query"]},
                handler=lambda parameters=None, **kwargs: f"Web search results for: {(parameters or kwargs).get('query', '')}",
                valid=True,
            ),
            "computer_settings": ActionRecord(
                name="computer_settings",
                description="Controls computer settings and window management.",
                parameters={"type": "OBJECT", "properties": {"action": {"type": "STRING"}, "setting": {"type": "STRING"}, "app_name": {"type": "STRING"}}},
                handler=lambda parameters=None, **kwargs: (
                    confirm.request(
                        key="shutdown:system",
                        title="Shut this computer down?",
                        detail="CHARLIE will shut down your computer.",
                        run=lambda: "Shutdown executed.",
                    )
                    if (parameters or kwargs).get("setting") == "shutdown" or (parameters or kwargs).get("action") == "shutdown"
                    else f"Closed {(parameters or kwargs).get('app_name', '')}."
                ),
                valid=True,
            ),
            "file_controller": ActionRecord(
                name="file_controller",
                description="File operations.",
                parameters={"type": "OBJECT", "properties": {"action": {"type": "STRING"}, "path": {"type": "STRING"}}},
                handler=lambda parameters=None, **kwargs: (
                    confirm.request(
                        key=f"delete:{(parameters or kwargs).get('path', '')}",
                        title=f"Move '{(parameters or kwargs).get('path', '')}' to the Recycle Bin?",
                        detail=f"CHARLIE will move {(parameters or kwargs).get('path', '')} to Recycle Bin.",
                        run=lambda: f"Deleted {(parameters or kwargs).get('path', '')}",
                    )
                    if (parameters or kwargs).get("action") == "delete"
                    else f"File action {(parameters or kwargs).get('action', '')} on {(parameters or kwargs).get('path', '')} completed."
                ),
                valid=True,
            ),
            "diagnose_error": ActionRecord(
                name="diagnose_error",
                description="Read-only, evidence-first diagnosis for local projects and logs.",
                parameters={"type": "OBJECT", "properties": {"action": {"type": "STRING"}, "error": {"type": "STRING"}}, "required": ["action"]},
                handler=lambda parameters=None, **kwargs: f"Diagnosed error: {(parameters or kwargs).get('error', '')}",
                valid=True,
            ),
            "meeting_notes": ActionRecord(
                name="meeting_notes",
                description="Meeting notes taker.",
                parameters={"type": "OBJECT", "properties": {"action": {"type": "STRING"}, "meeting_title": {"type": "STRING"}}, "required": ["action"]},
                handler=lambda parameters=None, **kwargs: f"Started meeting notes: {(parameters or kwargs).get('meeting_title', 'Meeting')}",
                valid=True,
            ),
            "file_processor": ActionRecord(
                name="file_processor",
                description="Processes documents and invoices.",
                parameters={"type": "OBJECT", "properties": {"action": {"type": "STRING"}, "query": {"type": "STRING"}}},
                handler=lambda parameters=None, **kwargs: f"Found files matching {(parameters or kwargs).get('query', '')}: invoice_2026.pdf",
                valid=True,
            ),
        }
        self.action_registry = ActionRegistry(self.mock_actions, logger=lambda m: None)

        self.mock_plugins = {
            "github_integration": PluginRecord(
                name="github_integration",
                description="Manage GitHub repositories and issues.",
                valid=True,
                settings={"namespace": "github_integration", "fields": []},
                run=lambda params, **kw: "GitHub issues: #1 Fix bug, #2 Add feature",
            ),
            "google_workspace": PluginRecord(
                name="google_workspace",
                description="Google Drive and Docs workspace helper.",
                valid=True,
                settings={"namespace": "google_workspace", "fields": []},
                run=lambda params, **kw: "Prepared invoice in Google Drive.",
            ),
        }
        self.plugin_registry = PluginRegistry(self.mock_plugins, logger=lambda _: None)

        def mock_generate(system: str, messages: list[dict[str, str]]) -> str:
            user_content = messages[-1].get("content", "")
            if "[Active Tool Execution Results]" in user_content:
                return f"Processed:\n{user_content.split('[Active Tool Execution Results]:')[-1].strip()}"
            return f"Answer for: {user_content}"

        confirm.bind(lambda title, detail: None, lambda: None)

        self.assistant = ProChatAssistant(
            generate=mock_generate,
            action_registry=self.action_registry,
            plugin_registry=self.plugin_registry,
        )

    def tearDown(self):
        from core import confirm
        confirm.resolve(accepted=False)
        if hasattr(self, "assistant") and self.assistant:
            clear_discovery_session(self.assistant.session_id)

    # ── Section 18: Normal Chat (No Tools) ─────────────────────────────────
    def test_step21_normal_chat_what_is_python(self):
        """'What is Python?' must produce normal answer without tools."""
        import io
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            reply = self.assistant.respond("What is Python?")
        logs = captured.getvalue()
        self.assertNotIn("[ProChat][Tool]", logs)
        self.assertNotIn("[ProChat][Discovery]", logs)
        self.assertIn("What is Python?", reply)

    def test_step21_normal_chat_explain_binary_search(self):
        """'Explain binary search.' must produce normal answer without tools."""
        import io
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            reply = self.assistant.respond("Explain binary search.")
        logs = captured.getvalue()
        self.assertNotIn("[ProChat][Tool]", logs)
        self.assertNotIn("[ProChat][Discovery]", logs)
        self.assertIn("Explain binary search.", reply)

    # ── Section 19: Direct CORE Tools ──────────────────────────────────────
    def test_step21_core_open_calculator(self):
        """'Open Calculator.' directly executes open_app."""
        import io
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            reply = self.assistant.respond("Open Calculator.")
        logs = captured.getvalue()
        self.assertIn("[ProChat][Tool] CORE: open_app", logs)
        self.assertIn("Opened Calculator.", reply)

    def test_step21_core_system_status(self):
        """'What is my system status?' directly executes system_status."""
        import io
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            reply = self.assistant.respond("What is my system status?")
        logs = captured.getvalue()
        self.assertIn("[ProChat][Tool] CORE: system_status", logs)
        self.assertIn("cpu_percent", reply)

    def test_step21_core_quick_calc(self):
        """'Calculate 125 * 48' directly executes quick_calc."""
        import io
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            reply = self.assistant.respond("Calculate 125 * 48")
        logs = captured.getvalue()
        self.assertIn("[ProChat][Tool] CORE: quick_calc", logs)
        self.assertIn("6000", reply)

    def test_step21_core_web_search(self):
        """'Search the web for Python 3.14.' directly executes web_search."""
        import io
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            reply = self.assistant.respond("Search the web for Python 3.14.")
        logs = captured.getvalue()
        self.assertIn("[ProChat][Tool] CORE: web_search", logs)
        self.assertIn("Python 3.14", reply)

    # ── Section 20: Specialized Discovery ──────────────────────────────────
    def test_step21_specialized_discovery_developer(self):
        """'I have a Python error. Help me diagnose it.' discovers and invokes diagnose_error."""
        import io
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            reply = self.assistant.respond("I have a Python error. Help me diagnose it.")
        logs = captured.getvalue()
        self.assertIn("[ProChat][Discovery]", logs)
        self.assertTrue("DEVELOPER" in logs or "ADMIN_DIAGNOSTICS" in logs)
        self.assertIn("[ProChat][Discovery] candidate=diagnose_error", logs)
        self.assertIn("[ProChat][Tool] invoke=diagnose_error", logs)
        self.assertIn("Diagnosed error:", reply)

    def test_step21_specialized_discovery_productivity(self):
        """'Help me create meeting notes.' discovers and invokes meeting_notes."""
        import io
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            reply = self.assistant.respond("Help me create meeting notes.")
        logs = captured.getvalue()
        self.assertIn("[ProChat][Discovery] groups=PRODUCTIVITY", logs)
        self.assertIn("[ProChat][Discovery] candidate=meeting_notes", logs)
        self.assertIn("[ProChat][Tool] invoke=meeting_notes", logs)
        self.assertIn("Started meeting notes", reply)

    def test_step21_specialized_discovery_plugins(self):
        """'Check my GitHub issues.' discovers github_integration."""
        import io
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            reply = self.assistant.respond("Check my GitHub issues.")
        logs = captured.getvalue()
        self.assertIn("[ProChat][Discovery] groups=PLUGINS", logs)
        self.assertIn("[ProChat][Discovery] candidate=github_integration", logs)
        self.assertIn("[ProChat][Tool] invoke=github_integration", logs)

    def test_step21_specialized_discovery_files_and_plugins(self):
        """'Find an invoice PDF and prepare it for Google Drive.' discovers FILES and PLUGINS."""
        import io
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            reply = self.assistant.respond("Find an invoice PDF and prepare it for Google Drive.")
        logs = captured.getvalue()
        self.assertIn("FILES", logs)
        self.assertIn("PLUGINS", logs)
        self.assertIn("[ProChat][Discovery] candidate=", logs)

    # ── Section 21: Multi-turn Context ─────────────────────────────────────
    def test_step21_multi_turn_context(self):
        """Turn 1: 'Open Chrome.' -> open_app. Turn 2: 'close it' -> closes Chrome."""
        import io
        captured1 = io.StringIO()
        with patch("sys.stdout", captured1):
            self.assistant.respond("Open Chrome.")
        self.assertIn("[ProChat][Tool] CORE: open_app", captured1.getvalue())

        captured2 = io.StringIO()
        with patch("sys.stdout", captured2):
            reply2 = self.assistant.respond("close it")
        logs2 = captured2.getvalue()
        self.assertIn("[ProChat][Tool] CORE: computer_settings", logs2)
        self.assertIn("Closed Chrome.", reply2)

    # ── Section 22: Security & Confirmation Gates ──────────────────────────
    def test_step21_destructive_file_delete_confirmation(self):
        """'Delete this test file.' requires confirmation; cancelling leaves it untouched."""
        from core import confirm
        reply = self.assistant.respond("Delete this test file.")
        self.assertIn("CONFIRMATION_PENDING", reply)
        self.assertTrue(bool(confirm.pending_title()))

        confirm.resolve(accepted=False)
        self.assertEqual(confirm.pending_title(), "")

    def test_step21_destructive_shutdown_confirmation(self):
        """'Shut down my computer.' requires confirmation; cancelling aborts."""
        from core import confirm
        reply = self.assistant.respond("Shut down my computer.")
        self.assertIn("CONFIRMATION_PENDING", reply)
        self.assertTrue(bool(confirm.pending_title()))

        confirm.resolve(accepted=False)
        self.assertEqual(confirm.pending_title(), "")

    def test_step21_malicious_gateway_tool_names_rejected(self):
        """Path traversal and dangerous tool names are rejected."""
        ctx = {"action_registry": self.action_registry}
        r1 = execute_discovered_tool("../../os.system", "{}", session_id="test", ctx=ctx)
        self.assertIn("Error: Invalid tool name format", r1)

        r2 = execute_discovered_tool("eval", "{}", session_id="test", ctx=ctx)
        self.assertIn("Error: Tool 'eval' has not been discovered", r2)

        r3 = execute_discovered_tool("__import__", "{}", session_id="test", ctx=ctx)
        self.assertIn("Error: Tool '__import__' has not been discovered", r3)

        r4 = execute_discovered_tool("subprocess.Popen", "{}", session_id="test", ctx=ctx)
        self.assertIn("Error: Invalid tool name format", r4)

    # ── Section 23: Session Isolation & TTL ─────────────────────────────────
    def test_step21_session_isolation(self):
        """Chat A and Chat B sessions are isolated."""
        from engine.pro_chat import ProChatAssistant
        assistant_a = ProChatAssistant(generate=lambda s, m: "ok", action_registry=self.action_registry)
        assistant_b = ProChatAssistant(generate=lambda s, m: "ok", action_registry=self.action_registry)

        sess_a = get_discovery_session(assistant_a.session_id)
        sess_b = get_discovery_session(assistant_b.session_id)

        sess_a.authorize("diagnose_error")
        self.assertTrue(sess_a.is_authorized("diagnose_error"))
        self.assertFalse(sess_b.is_authorized("diagnose_error"))

        clear_discovery_session(assistant_a.session_id)
        clear_discovery_session(assistant_b.session_id)

    def test_step21_ttl_expiration(self):
        """Authorization expires after TTL."""
        sess = DiscoverySession("ttl_test_sess", ttl=0.1)
        sess.authorize("diagnose_error")
        self.assertTrue(sess.is_authorized("diagnose_error"))
        import time
        time.sleep(0.15)
        self.assertFalse(sess.is_authorized("diagnose_error"))

    # ── Section 24: Tool Loop Bound & Protection ───────────────────────────
    def test_step21_tool_loop_bound(self):
        """Tool loop bounded to maximum 5 turns."""
        self.assertEqual(self.assistant.MAX_TOOL_LOOPS, 5)

    def test_step21_sensitive_redaction(self):
        """Tool output redacts API keys and secrets."""
        from engine.pro_chat import ProChatAssistant
        raw = "Config: api_key=AIzaSySecretKey123 token=abc123xyz"
        redacted = ProChatAssistant._format_tool_result(raw)
        self.assertNotIn("AIzaSySecretKey123", redacted)
        self.assertIn("[REDACTED]", redacted)


def _run_asgi(app, method: str, path: str, headers: list[tuple[str, str]] | None = None, body: bytes = b"", client_ip: str = "127.0.0.1"):
    import asyncio
    import json
    response_body = []
    response_headers = []
    status_code = [0]

    parts = path.split("?", 1)
    route_path = parts[0]
    query_str = parts[1].encode("latin-1") if len(parts) > 1 else b""

    header_list = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or [])]
    if body and not any(k == b"content-type" for k, _ in header_list):
        header_list.append((b"content-type", b"application/json"))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method.upper(),
        "scheme": "http",
        "path": route_path,
        "raw_path": route_path.encode("latin-1"),
        "query_string": query_str,
        "headers": header_list,
        "client": (client_ip, 50000),
        "server": ("127.0.0.1", 1901),
    }

    async def _call():
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                status_code[0] = message["status"]
                response_headers.extend(message.get("headers", []))
            elif message["type"] == "http.response.body":
                response_body.append(message.get("body", b""))

        await app(scope, receive, send)

    asyncio.run(_call())
    raw_data = b"".join(response_body)
    try:
        json_data = json.loads(raw_data.decode("utf-8"))
    except Exception:
        json_data = None
    return status_code[0], raw_data, json_data


def _run_asgi_ws(app, path: str, client_ip: str = "127.0.0.1"):
    import asyncio
    closed_codes = []
    parts = path.split("?", 1)
    route_path = parts[0]
    query_str = parts[1].encode("latin-1") if len(parts) > 1 else b""

    scope = {
        "type": "websocket",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "scheme": "ws",
        "path": route_path,
        "raw_path": route_path.encode("latin-1"),
        "query_string": query_str,
        "headers": [],
        "client": (client_ip, 50000),
        "server": ("127.0.0.1", 1901),
        "subprotocols": [],
    }

    async def _call():
        async def receive():
            return {"type": "websocket.connect"}

        async def send(message):
            if message["type"] == "websocket.close":
                closed_codes.append(message.get("code"))

        try:
            await app(scope, receive, send)
        except Exception:
            pass

    asyncio.run(_call())
    return closed_codes


class TestDashboardSecurityStep23A(unittest.TestCase):
    """Step 23A: Dashboard Authentication, Rate Limiting, and Session-Key Protection."""

    def setUp(self):
        from dashboard.server import DashboardServer
        self.server = DashboardServer()
        self.app = self.server.app

    def tearDown(self):
        self.server.shutdown()

    def test_step23a_lan_session_key_forbidden(self):
        """Unauthenticated LAN client cannot access GET /session-key (HTTP 403)."""
        status, raw, data = _run_asgi(
            self.app, "GET", "/session-key", client_ip="192.168.1.150"
        )
        self.assertEqual(status, 403)
        self.assertIsNotNone(data)
        self.assertIn("error", data)
        self.assertIn("Forbidden", data["error"])

    def test_step23a_loopback_session_key_allowed(self):
        """Local loopback clients can access GET /session-key (HTTP 200)."""
        for loopback_ip in ("127.0.0.1", "::1", "localhost"):
            status, raw, data = _run_asgi(
                self.app, "GET", "/session-key", client_ip=loopback_ip
            )
            self.assertEqual(status, 200)
            self.assertIsNotNone(data)
            self.assertIn("session_key", data)
            key = data["session_key"]
            self.assertEqual(len(key), 6)
            self.assertIn(key, self.server._pending_keys)

    def test_step23a_protected_endpoint_requires_auth(self):
        """Protected endpoint /api/files returns 401 when no token is provided."""
        status, raw, data = _run_asgi(
            self.app, "GET", "/api/files", client_ip="192.168.1.150"
        )
        self.assertEqual(status, 401)
        self.assertEqual(data, {"error": "Unauthorized"})

    def test_step23a_protected_endpoint_allows_valid_bearer(self):
        """Protected endpoint /api/files returns 200 when valid token is provided."""
        tok = "test_valid_bearer_token_12345"
        self.server._tokens.add(tok)
        status, raw, data = _run_asgi(
            self.app, "GET", "/api/files",
            headers=[("Authorization", f"Bearer {tok}")],
            client_ip="192.168.1.150"
        )
        self.assertEqual(status, 200)
        self.assertIsNotNone(data)
        self.assertIn("files", data)

    def test_step23a_login_valid_pin_success(self):
        """Valid PIN login returns token and consumes the one-time key."""
        pin = self.server.new_key(expiry_secs=300)
        self.assertIn(pin, self.server._pending_keys)

        payload = json.dumps({"pin": pin}).encode("utf-8")
        status, raw, data = _run_asgi(
            self.app, "POST", "/login",
            body=payload,
            client_ip="192.168.1.150"
        )
        self.assertEqual(status, 200)
        self.assertIsNotNone(data)
        self.assertTrue(data.get("ok"))
        self.assertIn("token", data)
        token = data["token"]
        self.assertIn(token, self.server._tokens)
        self.assertNotIn(pin, self.server._pending_keys)

    def test_step23a_login_invalid_pin_failure(self):
        """Invalid PIN returns 401 and records failed attempt."""
        payload = json.dumps({"pin": "BADPIN"}).encode("utf-8")
        with patch("asyncio.sleep", return_value=None):
            status, raw, data = _run_asgi(
                self.app, "POST", "/login",
                body=payload,
                client_ip="192.168.1.150"
            )
        self.assertEqual(status, 401)
        self.assertFalse(data.get("ok"))
        self.assertEqual(data.get("error"), "Invalid or expired key")

    def test_step23a_login_rate_limiting_blocks_brute_force(self):
        """More than 5 failed logins triggers HTTP 429 Too Many Requests."""
        payload = json.dumps({"pin": "BADPIN"}).encode("utf-8")
        with patch("asyncio.sleep", return_value=None):
            for _ in range(5):
                status, _, _ = _run_asgi(
                    self.app, "POST", "/login",
                    body=payload,
                    client_ip="192.168.1.180"
                )
                self.assertEqual(status, 401)

            # 6th attempt must be rejected with 429
            status, raw, data = _run_asgi(
                self.app, "POST", "/login",
                body=payload,
                client_ip="192.168.1.180"
            )
            self.assertEqual(status, 429)
            self.assertFalse(data.get("ok"))
            self.assertIn("Too many failed attempts", data.get("error", ""))

            # Different client IP is NOT rate-limited
            status_other, _, _ = _run_asgi(
                self.app, "POST", "/login",
                body=payload,
                client_ip="192.168.1.181"
            )
            self.assertEqual(status_other, 401)

    def test_step23a_auto_login_rate_limiting(self):
        """More than 5 failed auto-login requests triggers HTTP 429."""
        with patch("asyncio.sleep", return_value=None):
            for _ in range(5):
                status, raw, _ = _run_asgi(
                    self.app, "GET", "/auto-login?key=WRONGKEY",
                    client_ip="192.168.1.190"
                )
                self.assertEqual(status, 200)
                self.assertIn(b"Link Expired", raw)

            # 6th attempt must be rejected with 429
            status, raw, _ = _run_asgi(
                self.app, "GET", "/auto-login?key=WRONGKEY",
                client_ip="192.168.1.190"
            )
            self.assertEqual(status, 429)
            self.assertIn(b"Too Many Attempts", raw)

    def test_step23a_auto_login_valid_key(self):
        """Auto-login with valid key succeeds and consumes key."""
        key = self.server.new_key(expiry_secs=300)
        status, raw, _ = _run_asgi(
            self.app, "GET", f"/auto-login?key={key}",
            client_ip="192.168.1.190"
        )
        self.assertEqual(status, 200)
        self.assertIn(b"sessionStorage.setItem", raw)
        self.assertNotIn(key, self.server._pending_keys)

    def test_step23a_websocket_unauthorized_closed(self):
        """WebSocket connection without valid auth token is closed with code 4001."""
        codes = _run_asgi_ws(self.app, "/ws", client_ip="192.168.1.150")
        self.assertIn(4001, codes)

    def test_step23a_raw_key_not_logged_in_stdout(self):
        """Console output does not leak raw session key."""
        import io
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            key = self.server.new_key(expiry_secs=300)
            payload = json.dumps({"pin": "BADPIN"}).encode("utf-8")
            with patch("asyncio.sleep", return_value=None):
                _run_asgi(self.app, "POST", "/login", body=payload, client_ip="192.168.1.150")
        output = captured.getvalue()
        self.assertNotIn(key, output)
        self.assertNotIn("BADPIN", output)
        self.assertIn("Authentication rejected from 192.168.1.150", output)


if __name__ == "__main__":
    unittest.main()


