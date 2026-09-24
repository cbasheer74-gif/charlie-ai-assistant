"""engine/agents/contract.py — Universal Agent Contract and Structured Result Protocol.

Defines the standard execution, verification, and recovery interface for all JARVIS
specialized agents.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from engine.autonomy.context import ExecutionContext
    from engine.autonomy.task_graph import TaskNode



@dataclass
class AgentResult:
    """Structured response returned by every agent on task completion or failure."""
    status: str  # SUCCESS, PARTIAL, FAILED, BLOCKED, WAITING_USER
    output: Any = None
    files_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    observations: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    verification: Dict[str, Any] = field(default_factory=dict)
    memory_candidates: List[Dict[str, Any]] = field(default_factory=list)
    next_recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AgentContract(ABC):
    """Universal contract for specialized agents in JARVIS autonomous orchestration."""

    name: str = "BaseAgent"
    description: str = ""

    @abstractmethod
    def can_handle(self, task: TaskNode) -> bool:
        """Return True if this agent is equipped to execute the given task node."""
        pass

    def prepare(self, task: TaskNode, context: ExecutionContext) -> Dict[str, Any]:
        """Pre-execution setup: gather environment state, lock resources, retrieve memory."""
        return {}

    @abstractmethod
    def execute(self, task: TaskNode, context: ExecutionContext) -> AgentResult:
        """Run the core logic of the task node using available tools."""
        pass

    def verify(self, task: TaskNode, result: AgentResult, context: ExecutionContext) -> Tuple[bool, str]:
        """Validate that the task's expected output criteria were physically achieved."""
        if result.status != "SUCCESS":
            return False, f"Execution returned status: {result.status}"
        return True, "Verification standard met."

    def recover(self, task: TaskNode, error: str, context: ExecutionContext) -> AgentResult:
        """Attempt safe local recovery after a failure before escalating to replanner."""
        return AgentResult(
            status="FAILED",
            errors=[error],
            next_recommendation="Escalate to Replanner",
        )

    def summarize_result(self, result: AgentResult) -> str:
        """Produce a terse status message."""
        if result.status == "SUCCESS":
            created_str = f" Created: {len(result.files_created)}" if result.files_created else ""
            return f"[{self.name}] Completed successfully.{created_str}"
        return f"[{self.name}] Finished with status: {result.status}. Errors: {len(result.errors)}"
