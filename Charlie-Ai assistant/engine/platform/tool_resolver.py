"""
JARVIS Phase 12: Tool Resolver & Dynamic Tool Loader
Resolves tools semantically based on user goals and injects only relevant tool schemas into prompts.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .models import ToolContract

logger = logging.getLogger("jarvis.platform.tool_resolver")


class ToolResolver:
    """Discovers and resolves tools by semantic intent, avoiding giant schema prompt bloat."""

    def __init__(self):
        # tool_name -> ToolContract
        self._tools: Dict[str, ToolContract] = {}

    def register_tool(self, tool: ToolContract):
        self._tools[tool.name] = tool

    def resolve_tools_for_task(self, task_description: str, max_tools: int = 5) -> List[ToolContract]:
        """
        Filters the full registry down to only the relevant tools for the current task.
        Example: "clean excel file" -> only spreadsheet tools, NOT github or slack.
        """
        clean = task_description.lower()
        scored: List[tuple[int, ToolContract]] = []

        for name, tool in self._tools.items():
            score = 0
            desc = tool.description.lower()
            tool_words = set(name.replace(".", " ").replace("_", " ").lower().split() + desc.split())

            # Domain keyword matching
            for token in clean.split():
                if len(token) >= 3 and token in tool_words:
                    score += 3

            clean_words = set(clean.split())
            # General category affinity
            if any(k in clean_words for k in ("excel", "sheet", "csv", "spreadsheet")) and "excel" in name:
                score += 10
            if any(k in clean_words for k in ("issue", "issues", "pr", "prs", "repo", "github")) and "github" in name:
                score += 10
            if any(k in clean_words for k in ("slack", "channel", "message")) and "slack" in name:
                score += 10
            if any(k in clean_words for k in ("database", "sql", "query", "table", "db")) and "db" in name:
                score += 10

            if score > 0:
                scored.append((score, tool))

        # Sort descending by score
        scored.sort(key=lambda x: x[0], reverse=True)
        if scored:
            top_score = scored[0][0]
            # Only keep tools within 50% of the top score to avoid irrelevant leakage
            scored = [item for item in scored if item[0] >= top_score * 0.5]
        return [t for _, t in scored[:max_tools]]

    def list_all_tools(self) -> List[ToolContract]:
        return list(self._tools.values())
