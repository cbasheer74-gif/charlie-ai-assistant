"""engine/autonomy/context.py — Shared Execution Context and Artifact Registry for Multi-Agent Workflows.

Maintains execution state, tracked artifacts, agent observations, memory snapshots,
and inter-agent handoff data without blowing up context windows.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ArtifactRecord:
    """Represents a tangible file or generated output produced during task execution."""
    path: str
    type: str  # script, video, report, source_code, log, prompt, chart
    creator_agent: str
    task_id: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    verified: bool = False
    version: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ArtifactRegistry:
    """Thread-safe catalog of generated outputs across all agents in an autonomous run."""

    def __init__(self):
        self._artifacts: Dict[str, ArtifactRecord] = {}

    def register(
        self,
        path: str,
        artifact_type: str,
        creator_agent: str,
        task_id: str,
        verified: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ArtifactRecord:
        norm_path = str(Path(path).resolve()) if path else ""
        existing = self._artifacts.get(norm_path)
        version = (existing.version + 1) if existing else 1

        rec = ArtifactRecord(
            path=norm_path,
            type=artifact_type,
            creator_agent=creator_agent,
            task_id=task_id,
            verified=verified,
            version=version,
            metadata=metadata or {},
        )
        self._artifacts[norm_path] = rec
        return rec

    def get(self, path: str) -> Optional[ArtifactRecord]:
        norm = str(Path(path).resolve())
        return self._artifacts.get(norm)

    def mark_verified(self, path: str) -> bool:
        norm = str(Path(path).resolve())
        rec = self._artifacts.get(norm)
        if rec:
            rec.verified = True
            return True
        return False

    def list_by_task(self, task_id: str) -> List[ArtifactRecord]:
        return [a for a in self._artifacts.values() if a.task_id == task_id]

    def list_by_type(self, artifact_type: str) -> List[ArtifactRecord]:
        return [a for a in self._artifacts.values() if a.type == artifact_type]

    def all(self) -> List[ArtifactRecord]:
        return list(self._artifacts.values())

    def to_dict_list(self) -> List[Dict[str, Any]]:
        return [a.to_dict() for a in self._artifacts.values()]


@dataclass
class ExecutionContext:
    """Shared blackboard and state machine environment passed across collaborating agents."""
    task_id: str
    goal: str
    project_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    current_step: str = ""
    artifacts: ArtifactRegistry = field(default_factory=ArtifactRegistry)
    memory_context: Dict[str, Any] = field(default_factory=dict)
    available_tools: List[str] = field(default_factory=list)
    permission_state: Dict[str, Any] = field(default_factory=dict)
    recent_actions: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    checkpoints: List[Dict[str, Any]] = field(default_factory=list)
    shared_data: Dict[str, Any] = field(default_factory=dict)
    computer_state: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def record_action(self, agent: str, tool: str, arguments: Dict[str, Any], result: Any, status: str = "SUCCESS"):
        self.recent_actions.append({
            "timestamp": datetime.now().isoformat(),
            "agent": agent,
            "tool": tool,
            "arguments": arguments,
            "result_summary": str(result)[:300],
            "status": status,
        })
        # Keep last 50 actions to avoid memory bloat
        if len(self.recent_actions) > 50:
            self.recent_actions = self.recent_actions[-50:]
        self.updated_at = datetime.now().isoformat()

    def record_error(self, agent: str, tool: str, error: str, context_details: Optional[Dict[str, Any]] = None):
        self.errors.append({
            "timestamp": datetime.now().isoformat(),
            "agent": agent,
            "tool": tool,
            "error": error,
            "context": context_details or {},
        })
        self.updated_at = datetime.now().isoformat()

    def set_handoff(self, key: str, value: Any):
        """Pass structured data from one agent to subsequent agents."""
        self.shared_data[key] = value
        self.updated_at = datetime.now().isoformat()

    def get_handoff(self, key: str, default: Any = None) -> Any:
        return self.shared_data.get(key, default)

    def snapshot(self) -> Dict[str, Any]:
        """Serialize current execution state for durable checkpointing."""
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "project_id": self.project_id,
            "parent_task_id": self.parent_task_id,
            "current_step": self.current_step,
            "artifacts": self.artifacts.to_dict_list(),
            "memory_context": self.memory_context,
            "shared_data": self.shared_data,
            "errors_count": len(self.errors),
            "recent_actions_count": len(self.recent_actions),
            "updated_at": self.updated_at,
        }
