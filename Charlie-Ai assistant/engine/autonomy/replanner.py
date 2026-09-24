"""engine/autonomy/replanner.py — In-Flight Task Graph Replanner.

Dynamically adapts task graph branches when tools fail, assumptions invalidate,
or user interrupts with new parameters, preserving already-completed work.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from engine.autonomy.task_graph import TaskGraph, TaskNode, TaskStatus


class Replanner:
    """Modifies targeted TaskGraph sub-branches without invalidating completed work."""

    @staticmethod
    def replan_on_failure(
        graph: TaskGraph,
        failed_node_id: str,
        error_msg: str,
        alternative_agent: Optional[str] = None,
        alternative_tool: Optional[str] = None,
    ) -> bool:
        """Replace or augment a failing node with an alternative recovery path."""
        failed_node = graph.get_node(failed_node_id)
        if not failed_node:
            return False

        # Mark original node as FAILED or RECOVERING
        failed_node.status = TaskStatus.RECOVERING

        # Strategy 1: If alternative agent/tool provided, shift execution strategy on this node
        if alternative_tool or alternative_agent:
            failed_node.agent = alternative_agent or failed_node.agent
            failed_node.tool = alternative_tool or failed_node.tool
            failed_node.retry_count += 1
            failed_node.status = TaskStatus.READY
            failed_node.error = f"Replanned after error: {error_msg}"
            return True

        # Strategy 2: Common domain fallbacks
        low_tool = (failed_node.tool or "").lower()
        if "gui" in low_tool or "desktop" in low_tool:
            # Fall back from GUI to CLI/API
            failed_node.tool = "powershell_execute"
            failed_node.error = f"Replanned: Switched from GUI to direct CLI tool after failure."
            failed_node.status = TaskStatus.READY
            return True

        if failed_node.agent == "VideoAgent" and "ffmpeg" not in low_tool:
            # Shift video editing to direct ffmpeg composition
            failed_node.tool = "video_studio"
            failed_node.status = TaskStatus.READY
            return True

        # If retries exceeded, create a diagnostic/fallback branch node
        alt_id = f"node_alt_{uuid.uuid4().hex[:6]}"
        alt_node = TaskNode(
            id=alt_id,
            name=f"Alternative Recovery for: {failed_node.name}",
            description=f"Automated recovery step bypassing failure: {error_msg[:60]}",
            agent="TroubleshootingAgent",
            tool="diagnose_error",
            dependencies=failed_node.dependencies,
            status=TaskStatus.READY,
            inputs={"failing_node_id": failed_node_id, "error": error_msg},
        )
        graph.add_node(alt_node)

        # Update downstream nodes that depended on the failed node to depend on the alt node
        for n in graph.nodes.values():
            if failed_node_id in n.dependencies:
                n.dependencies = [alt_id if dep == failed_node_id else dep for dep in n.dependencies]

        failed_node.status = TaskStatus.SKIPPED
        return True

    @staticmethod
    def replan_on_user_modification(
        graph: TaskGraph,
        param_updates: Dict[str, Any],
        target_domain: Optional[str] = None,
    ) -> int:
        """Update parameter inputs of downstream pending/ready nodes without restarting."""
        modified_count = 0
        for node in graph.nodes.values():
            # Only update nodes that haven't executed yet
            if node.status in (TaskStatus.PENDING, TaskStatus.READY, TaskStatus.BLOCKED):
                if target_domain is None or target_domain.lower() in node.agent.lower() or target_domain.lower() in node.name.lower():
                    node.inputs.update(param_updates)
                    modified_count += 1
        return modified_count
