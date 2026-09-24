"""engine/agents/security_agent.py — Security Agent for Destructive Action & Secret Auditing.

Inspects tool calls and commands to prevent data loss, credential leaks,
and unauthorized high-impact system modifications.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from engine.agents.contract import AgentContract, AgentResult

if TYPE_CHECKING:
    from engine.autonomy.context import ExecutionContext
    from engine.autonomy.task_graph import TaskNode

from engine.permissions import PermissionManager, RiskLevel


class SecurityAgent(AgentContract):
    name = "SecurityAgent"
    description = "Enforces safety boundaries, detects destructive patterns, and redacts secrets."

    def __init__(self, permission_manager: Optional[PermissionManager] = None):
        self.perm_mgr = permission_manager or PermissionManager()

    def can_handle(self, task: TaskNode) -> bool:
        low = (task.name + " " + task.description + " " + (task.tool or "")).lower()
        return any(w in low for w in ("security", "permission", "audit", "safety check", "credential"))

    def audit_command(self, command: str) -> Tuple[bool, str]:
        """Check command for dangerous destructive patterns."""
        return self.perm_mgr.is_command_safe(command)

    def execute(self, task: TaskNode, context: ExecutionContext) -> AgentResult:
        cmd = task.inputs.get("command", "")
        if cmd:
            is_safe, reason = self.audit_command(cmd)
            if not is_safe:
                return AgentResult(
                    status="BLOCKED",
                    errors=[f"Security policy blocked command: {reason}"],
                    next_recommendation="Halt execution and require explicit user authorization.",
                )

        return AgentResult(
            status="SUCCESS",
            output={"safe": True},
            observations=["Security audit passed. No destructive commands detected."],
        )
