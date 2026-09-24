"""engine/autonomy/resume_manager.py — Checkpoint Persistence and Resume Manager.

Allows JARVIS to recover multi-step autonomous workflows after application restarts,
user pauses, or transient system interruptions.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from engine.autonomy.context import ExecutionContext
from engine.autonomy.task_graph import TaskGraph, TaskNode, TaskStatus
from engine.memory_manager import MemoryManager


class CheckpointManager:
    """Saves and retrieves durable task graph snapshots in SQLite."""

    def __init__(self, memory_manager: MemoryManager):
        self.memory = memory_manager

    def save_checkpoint(self, graph: TaskGraph, context: ExecutionContext, current_stage: str = "") -> str:
        checkpoint_data = {
            "graph": graph.to_dict(),
            "context": context.snapshot(),
            "current_stage": current_stage,
            "saved_at": datetime.now().isoformat(),
        }
        summary_text = (
            f"Stage: {current_stage} | "
            f"Completed: {graph.get_progress()['completed']}/{graph.get_progress()['total']} | "
            f"Artifacts: {len(context.artifacts.all())}"
        )

        return self.memory.store_task_checkpoint(
            task_id=graph.graph_id,
            checkpoint_data=checkpoint_data,
            summary=summary_text,
        )

    def load_checkpoint(self, task_id: str) -> Optional[Dict[str, Any]]:
        row = self.memory.get_task(task_id)
        if not row or not row.get("last_checkpoint"):
            return None
        try:
            return json.loads(row["last_checkpoint"])
        except Exception:
            return None


class ResumeManager:
    """Restores execution state, re-observes desktop context, and returns ready tasks."""

    def __init__(self, memory_manager: MemoryManager, checkpoint_manager: CheckpointManager):
        self.memory = memory_manager
        self.checkpointer = checkpoint_manager

    def get_resumable_task(self, project_id: Optional[str] = None) -> Optional[Tuple[TaskGraph, ExecutionContext, str]]:
        """Retrieve most recent incomplete task checkpoint."""
        active_task_row = self.memory.resume_task(project_id=project_id)
        if not active_task_row:
            return None

        task_id = active_task_row["id"]
        chk = self.checkpointer.load_checkpoint(task_id)
        if not chk or "graph" not in chk:
            return None

        # Reconstruct TaskGraph
        graph = TaskGraph.from_dict(chk["graph"])

        # Reconstruct ExecutionContext
        ctx_data = chk.get("context", {})
        context = ExecutionContext(
            task_id=ctx_data.get("task_id", task_id),
            goal=ctx_data.get("goal", graph.goal),
            project_id=ctx_data.get("project_id", project_id),
            current_step=ctx_data.get("current_step", ""),
            shared_data=ctx_data.get("shared_data", {}),
            memory_context=ctx_data.get("memory_context", {}),
        )

        # Restore artifacts
        for art in ctx_data.get("artifacts", []):
            context.artifacts.register(
                path=art.get("path", ""),
                artifact_type=art.get("type", "file"),
                creator_agent=art.get("creator_agent", "unknown"),
                task_id=task_id,
                verified=art.get("verified", False),
                metadata=art.get("metadata", {}),
            )

        # Reset any node that was left in RUNNING or RECOVERING to READY/PENDING
        for node in graph.nodes.values():
            if node.status in (TaskStatus.RUNNING, TaskStatus.VERIFYING, TaskStatus.RECOVERING):
                node.status = TaskStatus.READY

        stage = chk.get("current_stage", "Resumed")
        return graph, context, stage
