"""
JARVIS Phase 12: Master Developer Platform Architecture
Unifies Plugin Registry, Tool SDK, Connector Ecosystem, MCP Gateway, Custom Agent Builder,
and Developer Console.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from .agent_builder import CustomAgentBuilder
from .connectors import DatabaseConnector, GitHubConnector, SlackConnector
from .events_webhooks import AutomationBuilder, EventBus, WebhookGateway
from .mcp import MCPGateway, MockMCPServer
from .models import (
    AutomationRule,
    CustomAgentSpec,
    ExtensionManifest,
    ExtensionType,
    PermissionManifest,
    PluginLifecycle,
    ToolContract,
    ToolExecutionResult,
)
from .registry import ExtensionHealthManager, PluginRegistry
from .security import CredentialBindingManager, ExtensionSandbox, PluginSecurityScanner
from .tool_resolver import ToolResolver

logger = logging.getLogger("jarvis.platform.core")


class DeveloperPlatform:
    """Master Developer Platform integrating extensible capabilities into JARVIS."""

    def __init__(self, tool_registry: Optional[Any] = None, security_core: Optional[Any] = None):
        self.tool_registry = tool_registry
        self.security_core = security_core

        # 1. Security & Registry
        self.security_scanner = PluginSecurityScanner()
        self.credential_binding = CredentialBindingManager()
        self.plugin_registry = PluginRegistry(scanner=self.security_scanner)
        self.health_manager = self.plugin_registry.health_manager

        # 2. Tool Resolver
        self.tool_resolver = ToolResolver()

        # 3. Connectors & MCP
        self.mcp_gateway = MCPGateway(tool_registry=self.tool_registry, security_core=self.security_core)
        self.github_connector = GitHubConnector("github_builtin")
        self.slack_connector = SlackConnector("slack_builtin")
        self.db_connector = DatabaseConnector("db_builtin")

        # 4. Custom Agents & Automations
        self.agent_builder = CustomAgentBuilder()
        self.event_bus = EventBus()
        self.webhook_gateway = WebhookGateway()
        self.automation_builder = AutomationBuilder(self.event_bus)

        self._init_builtins()
        logger.info("DeveloperPlatform initialized.")

    def _init_builtins(self):
        """Registers built-in mock MCP server and baseline tools."""
        # 1. Mock MCP server
        mock_server = MockMCPServer("default_mcp_mock")
        self.mcp_gateway.register_server("default_mcp_mock", mock_server)
        self.mcp_gateway.discover_and_map_tools("default_mcp_mock")

        # 2. Register tools with resolver
        t_excel = ToolContract(
            name="excel.clean_data",
            description="Cleans spreadsheet columns, strips nulls and whitespace",
            input_schema={"file_path": "string"},
            output_schema={"cleaned_rows": "integer"},
        )
        t_gh = ToolContract(
            name="github.issue.create",
            description="Creates a new issue in a GitHub repository",
            input_schema={"title": "string", "repo": "string"},
            output_schema={"issue_id": "integer"},
        )
        self.tool_resolver.register_tool(t_excel)
        self.tool_resolver.register_tool(t_gh)

    def install_plugin_from_manifest(self, manifest: ExtensionManifest) -> Tuple[bool, str]:
        """Installs and verifies an extension plugin."""
        ok, msg = self.plugin_registry.install_plugin(manifest)
        if not ok:
            return False, msg

        # Bind credentials
        creds = self.credential_binding.get_scoped_credentials(manifest)

        # Enable plugin
        self.plugin_registry.enable_plugin(manifest.id)
        return True, f"Plugin {manifest.id} installed and enabled."

    def execute_tool_sandboxed(self, tool_name: str, parameters: Dict[str, Any]) -> ToolExecutionResult:
        """Executes a tool with active sandbox checks (filesystem, network)."""
        sandbox = self.plugin_registry.get_sandbox_for_tool(tool_name)

        # If tool belongs to a sandboxed plugin, enforce checks
        if sandbox:
            # 1. Network check
            if "url" in parameters or "domain" in parameters:
                domain = parameters.get("domain", parameters.get("url", ""))
                net_ok, net_msg = sandbox.check_network_access(domain)
                if not net_ok:
                    return ToolExecutionResult(status="BLOCKED", error=net_msg)

            # 2. File check
            if "path" in parameters or "file_path" in parameters:
                f_path = parameters.get("path", parameters.get("file_path", ""))
                file_ok, file_msg = sandbox.check_file_access(f_path)
                if not file_ok:
                    return ToolExecutionResult(status="BLOCKED", error=file_msg)

        # Execute via connector or native tool
        if tool_name.startswith("github."):
            return self.github_connector.execute_action(tool_name, parameters)
        elif tool_name.startswith("slack."):
            return self.slack_connector.execute_action(tool_name, parameters)
        elif tool_name.startswith("db."):
            return self.db_connector.execute_action(tool_name, parameters)

        return ToolExecutionResult(status="SUCCESS", data={"result": "Executed native tool"}, verified=True)
