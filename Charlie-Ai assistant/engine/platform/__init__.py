"""
JARVIS Phase 12: Developer Platform Package
Exposes DeveloperPlatform, SDKs, registries, connectors, MCP gateway, and agent builder.
"""

from .agent_builder import CustomAgentBuilder
from .connectors import DatabaseConnector, GitHubConnector, OpenAPIImporter, SlackConnector
from .core import DeveloperPlatform
from .events_webhooks import AutomationBuilder, EventBus, WebhookGateway
from .mcp import MCPGateway, MockMCPServer
from .models import (
    AutomationRule,
    ConnectorContract,
    CustomAgentSpec,
    EventMessage,
    ExtensionManifest,
    ExtensionType,
    MemoryScope,
    PermissionManifest,
    PluginLifecycle,
    ToolContract,
    ToolExecutionResult,
    TrustStatus,
    WebhookPayload,
)
from .registry import ExtensionHealthManager, PluginRegistry
from .sdk import BaseConnector, BaseCustomAgent, BaseTool
from .security import CredentialBindingManager, ExtensionSandbox, PluginSecurityScanner
from .tool_resolver import ToolResolver

__all__ = [
    "DeveloperPlatform",
    "PluginRegistry",
    "ExtensionHealthManager",
    "PluginSecurityScanner",
    "ExtensionSandbox",
    "CredentialBindingManager",
    "ToolResolver",
    "MCPGateway",
    "MockMCPServer",
    "GitHubConnector",
    "SlackConnector",
    "DatabaseConnector",
    "OpenAPIImporter",
    "CustomAgentBuilder",
    "EventBus",
    "WebhookGateway",
    "AutomationBuilder",
    "BaseTool",
    "BaseConnector",
    "BaseCustomAgent",
    "ExtensionManifest",
    "PermissionManifest",
    "ToolContract",
    "ToolExecutionResult",
    "ConnectorContract",
    "CustomAgentSpec",
    "EventMessage",
    "WebhookPayload",
    "AutomationRule",
    "ExtensionType",
    "PluginLifecycle",
    "TrustStatus",
    "MemoryScope",
]
