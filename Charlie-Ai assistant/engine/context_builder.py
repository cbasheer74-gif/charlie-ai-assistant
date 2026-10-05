"""engine/context_builder.py — Dynamic Context Builder for CHARLIE.

Constructs context dynamically before dispatching complex requests to the LLM:
Active Project + Relevant Memories + Checkpoint State + Procedures + Computer State.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from engine.memory_manager import MemoryManager


class ContextBuilder:
    """Assembles rich, relevant, and deduplicated context for agent execution with TTL caching."""

    def __init__(self, memory_manager: MemoryManager, cache_ttl_sec: float = 45.0):
        self.memory = memory_manager
        self.cache_ttl = cache_ttl_sec
        self._cache: Dict[str, tuple[float, str]] = {}

    def invalidate_cache(self) -> None:
        """Clear cached context assemblies."""
        self._cache.clear()

    def build_context(
        self,
        user_request: str,
        active_project: Optional[str] = None,
        available_tools: Optional[List[str]] = None,
    ) -> str:
        """Assemble structured context for the current turn with fast caching."""
        cache_key = f"{user_request.strip()}::{active_project or ''}"
        now = time.monotonic()

        cached = self._cache.get(cache_key)
        if cached is not None:
            timestamp, content = cached
            if now - timestamp < self.cache_ttl:
                return content

        parts: List[str] = []

        # 1. Project Context
        if active_project:
            p_ctx = self.memory.get_project_context(active_project)
            if p_ctx and p_ctx.get("facts"):
                lines = [f"[ACTIVE PROJECT: {active_project.upper()}]"]
                for cat, kvs in p_ctx["facts"].items():
                    for k, v in kvs.items():
                        lines.append(f"- {cat}.{k}: {v}")
                parts.append("\n".join(lines))

        # 2. Semantic Memory Retrieval (Targeted, max 4 items to keep fast)
        recalled = self.memory.search(user_request, project_name=active_project, limit=4)
        if recalled:
            lines = ["[RELEVANT MEMORY]"]
            for item in recalled:
                lines.append(f"- ({item['category']}) {item['content']}")
            parts.append("\n".join(lines))

        # 3. Recent Task Checkpoint (if any active/recent)
        recent_task = self.memory.get_recent_task_context(project_name=active_project)
        if recent_task and recent_task.get("status") in ("RUNNING", "WAITING_USER"):
            lines = [
                "[IN-PROGRESS TASK CHECKPOINT]",
                f"Task: {recent_task.get('task_name', '')}",
                f"Goal: {recent_task.get('goal', '')}",
                f"Status: {recent_task.get('status', '')}",
                f"Last Checkpoint: {recent_task.get('last_checkpoint', '')}",
                f"Next Action: {recent_task.get('next_action', '')}",
            ]
            parts.append("\n".join(lines))

        # 4. Relevant Procedural Memory
        proc = self.memory.get_procedure(user_request)
        if proc:
            steps_str = " -> ".join(proc.get("steps", []))
            parts.append(f"[PROVEN PROCEDURE: {proc.get('name')}]\nWorkflow: {steps_str}")

        # 5. Error Memory Check
        err = self.memory.find_error_solution(user_request)
        if err and err.get("successful_fix"):
            parts.append(f"[KNOWN ERROR SOLUTION]\nIssue: {err.get('error_signature')}\nFix: {err.get('successful_fix')}")

        # 6. RAG Document Knowledge Base — late-bind: query the assembled context
        # so retrieval matches the final LLM input, not just the raw user_request.
        try:
            from engine.rag import get_rag
            _rag_query_base = "\n\n".join(parts) if parts else user_request
            rag_context = get_rag().late_bind_search_context(
                _rag_query_base, top_k=2, max_chars=1800
            )
            if rag_context:
                parts.append(rag_context)
        except Exception:
            pass

        assembled = "\n\n".join(parts)

        # LRU eviction guard
        if len(self._cache) > 64:
            self._cache.pop(next(iter(self._cache)))
        self._cache[cache_key] = (now, assembled)

        return assembled
