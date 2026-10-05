"""engine/autonomy/resume_manager.py — Checkpoint Persistence and Resume Manager.

Allows CHARLIE to recover multi-step autonomous workflows after application restarts,
user pauses, or transient system interruptions.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from engine.autonomy.context import ExecutionContext
from engine.autonomy.task_graph import TaskGraph, TaskNode, TaskStatus
from engine.memory_manager import MemoryManager


class CheckpointManager:
    """Saves and retrieves durable task graph snapshots in SQLite."""

    def __init__(self, memory_manager: MemoryManager):
        self.memory = memory_manager

    def save_checkpoint(
        self,
        graph: TaskGraph,
        context: ExecutionContext,
        current_stage: str = "",
        status: Optional[str] = None,
    ) -> str:
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

        # Derive task status if not explicitly passed
        if status is None:
            stage_low = current_stage.lower()
            if graph.is_completed() or "completed" in stage_low:
                status = "COMPLETED"
            elif "loop hard-stop" in stage_low or "cost hard-stop" in stage_low or "halted" in stage_low:
                status = "STOPPED"
            elif "budget" in stage_low or "timeout" in stage_low or "partial" in stage_low:
                status = "PARTIAL"
            elif "pause" in stage_low:
                status = "PAUSED"
            else:
                status = "RUNNING"

        return self.memory.store_task_checkpoint(
            task_id=graph.graph_id,
            checkpoint_data=checkpoint_data,
            summary=summary_text,
            status=status,
        )

    def load_checkpoint(self, task_id: str) -> Optional[Dict[str, Any]]:
        row = self.memory.get_task(task_id)
        if not row or not row.get("last_checkpoint"):
            return None
        try:
            return json.loads(row["last_checkpoint"])
        except Exception:
            return None

    def delete_checkpoint(self, task_id: str) -> bool:
        """Mark checkpoint/task cancelled in memory."""
        return self.memory.cancel_task(task_id)


class ResumeManager:
    """Restores execution state, re-observes desktop context, and returns ready tasks."""

    def __init__(self, memory_manager: MemoryManager, checkpoint_manager: CheckpointManager):
        self.memory = memory_manager
        self.checkpointer = checkpoint_manager

    def list_resumable_tasks(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List summary of all incomplete/resumable tasks with saved checkpoints."""
        rows = self.memory.list_incomplete_tasks(project_id=project_id)
        resumable: List[Dict[str, Any]] = []
        for r in rows:
            task_id = r["id"]
            chk = self.checkpointer.load_checkpoint(task_id)
            if not chk or "graph" not in chk:
                continue
            graph_data = chk.get("graph", {})
            nodes = graph_data.get("nodes", {})
            total = len(nodes)
            completed = sum(1 for n in nodes.values() if n.get("status") == "COMPLETED")
            percent = int((completed / total * 100)) if total else 0

            resumable.append({
                "task_id": task_id,
                "goal": r.get("goal") or graph_data.get("goal", ""),
                "project_id": r.get("project_name") or r.get("project_id"),
                "status": r.get("status", "PAUSED"),
                "current_stage": chk.get("current_stage", "Checkpoint"),
                "saved_at": chk.get("saved_at", r.get("started_at", "")),
                "progress": {
                    "completed": completed,
                    "total": total,
                    "percent": percent,
                },
            })
        return resumable

    def get_resumable_task(
        self,
        task_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Optional[Tuple[TaskGraph, ExecutionContext, str]]:
        """Retrieve and reconstruct the most recent incomplete task checkpoint."""
        if task_id:
            active_task_row = self.memory.get_task(task_id)
        else:
            active_task_row = self.memory.resume_task(project_id=project_id)

        if not active_task_row:
            return None

        resolved_task_id = active_task_row["id"]
        chk = self.checkpointer.load_checkpoint(resolved_task_id)
        if not chk or "graph" not in chk:
            return None

        # Reconstruct TaskGraph
        graph = TaskGraph.from_dict(chk["graph"])

        # Reconstruct ExecutionContext
        ctx_data = chk.get("context", {})
        context = ExecutionContext(
            task_id=ctx_data.get("task_id", resolved_task_id),
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
                task_id=resolved_task_id,
                verified=art.get("verified", False),
                metadata=art.get("metadata", {}),
            )

        # Dependency-aware node reset:
        # Reset in-flight or recovering nodes:
        # If all its dependencies are COMPLETED -> mark READY; else PENDING
        for node in graph.nodes.values():
            if node.status in (TaskStatus.RUNNING, TaskStatus.VERIFYING, TaskStatus.RECOVERING):
                deps_met = all(
                    graph.nodes.get(d) and graph.nodes[d].status == TaskStatus.COMPLETED
                    for d in node.dependencies
                )
                node.status = TaskStatus.READY if deps_met else TaskStatus.PENDING
            elif node.status == TaskStatus.PENDING:
                if all(
                    graph.nodes.get(d) and graph.nodes[d].status == TaskStatus.COMPLETED
                    for d in node.dependencies
                ):
                    node.status = TaskStatus.READY

        stage = chk.get("current_stage", "Resumed")
        return graph, context, stage

    def cancel_resumable_task(self, task_id: str) -> bool:
        """Cancel an incomplete task so it won't be resumed."""
        return self.memory.cancel_task(task_id)
