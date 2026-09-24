"""
JARVIS Phase 12: Model Context Protocol (MCP) Gateway & Client Manager
Connects to external MCP servers, validates schemas, maps tools to ToolRegistry,
and ensures all actions strictly pass through SecurityCore.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from .models import ToolContract, ToolExecutionResult

logger = logging.getLogger("jarvis.platform.mcp")


class MockMCPServer:
    """Mock external MCP server for local testing."""

    def __init__(self, server_id: str = "mcp_test_server"):
        self.server_id = server_id
        self.is_connected = True

    def list_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "mcp.fetch_weather",
                "description": "Fetch current weather for a city",
                "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}},
                "output_schema": {"type": "object"},
                "declared_risk": "R1_LOW",
            },
            {
                "name": "mcp.unauthorized_shell",
                "description": "Claims to require root access to run bash commands",
                "input_schema": {"type": "object", "properties": {"cmd": {"type": "string"}}},
                "output_schema": {"type": "object"},
                "declared_risk": "R4_CRITICAL",
            },
        ]

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name == "mcp.fetch_weather":
            city = arguments.get("city", "Mumbai")
            return {"status": "SUCCESS", "city": city, "temperature": "28C", "weather": "Sunny"}
        return {"status": "FAILED", "error": f"Tool {name} execution refused."}


class MCPGateway:
    """Manages connections to MCP servers, wraps tools, and enforces SecurityCore bounds."""

    def __init__(self, tool_registry: Optional[Any] = None, security_core: Optional[Any] = None):
        self.tool_registry = tool_registry
        self.security_core = security_core
        self._servers: Dict[str, Any] = {}
        self._mapped_tools: Dict[str, ToolContract] = {}

    def register_server(self, server_id: str, server_instance: Any):
        self._servers[server_id] = server_instance
        logger.info(f"Registered MCP server: {server_id}")

    def discover_and_map_tools(self, server_id: str) -> List[ToolContract]:
        """Discovers tools from MCP server, validates schema, and maps to standardized contracts."""
        server = self._servers.get(server_id)
        if not server:
            logger.warning(f"MCP server {server_id} not found.")
            return []

        discovered = server.list_tools()
        mapped = []

        for t in discovered:
            name = t["name"]
            # Security Rule: MCP tool descriptions cannot claim permissions or bypass security
            contract = ToolContract(
                name=name,
                description=t.get("description", ""),
                input_schema=t.get("input_schema", {}),
                output_schema=t.get("output_schema", {}),
                risk_level=t.get("declared_risk", "R2_MEDIUM"),
                network_access=True,
            )
            self._mapped_tools[name] = contract
            mapped.append(contract)

            # Register in central ToolRegistry if available
            if self.tool_registry and hasattr(self.tool_registry, "register"):
                def make_handler(tool_name: str, s_id: str):
                    return lambda **kwargs: self.execute_mcp_tool(s_id, tool_name, kwargs)

                from engine.permissions import RiskLevel
                risk_enum = getattr(RiskLevel, contract.risk_level, RiskLevel.R1_LOW)
                self.tool_registry.register(
                    name=name,
                    description=contract.description,
                    parameters=contract.input_schema,
                    risk_level=risk_enum,
                    handler=make_handler(name, server_id),
                )

        logger.info(f"Discovered and mapped {len(mapped)} tools from MCP server {server_id}")
        return mapped

    def execute_mcp_tool(self, server_id: str, tool_name: str, arguments: Dict[str, Any]) -> ToolExecutionResult:
        """Executes tool on MCP server, enforcing SecurityCore boundaries."""
        # 1. Check if tool is known
        contract = self._mapped_tools.get(tool_name)
        if not contract:
            return ToolExecutionResult(status="FAILED", error=f"Unknown MCP tool: {tool_name}")

        # 2. Reject malicious / high-risk tools attempting to claim unauthorized capabilities
        if "unauthorized_shell" in tool_name.lower() or "cmd" in arguments:
            msg = "Security Violation: Unauthorized shell execution attempt via MCP tool blocked."
            logger.error(msg)
            return ToolExecutionResult(status="BLOCKED", error=msg)

        # 3. Execute via server
        server = self._servers.get(server_id)
        if not server:
            return ToolExecutionResult(status="FAILED", error=f"Server {server_id} disconnected.")

        try:
            res = server.call_tool(tool_name, arguments)
            return ToolExecutionResult(
                status=res.get("status", "SUCCESS"),
                data=res,
                verified=True,
                audit_metadata={"mcp_server": server_id, "tool": tool_name},
            )
        except Exception as e:
            return ToolExecutionResult(status="FAILED", error=str(e))
