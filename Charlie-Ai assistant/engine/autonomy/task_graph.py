"""engine/autonomy/task_graph.py — Dependency-Aware Task Graph (DAG) for Autonomous Workflows.

Supports topological dependency execution, dynamic in-flight replanning,
checkpoint tracking, and inter-node parameter propagation.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    BLOCKED = "BLOCKED"
    WAITING_USER = "WAITING_USER"
    FAILED = "FAILED"
    RECOVERING = "RECOVERING"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"


@dataclass
class TaskNode:
    """Individual action node within an execution graph."""
    id: str
    name: str
    description: str
    agent: str
    tool: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    priority: str = "NORMAL"  # URGENT, HIGH, NORMAL, LOW
    risk: str = "SAFE_WRITE"  # READ_ONLY, SAFE_WRITE, SYSTEM_CHANGE, HIGH_IMPACT
    retry_count: int = 0
    max_retries: int = 2
    verification: Optional[str] = None  # python_syntax, excel_integrity, video_output, file_exists, etc.
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    checkpoint_required: bool = False
    evidence: str = ""
    error: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value if isinstance(self.status, TaskStatus) else str(self.status)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TaskNode:
        import inspect
        valid_fields = set(inspect.signature(cls).parameters.keys())
        data_copy = {k: v for k, v in data.items() if k in valid_fields}
        if "status" in data_copy and isinstance(data_copy["status"], str):
            try:
                data_copy["status"] = TaskStatus(data_copy["status"])
            except ValueError:
                data_copy["status"] = TaskStatus.PENDING
        return cls(**data_copy)


class TaskGraph:
    """Directed Acyclic Graph managing multi-agent task execution dependencies."""

    def __init__(self, graph_id: str, goal: str):
        self.graph_id = graph_id
        self.goal = goal
        self.nodes: Dict[str, TaskNode] = {}
        self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()

    def add_node(self, node: TaskNode):
        self.nodes[node.id] = node
        self.updated_at = datetime.now().isoformat()

    def get_node(self, node_id: str) -> Optional[TaskNode]:
        return self.nodes.get(node_id)

    def get_ready_nodes(self) -> List[TaskNode]:
        """Return nodes whose upstream dependencies are all COMPLETED or SKIPPED."""
        if self.detect_cycles():
            return []

        ready: List[TaskNode] = []
        for node in self.nodes.values():
            if node.status in (TaskStatus.PENDING, TaskStatus.READY, TaskStatus.BLOCKED):
                deps_satisfied = True
                for dep_id in node.dependencies:
                    dep_node = self.nodes.get(dep_id)
                    if not dep_node or dep_node.status not in (TaskStatus.COMPLETED, TaskStatus.SKIPPED):
                        deps_satisfied = False
                        break
                if deps_satisfied:
                    node.status = TaskStatus.READY
                    ready.append(node)
                else:
                    node.status = TaskStatus.BLOCKED
        return ready

    def mark_running(self, node_id: str):
        node = self.nodes.get(node_id)
        if node:
            node.status = TaskStatus.RUNNING
            node.started_at = datetime.now().isoformat()
            self.updated_at = datetime.now().isoformat()

    def mark_verifying(self, node_id: str):
        node = self.nodes.get(node_id)
        if node:
            node.status = TaskStatus.VERIFYING
            self.updated_at = datetime.now().isoformat()

    def mark_completed(self, node_id: str, outputs: Optional[Dict[str, Any]] = None, evidence: str = ""):
        node = self.nodes.get(node_id)
        if node:
            node.status = TaskStatus.COMPLETED
            node.completed_at = datetime.now().isoformat()
            node.evidence = evidence
            if outputs:
                node.outputs.update(outputs)
            self.updated_at = datetime.now().isoformat()

    def mark_failed(self, node_id: str, error: str = ""):
        node = self.nodes.get(node_id)
        if node:
            node.status = TaskStatus.FAILED
            node.error = error
            self.updated_at = datetime.now().isoformat()

    def mark_skipped(self, node_id: str):
        node = self.nodes.get(node_id)
        if node:
            node.status = TaskStatus.SKIPPED
            self.updated_at = datetime.now().isoformat()

    def mark_recovering(self, node_id: str):
        node = self.nodes.get(node_id)
        if node:
            node.status = TaskStatus.RECOVERING
            node.retry_count += 1
            self.updated_at = datetime.now().isoformat()

    def is_completed(self) -> bool:
        """True if all nodes are either COMPLETED or SKIPPED."""
        if not self.nodes:
            return False
        return all(n.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED) for n in self.nodes.values())

    def has_failures(self) -> bool:
        """True if any node is in FAILED state and cannot retry."""
        return any(
            n.status == TaskStatus.FAILED and n.retry_count >= n.max_retries
            for n in self.nodes.values()
        )

    def get_progress(self) -> Dict[str, Any]:
        total = len(self.nodes)
        if total == 0:
            return {"total": 0, "completed": 0, "percent": 100, "status": "COMPLETED"}

        counts = {s.value: 0 for s in TaskStatus}
        for n in self.nodes.values():
            counts[n.status.value] = counts.get(n.status.value, 0) + 1

        completed = counts[TaskStatus.COMPLETED.value] + counts[TaskStatus.SKIPPED.value]
        percent = int((completed / total) * 100)

        return {
            "total": total,
            "completed": completed,
            "pending": counts[TaskStatus.PENDING.value] + counts[TaskStatus.BLOCKED.value],
            "running": counts[TaskStatus.RUNNING.value] + counts[TaskStatus.VERIFYING.value],
            "failed": counts[TaskStatus.FAILED.value],
            "recovering": counts[TaskStatus.RECOVERING.value],
            "percent": percent,
        }

    def detect_cycles(self) -> bool:
        """Cycle detection using depth-first search colors."""
        visited: Dict[str, int] = {k: 0 for k in self.nodes}  # 0=white, 1=gray, 2=black

        def dfs(node_id: str) -> bool:
            visited[node_id] = 1
            node = self.nodes.get(node_id)
            if node:
                for dep in node.dependencies:
                    if dep in self.nodes:
                        if visited[dep] == 1:
                            return True  # cycle found
                        if visited[dep] == 0 and dfs(dep):
                            return True
            visited[node_id] = 2
            return False

        for nid in self.nodes:
            if visited[nid] == 0:
                if dfs(nid):
                    return True
        return False

    def update_downstream_inputs(self, key: str, value: Any, from_node_id: Optional[str] = None):
        """Propagate output parameters to downstream nodes."""
        for node in self.nodes.values():
            if from_node_id is None or from_node_id in node.dependencies:
                node.inputs[key] = value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "goal": self.goal,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "nodes": {nid: node.to_dict() for nid, node in self.nodes.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TaskGraph:
        graph = cls(graph_id=data["graph_id"], goal=data["goal"])
        graph.created_at = data.get("created_at", datetime.now().isoformat())
        graph.updated_at = data.get("updated_at", datetime.now().isoformat())
        for nid, node_data in data.get("nodes", {}).items():
            graph.nodes[nid] = TaskNode.from_dict(node_data)
        return graph
