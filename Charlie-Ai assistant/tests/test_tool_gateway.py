"""Unit tests for Phase 3 Step 14: Two-stage tool discovery gateway and session-scoped invocation."""

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
    TOOL_DISCOVERY_GATEWAY_ENABLED,
    TOOL_DISCOVERY_PILOT,
    DiscoverySession,
    clear_discovery_session,
    discover_candidates,
    execute_discovered_tool,
    get_discovery_session,
    is_gateway_enabled,
    is_pilot_enabled,
)
from core.tool_groups import get_core_tools


class TestDiscoveryGateway(unittest.TestCase):
    """Test tool discovery candidate resolution, filtering, and authorization."""

    def setUp(self):
        clear_discovery_session("test_session_a")
        clear_discovery_session("test_session_b")

        self.mock_actions = {
            "send_message": ActionRecord(
                name="send_message",
                description="Send a message on WhatsApp or Telegram to a contact.",
                parameters={"type": "OBJECT", "properties": {"message": {"type": "STRING"}}, "required": ["message"]},
                handler=lambda message, **kw: f"Sent: {message}",
                valid=True,
            ),
            "code_helper": ActionRecord(
                name="code_helper",
                description="Analyze, fix, or review code in Python, JavaScript, etc.",
                parameters={"type": "OBJECT", "properties": {"code": {"type": "STRING"}}, "required": ["code"]},
                handler=lambda code, **kw: f"Fixed code: {code}",
                valid=True,
            ),
            "file_catalog": ActionRecord(
                name="file_catalog",
                description="Find the exact local file for an autonomous task.",
                parameters={"type": "OBJECT", "properties": {"query": {"type": "STRING"}}, "required": ["query"]},
                handler=lambda query, **kw: f"Found: {query}",
                valid=True,
            ),
            "dev_agent": ActionRecord(
                name="dev_agent",
                description="Autonomous developer agent for writing code.",
                parameters={"type": "OBJECT", "properties": {"task": {"type": "STRING"}}, "required": ["task"]},
                handler=lambda task, **kw: f"Dev task: {task}",
                valid=True,
            ),
        }
        self.action_registry = ActionRegistry(self.mock_actions, logger=lambda _: None)

        self.mock_plugins = {
            "whatsapp_integration": PluginRecord(
                name="whatsapp_integration",
                description="Send WhatsApp messages directly.",
                parameters={"type": "OBJECT", "properties": {"text": {"type": "STRING"}}},
                run=lambda **kw: "WhatsApp message sent",
                valid=True,
                settings={"namespace": "whatsapp_integration", "fields": [{"key": "access_token"}]},
            )
        }
        self.plugin_registry = PluginRegistry(self.mock_plugins, logger=lambda _: None)

    def tearDown(self):
        clear_discovery_session("test_session_a")
        clear_discovery_session("test_session_b")

    def test_discover_candidates_bounds_results(self):
        candidates = discover_candidates(
            intent="send WhatsApp message",
            session_id="test_session_a",
            action_registry=self.action_registry,
            plugin_registry=self.plugin_registry,
            max_results=3,
        )
        self.assertLessEqual(len(candidates), 3)
        self.assertGreaterEqual(len(candidates), 1)
        names = [c["tool_name"] for c in candidates]
        self.assertIn("send_message", names)

    def test_unconfigured_plugin_excluded(self):
        # Plugin without access_token should not be returned
        with patch.object(self.plugin_registry, "is_configured", return_value=False):
            candidates = discover_candidates(
                intent="send WhatsApp message",
                session_id="test_session_a",
                action_registry=self.action_registry,
                plugin_registry=self.plugin_registry,
            )
            names = [c["tool_name"] for c in candidates]
            self.assertNotIn("whatsapp_integration", names)

    def test_developer_tool_isolation(self):
        # Normal query does not expose dev_agent
        candidates = discover_candidates(
            intent="find invoice PDF",
            session_id="test_session_a",
            action_registry=self.action_registry,
            plugin_registry=self.plugin_registry,
        )
        names = [c["tool_name"] for c in candidates]
        self.assertNotIn("dev_agent", names)

        # Developer query includes code tools
        dev_candidates = discover_candidates(
            intent="fix Python code traceback",
            session_id="test_session_a",
            action_registry=self.action_registry,
            plugin_registry=self.plugin_registry,
        )
        dev_names = [c["tool_name"] for c in dev_candidates]
        self.assertTrue("code_helper" in dev_names or "dev_agent" in dev_names)

    def test_session_scoped_authorization(self):
        # Discover in session A
        discover_candidates(
            intent="send message",
            session_id="test_session_a",
            action_registry=self.action_registry,
            plugin_registry=self.plugin_registry,
        )

        session_a = get_discovery_session("test_session_a")
        session_b = get_discovery_session("test_session_b")

        self.assertTrue(session_a.is_authorized("send_message"))
        self.assertFalse(session_b.is_authorized("send_message"))

    def test_ttl_expiration(self):
        session = DiscoverySession("test_session_ttl", ttl=0.1)
        session.authorize("file_catalog")
        self.assertTrue(session.is_authorized("file_catalog"))

        time.sleep(0.15)
        self.assertFalse(session.is_authorized("file_catalog"))


class TestInvocationGateway(unittest.TestCase):
    """Test invoke_discovered_tool security checks, parameter validation, and execution."""

    def setUp(self):
        clear_discovery_session("test_inv_session")
        self.mock_actions = {
            "send_message": ActionRecord(
                name="send_message",
                description="Send message.",
                parameters={"type": "OBJECT", "properties": {"message": {"type": "STRING"}}, "required": ["message"]},
                handler=lambda message, **kw: f"Sent: {message}",
                valid=True,
            ),
            "file_controller": ActionRecord(
                name="file_controller",
                description="Manage files.",
                parameters={"type": "OBJECT", "properties": {"action": {"type": "STRING"}}, "required": ["action"]},
                handler=lambda action, **kw: f"File action: {action}",
                valid=True,
            ),
        }
        self.action_registry = ActionRegistry(self.mock_actions, logger=lambda _: None)
        self.plugin_registry = PluginRegistry({}, logger=lambda _: None)

    def tearDown(self):
        clear_discovery_session("test_inv_session")

    def test_successful_invocation_of_discovered_tool(self):
        session = get_discovery_session("test_inv_session")
        session.authorize("send_message")

        res = execute_discovered_tool(
            tool_name="send_message",
            arguments_json=json.dumps({"message": "Hello World"}),
            session_id="test_inv_session",
            action_registry=self.action_registry,
            plugin_registry=self.plugin_registry,
        )
        self.assertEqual(res, "Sent: Hello World")

    def test_core_tool_always_authorized_without_discovery(self):
        # file_controller is a CORE tool, should execute without prior discovery
        res = execute_discovered_tool(
            tool_name="file_controller",
            arguments_json=json.dumps({"action": "list"}),
            session_id="test_inv_session",
            action_registry=self.action_registry,
            plugin_registry=self.plugin_registry,
        )
        self.assertEqual(res, "File action: list")

    def test_rejection_of_unauthorized_specialized_tool(self):
        res = execute_discovered_tool(
            tool_name="send_message",
            arguments_json=json.dumps({"message": "Hello"}),
            session_id="test_inv_session",
            action_registry=self.action_registry,
            plugin_registry=self.plugin_registry,
        )
        self.assertIn("Error: Tool 'send_message' has not been discovered", res)

    def test_rejection_of_recursive_gateway_calls(self):
        res1 = execute_discovered_tool("discover_tools", "{}", session_id="test_inv_session")
        self.assertIn("Error: Tool 'discover_tools' cannot be invoked", res1)

        res2 = execute_discovered_tool("invoke_discovered_tool", "{}", session_id="test_inv_session")
        self.assertIn("Error: Tool 'invoke_discovered_tool' cannot be invoked", res2)

    def test_rejection_of_path_traversal_and_invalid_names(self):
        res1 = execute_discovered_tool("../../../etc/passwd", "{}", session_id="test_inv_session")
        self.assertIn("Error: Invalid tool name format", res1)

        res2 = execute_discovered_tool("__import__", "{}", session_id="test_inv_session")
        self.assertIn("Error: Tool '__import__' has not been discovered", res2)

    def test_rejection_of_malformed_json_and_missing_required_params(self):
        session = get_discovery_session("test_inv_session")
        session.authorize("send_message")

        res_bad_json = execute_discovered_tool(
            tool_name="send_message",
            arguments_json="{not_valid_json:",
            session_id="test_inv_session",
            action_registry=self.action_registry,
        )
        self.assertIn("Error: Failed to parse arguments_json", res_bad_json)

        res_missing = execute_discovered_tool(
            tool_name="send_message",
            arguments_json=json.dumps({"wrong_param": 123}),
            session_id="test_inv_session",
            action_registry=self.action_registry,
        )
        self.assertIn("Error: Missing required argument 'message'", res_missing)


class TestGatewayConfigurationAndSchema(unittest.TestCase):
    """Test feature flags, production defaults, manual override, and tool declarations."""

    def test_production_defaults_and_override_precedence(self):
        from core.tool_gateway import is_discovery_enabled, is_full_mode_forced, is_pilot_enabled
        import os

        # 1. Default without env flags: DISCOVERY mode enabled, FULL mode not forced
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(is_discovery_enabled())
            self.assertTrue(is_pilot_enabled())
            self.assertFalse(is_full_mode_forced())

        # 2. Explicit manual FULL override: CHARLIE_TOOL_FULL=1
        with patch.dict(os.environ, {"CHARLIE_TOOL_FULL": "1"}, clear=True):
            self.assertTrue(is_full_mode_forced())
            self.assertFalse(is_discovery_enabled())
            self.assertFalse(is_pilot_enabled())

        # 3. Explicit manual FULL override: CHARLIE_FULL_TOOLS=1
        with patch.dict(os.environ, {"CHARLIE_FULL_TOOLS": "1"}, clear=True):
            self.assertTrue(is_full_mode_forced())
            self.assertFalse(is_discovery_enabled())

    def test_declarations_conform_to_schema(self):
        for decl in (DISCOVERY_TOOL_DECLARATION, INVOCATION_TOOL_DECLARATION):
            self.assertIn("name", decl)
            self.assertIn("description", decl)
            self.assertIn("parameters", decl)
            self.assertEqual(decl["parameters"]["type"], "OBJECT")
            self.assertEqual(decl.get("behavior"), "BLOCKING")


if __name__ == "__main__":
    unittest.main()
