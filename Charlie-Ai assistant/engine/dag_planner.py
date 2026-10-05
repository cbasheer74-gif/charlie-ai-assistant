"""engine/dag_planner.py — Directed Acyclic Graph (DAG) Parallel Execution Planner.

Decomposes complex workflows into topological layers, executes independent
tool steps concurrently, passes intermediate outputs, and enforces safety bounds.
"""

from __future__ import annotations

import concurrent.futures
import logging
import time
from collections import defaultdict, deque
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("charlie.dag_planner")


class DAGNode:
    """A discrete task node in an execution DAG."""

    def __init__(
        self,
        node_id: str,
        name: str,
        action: Callable[..., Any],
        depends_on: Optional[List[str]] = None,
    ):
        self.node_id = node_id
        self.name = name
        self.action = action
        self.depends_on: Set[str] = set(depends_on or [])
        self.status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, SKIPPED
        self.result: Any = None
        self.error: Optional[str] = None
        self.duration: float = 0.0

    def __repr__(self) -> str:
        return f"<DAGNode {self.node_id}: {self.name} ({self.status})>"


class DAGPlanner:
    """Manages DAG dependency resolution and parallel stage execution."""

    def __init__(self, plan_id: str = "default_dag"):
        self.plan_id = plan_id
        self.nodes: Dict[str, DAGNode] = {}

    def add_node(
        self,
        node_id: str,
        name: str,
        action: Callable[..., Any],
        depends_on: Optional[List[str]] = None,
    ) -> DAGNode:
        if node_id in self.nodes:
            raise ValueError(f"Node '{node_id}' already exists in DAG")
        node = DAGNode(node_id, name, action, depends_on)
        self.nodes[node_id] = node
        return node

    def compute_layers(self) -> List[List[DAGNode]]:
        """Compute topological parallel stages using Kahn's algorithm."""
        in_degree: Dict[str, int] = {k: len(v.depends_on) for k, v in self.nodes.items()}
        dependents: Dict[str, List[str]] = defaultdict(list)
        for nid, node in self.nodes.items():
            for dep in node.depends_on:
                if dep not in self.nodes:
                    raise ValueError(f"Node '{nid}' references non-existent dependency '{dep}'")
                dependents[dep].append(nid)

        current_layer = [self.nodes[k] for k, deg in in_degree.items() if deg == 0]
        layers: List[List[DAGNode]] = []
        processed_count = 0

        while current_layer:
            layers.append(current_layer)
            processed_count += len(current_layer)
            next_layer = []
            for node in current_layer:
                for dep_id in dependents[node.node_id]:
                    in_degree[dep_id] -= 1
                    if in_degree[dep_id] == 0:
                        next_layer.append(self.nodes[dep_id])
            current_layer = next_layer

        if processed_count != len(self.nodes):
            raise ValueError("Cycle detected in DAG execution dependencies")

        return layers

    def execute(self, max_workers: int = 4) -> Dict[str, Any]:
        """Execute the DAG layer-by-layer, running all nodes within a layer in parallel."""
        layers = self.compute_layers()
        results: Dict[str, Any] = {}
        total_start = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            for layer_idx, layer in enumerate(layers):
                future_to_node = {}
                for node in layer:
                    # Verify dependencies completed successfully
                    dep_failed = any(
                        self.nodes[d].status != "COMPLETED" for d in node.depends_on
                    )
                    if dep_failed:
                        node.status = "SKIPPED"
                        node.error = "Upstream dependency failed or skipped"
                        continue

                    node.status = "RUNNING"
                    # Pass results dictionary to action callable
                    fut = executor.submit(self._run_node, node, results)
                    future_to_node[fut] = node

                # Wait for all nodes in current layer before progressing
                for fut in concurrent.futures.as_completed(future_to_node):
                    node = future_to_node[fut]
                    try:
                        res = fut.result()
                        node.result = res
                        node.status = "COMPLETED"
                        results[node.node_id] = res
                    except Exception as exc:
                        node.status = "FAILED"
                        node.error = str(exc)
                        logger.error(f"[DAGPlanner] Node '{node.node_id}' failed: {exc}")

        total_duration = time.time() - total_start
        succeeded = sum(1 for n in self.nodes.values() if n.status == "COMPLETED")
        failed = sum(1 for n in self.nodes.values() if n.status == "FAILED")
        skipped = sum(1 for n in self.nodes.values() if n.status == "SKIPPED")

        return {
            "plan_id": self.plan_id,
            "total_nodes": len(self.nodes),
            "layers_executed": len(layers),
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
            "duration_s": round(total_duration, 4),
            "results": results,
        }

    @staticmethod
    def _run_node(node: DAGNode, accumulated_results: Dict[str, Any]) -> Any:
        start = time.time()
        try:
            # Action can accept results or take 0 arguments
            import inspect
            sig = inspect.signature(node.action)
            if len(sig.parameters) > 0:
                res = node.action(accumulated_results)
            else:
                res = node.action()
            node.duration = time.time() - start
            return res
        except Exception:
            node.duration = time.time() - start
            raise
