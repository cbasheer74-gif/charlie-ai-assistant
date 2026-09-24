"""
JARVIS Phase 12: Custom Agent Builder & Templates
Allows no-code and programmatic creation of specialized agents with scoped tools, memory, and permissions.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .models import CustomAgentSpec, MemoryScope

logger = logging.getLogger("jarvis.platform.agent_builder")


class CustomAgentBuilder:
    """Factory and registry for user-defined custom agents."""

    def __init__(self):
        self._agents: Dict[str, CustomAgentSpec] = {}
        self._init_default_templates()

    def _init_default_templates(self):
        """Initializes standard starter templates."""
        # 1. QA Testing Agent
        qa_spec = CustomAgentSpec(
            agent_id="template_qa_agent",
            name="ZynPay QA Agent",
            role="Automated Quality Assurance and Test Runner",
            instructions="Run tests, inspect build logs, report issues. Do not send external emails or modify source files.",
            allowed_tools=["test.run", "logs.inspect", "github.issue.list", "github.issue.create"],
            allowed_models=["local_coder_7b", "cloud_strong_reasoning"],
            memory_scope=MemoryScope.PROJECT,
            project_scope="ZynPay",
            autonomy_level="SUPERVISED",
            is_certified=True,
        )

        # 2. Finance Report Agent
        finance_spec = CustomAgentSpec(
            agent_id="template_finance_agent",
            name="Finance Analyst Agent",
            role="Financial Spreadsheet and Ledger Analyzer",
            instructions="Analyze ledger csv files and generate summaries. Read-only permissions.",
            allowed_tools=["excel.read", "excel.summarize", "db.query.read"],
            allowed_models=["local_fast_small", "cloud_fast_cheap"],
            memory_scope=MemoryScope.SESSION,
            autonomy_level="READ_ONLY",
            is_certified=True,
        )

        self._agents[qa_spec.agent_id] = qa_spec
        self._agents[finance_spec.agent_id] = finance_spec

    def create_agent(
        self,
        agent_id: str,
        name: str,
        role: str,
        instructions: str,
        allowed_tools: List[str],
        project_scope: Optional[str] = None,
        memory_scope: MemoryScope = MemoryScope.PROJECT,
        autonomy_level: str = "SUPERVISED",
    ) -> CustomAgentSpec:
        """Creates and registers a custom agent with strict tool boundaries."""
        spec = CustomAgentSpec(
            agent_id=agent_id,
            name=name,
            role=role,
            instructions=instructions,
            allowed_tools=allowed_tools,
            memory_scope=memory_scope,
            project_scope=project_scope,
            autonomy_level=autonomy_level,
            is_certified=False,
        )
        self._agents[agent_id] = spec
        logger.info(f"Custom Agent created: {name} (ID: {agent_id}, Allowed Tools: {allowed_tools})")
        return spec

    def get_agent(self, agent_id: str) -> Optional[CustomAgentSpec]:
        return self._agents.get(agent_id)

    def list_agents(self) -> List[CustomAgentSpec]:
        return list(self._agents.values())

    def can_agent_execute_tool(self, agent_id: str, tool_name: str) -> bool:
        agent = self.get_agent(agent_id)
        if not agent:
            return False
        return tool_name in agent.allowed_tools
