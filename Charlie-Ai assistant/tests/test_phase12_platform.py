"""
CHARLIE Phase 12: Developer Platform Test Suite
Validates Golden Tests 111 to 127 and Section 128 Certification Matrix:
- MCP Discovery, Schema Validation, Execution & Malicious Tool Defense
- Plugin Lifecycle (Install, Security Scan, Activation, Rollback, Uninstall)
- Extension Sandbox (Domain allowlist, Filesystem isolation)
- Scoped Credential Binding (Zero secret leakage)
- Custom Agent Boundaries & Scoped Tool Execution
- Tool Resolver & Dynamic Tool Loading (Token conservation)
- Event Bus, Replay-Protected Webhooks & Automations
- OpenAPI Importer & Database Read-Only Enforcement
"""

import hashlib
import hmac
import time
import unittest
import uuid

from engine.platform.core import DeveloperPlatform
from engine.platform.models import (
    AutomationRule,
    EventMessage,
    ExtensionManifest,
    ExtensionType,
    MemoryScope,
    PermissionManifest,
    PluginLifecycle,
    ToolContract,
    WebhookPayload,
)


class TestPhase12Platform(unittest.TestCase):

    def setUp(self):
        self.platform = DeveloperPlatform()

    # --- 111. MCP Golden Test ---
    def test_golden_111_mcp_discovery_and_execution(self):
        # Discover tools from default mock MCP server
        tools = self.platform.mcp_gateway.discover_and_map_tools("default_mcp_mock")
        self.assertTrue(len(tools) >= 2)
        tool_names = [t.name for t in tools]
        self.assertIn("mcp.fetch_weather", tool_names)

        # Execute safe tool
        res = self.platform.mcp_gateway.execute_mcp_tool(
            "default_mcp_mock", "mcp.fetch_weather", {"city": "Bengaluru"}
        )
        self.assertEqual(res.status, "SUCCESS")
        self.assertTrue(res.verified)
        self.assertEqual(res.data["city"], "Bengaluru")

    # --- 112. MCP Malicious Tool Defense ---
    def test_golden_112_mcp_malicious_tool_defense(self):
        # Malicious tool description claims full access, but execution must be blocked
        res = self.platform.mcp_gateway.execute_mcp_tool(
            "default_mcp_mock", "mcp.unauthorized_shell", {"cmd": "rmdir /s /q c:\\"}
        )
        self.assertEqual(res.status, "BLOCKED")
        self.assertIn("blocked", res.error.lower())

    # --- 113. Plugin Install Test ---
    def test_golden_113_plugin_install_and_health(self):
        manifest = ExtensionManifest(
            id="test_crm_plugin",
            name="Test CRM",
            version="1.0.0",
            type=ExtensionType.CONNECTOR,
            description="CRM Integration for client sync",
            entrypoint="crm.py",
            tools=["crm.lead.create", "crm.lead.get"],
            permissions=PermissionManifest(
                network=["api.crm.com"],
                filesystem=["workspace:read"],
                allowed_credentials=["crm_api_key"],
            ),
        )
        ok, msg = self.platform.install_plugin_from_manifest(manifest)
        self.assertTrue(ok)
        plugin = self.platform.plugin_registry.get_plugin("test_crm_plugin")
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.version, "1.0.0")

    # --- 114. Invalid Plugin Rejected ---
    def test_golden_114_invalid_plugin_rejected(self):
        # Missing permissions and empty tools
        bad_manifest = ExtensionManifest(
            id="",
            name="",
            version="1.0.0",
            type=ExtensionType.TOOL,
            description="Bad plugin",
            entrypoint="",
            tools=[],
        )
        ok, msg = self.platform.plugin_registry.install_plugin(bad_manifest)
        self.assertFalse(ok)
        self.assertIn("rejected", msg.lower())

    # --- 115. Permission Update / Rollback Test ---
    def test_golden_115_plugin_rollback(self):
        # Install v1
        v1 = ExtensionManifest(
            id="plugin_upg",
            name="Upgrade Test",
            version="1.0.0",
            type=ExtensionType.TOOL,
            description="Safe v1",
            entrypoint="main.py",
            tools=["tool_v1"],
            permissions=PermissionManifest(network=["safe.com"]),
        )
        self.platform.install_plugin_from_manifest(v1)

        # Upgrade to v2
        v2 = ExtensionManifest(
            id="plugin_upg",
            name="Upgrade Test",
            version="2.0.0",
            type=ExtensionType.TOOL,
            description="Updated v2",
            entrypoint="main.py",
            tools=["tool_v1", "tool_v2"],
            permissions=PermissionManifest(network=["safe.com"]),
        )
        self.platform.install_plugin_from_manifest(v2)
        self.assertEqual(self.platform.plugin_registry.get_plugin("plugin_upg").version, "2.0.0")

        # Roll back
        rb_ok, rb_msg = self.platform.plugin_registry.rollback_plugin("plugin_upg")
        self.assertTrue(rb_ok)
        self.assertEqual(self.platform.plugin_registry.get_plugin("plugin_upg").version, "1.0.0")

    # --- 116. Plugin Crash & Circuit Breaker ---
    def test_golden_116_plugin_crash_circuit_breaker(self):
        p_id = "crashing_plugin"
        self.platform.health_manager.record_failure(p_id, "Memory crash 1")
        self.platform.health_manager.record_failure(p_id, "Memory crash 2")
        self.assertFalse(self.platform.health_manager.is_degraded_or_broken(p_id))

        # 3rd crash trips breaker
        tripped = self.platform.health_manager.record_failure(p_id, "Memory crash 3")
        self.assertTrue(tripped)
        self.assertTrue(self.platform.health_manager.is_degraded_or_broken(p_id))

    # --- 117. Sandbox Filesystem Restriction ---
    def test_golden_117_sandbox_filesystem_restriction(self):
        manifest = ExtensionManifest(
            id="restricted_file_plugin",
            name="Restricted File Tool",
            version="1.0.0",
            type=ExtensionType.TOOL,
            description="Scoped file reader",
            entrypoint="main.py",
            tools=["file.scoped_read"],
            permissions=PermissionManifest(filesystem=["workspace:read"]),
        )
        self.platform.install_plugin_from_manifest(manifest)

        # Attempt to access protected Windows system32 directory
        res = self.platform.execute_tool_sandboxed("file.scoped_read", {"path": "C:\\Windows\\System32\\cmd.exe"})
        self.assertEqual(res.status, "BLOCKED")
        self.assertIn("protected system directory", res.error)

    # --- 118. Sandbox Network Restriction ---
    def test_golden_118_sandbox_network_restriction(self):
        manifest = ExtensionManifest(
            id="restricted_net_plugin",
            name="Restricted Net Tool",
            version="1.0.0",
            type=ExtensionType.TOOL,
            description="Scoped net tool",
            entrypoint="main.py",
            tools=["net.scoped_call"],
            permissions=PermissionManifest(network=["api.approved-domain.com"]),
        )
        self.platform.install_plugin_from_manifest(manifest)

        # Attempt to call unapproved domain
        res = self.platform.execute_tool_sandboxed("net.scoped_call", {"domain": "evil-exfiltration.org"})
        self.assertEqual(res.status, "BLOCKED")
        self.assertIn("not in plugin allowlist", res.error)

    # --- 119. Scoped Secret Binding ---
    def test_golden_119_scoped_secret_binding(self):
        manifest = ExtensionManifest(
            id="gh_plugin",
            name="GitHub Extension",
            version="1.0.0",
            type=ExtensionType.CONNECTOR,
            description="GH integration",
            entrypoint="main.py",
            credentials=["github_token"],
            permissions=PermissionManifest(allowed_credentials=["github_token"]),
            tools=["github.issue.list"],
        )
        creds = self.platform.credential_binding.get_scoped_credentials(manifest)
        self.assertIn("github_token", creds)
        self.assertNotIn("db_password", creds)
        self.assertNotIn("slack_token", creds)

    # --- 120. Tool Resolver & Dynamic Tool Loading ---
    def test_golden_120_dynamic_tool_loading(self):
        # Resolve tools for an Excel task
        excel_tools = self.platform.tool_resolver.resolve_tools_for_task("clean my monthly excel report")
        tool_names = [t.name for t in excel_tools]
        self.assertIn("excel.clean_data", tool_names)
        self.assertNotIn("github.issue.create", tool_names)

    # --- 121. Custom Agent Boundaries ---
    def test_golden_121_custom_agent_boundaries(self):
        agent_spec = self.platform.agent_builder.create_agent(
            agent_id="zynpay_qa_01",
            name="ZynPay QA Agent",
            role="QA Tester",
            instructions="Run tests and report issues only",
            allowed_tools=["test.run", "github.issue.create"],
            project_scope="ZynPay",
            memory_scope=MemoryScope.PROJECT,
        )

        self.assertTrue(self.platform.agent_builder.can_agent_execute_tool("zynpay_qa_01", "test.run"))
        self.assertTrue(self.platform.agent_builder.can_agent_execute_tool("zynpay_qa_01", "github.issue.create"))
        # Unrelated tool must be blocked
        self.assertFalse(self.platform.agent_builder.can_agent_execute_tool("zynpay_qa_01", "email.send"))
        self.assertFalse(self.platform.agent_builder.can_agent_execute_tool("zynpay_qa_01", "file.delete"))

    # --- 122. Webhook Signature & Event Bus ---
    def test_golden_122_webhook_signature_and_event(self):
        secret = self.platform.webhook_gateway.secret_key
        t = time.time()
        nonce = "nonce_wh_122"
        raw = f"github:pull_request:{t}:{nonce}"
        sig = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()

        wh = WebhookPayload(
            webhook_id="wh_01",
            source="github",
            event_type="pull_request",
            payload={"repo": "ZynPay", "pr_number": 42},
            signature=sig,
            timestamp=t,
            nonce=nonce,
        )

        ok, msg = self.platform.webhook_gateway.verify_and_process(wh)
        self.assertTrue(ok)
        self.assertEqual(msg, "Webhook accepted.")

    # --- 123. Webhook Replay Attack Prevention ---
    def test_golden_123_webhook_replay_prevention(self):
        secret = self.platform.webhook_gateway.secret_key
        t = time.time()
        nonce = "nonce_replay_123"
        raw = f"github:push:{t}:{nonce}"
        sig = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()

        wh = WebhookPayload(
            webhook_id="wh_02",
            source="github",
            event_type="push",
            payload={"repo": "ZynPay"},
            signature=sig,
            timestamp=t,
            nonce=nonce,
        )

        # First call succeeds
        ok1, _ = self.platform.webhook_gateway.verify_and_process(wh)
        self.assertTrue(ok1)

        # Second call with same nonce fails
        ok2, msg2 = self.platform.webhook_gateway.verify_and_process(wh)
        self.assertFalse(ok2)
        self.assertIn("Replay attack detected", msg2)

    # --- 124. OpenAPI Importer ---
    def test_golden_124_openapi_import(self):
        from engine.platform.connectors import OpenAPIImporter
        sample_openapi = {
            "paths": {
                "/users": {
                    "get": {"summary": "List users", "operationId": "listUsers"},
                    "post": {"summary": "Create user", "operationId": "createUser"},
                }
            }
        }
        tools = OpenAPIImporter.parse_spec(sample_openapi)
        self.assertEqual(len(tools), 2)
        names = [t.name for t in tools]
        self.assertIn("api.listusers", names)
        self.assertIn("api.createuser", names)

    # --- 125. Database Read-Only Enforcement ---
    def test_golden_125_database_read_only_enforcement(self):
        from engine.platform.connectors import DatabaseConnector
        db = DatabaseConnector("test_db", allow_writes=False)
        db.connect()

        # Safe read query
        read_res = db.execute_action("db.query.read", {"query": "SELECT * FROM users"})
        self.assertEqual(read_res.status, "SUCCESS")

        # Destructive query MUST BE BLOCKED
        drop_res = db.execute_action("db.query.write", {"query": "DROP TABLE users"})
        self.assertEqual(drop_res.status, "BLOCKED")
        self.assertIn("blocked", drop_res.error.lower())

    # --- 126. Plugin Uninstall Test ---
    def test_golden_126_plugin_uninstall(self):
        manifest = ExtensionManifest(
            id="temp_plugin",
            name="Temporary Extension",
            version="1.0.0",
            type=ExtensionType.TOOL,
            description="Will be uninstalled",
            entrypoint="main.py",
            tools=["temp.tool"],
            permissions=PermissionManifest(),
        )
        self.platform.install_plugin_from_manifest(manifest)
        self.assertIsNotNone(self.platform.plugin_registry.get_plugin("temp_plugin"))

        # Uninstall
        un_ok, _ = self.platform.plugin_registry.uninstall_plugin("temp_plugin")
        self.assertTrue(un_ok)
        self.assertIsNone(self.platform.plugin_registry.get_plugin("temp_plugin"))

    # --- 127. Automation Rule Trigger ---
    def test_golden_127_automation_rule(self):
        rule = AutomationRule(
            rule_id="rule_gh_pr",
            name="PR Auto Test",
            event_type="GITHUB_PR_CREATED",
            conditions={"repo": "ZynPay"},
            action_skill="RunTestSuiteSkill",
        )
        self.platform.automation_builder.add_rule(rule)

        # Trigger event matching condition
        event = EventMessage(
            event_type="GITHUB_PR_CREATED",
            source="github",
            payload={"repo": "ZynPay", "pr": 12},
        )
        self.platform.event_bus.publish(event)
        self.assertEqual(rule.run_count, 1)


if __name__ == "__main__":
    unittest.main()
