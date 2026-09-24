"""
JARVIS Phase 12: Extension SDK
Standardized developer base classes for Tools, Connectors, Custom Agents, and Skills.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging
from typing import Any, Dict, List, Optional, Tuple

from .models import ConnectorContract, CustomAgentSpec, ToolContract, ToolExecutionResult

logger = logging.getLogger("jarvis.platform.sdk")


class BaseTool(ABC):
    """Developer base class for custom tools."""

    def __init__(self, contract: ToolContract):
        self.contract = contract

    @abstractmethod
    def execute(self, **kwargs) -> ToolExecutionResult:
        """Executes the tool logic with keyword parameters."""
        pass

    def verify(self, result: ToolExecutionResult) -> Tuple[bool, str]:
        """Verifies whether tool execution completed as expected."""
        return True, "Default verification passed."

    def rollback(self, result: ToolExecutionResult) -> Tuple[bool, str]:
        """Reverts changes if tool supports rollback."""
        return False, "Rollback not supported for this tool."

    def health_check(self) -> bool:
        return True


class BaseConnector(ABC):
    """Developer base class for external service connectors (GitHub, Slack, CRM, DB)."""

    def __init__(self, connector_id: str, credentials: Optional[Dict[str, str]] = None):
        self.connector_id = connector_id
        self.credentials = credentials or {}
        self.is_connected = False

    @abstractmethod
    def connect(self) -> bool:
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        pass

    @abstractmethod
    def list_capabilities(self) -> List[str]:
        pass

    @abstractmethod
    def execute_action(self, action_name: str, parameters: Dict[str, Any]) -> ToolExecutionResult:
        pass

    def health_check(self) -> bool:
        return self.is_connected


class BaseCustomAgent(ABC):
    """Developer base class for specialized custom agents."""

    def __init__(self, spec: CustomAgentSpec):
        self.spec = spec

    @abstractmethod
    def run_task(self, goal: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        pass

    def can_use_tool(self, tool_name: str) -> bool:
        return tool_name in self.spec.allowed_tools
