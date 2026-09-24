"""
JARVIS Phase 11: Context & Token Budget Managers, Cost Tracker & Semantic Compressor
Prevents token waste, prioritizes context streams, compacts logs, and enforces budgets.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from .models import TokenUsageRecord

logger = logging.getLogger("jarvis.ai.budget")


class ContextBudgetManager:
    """Allocates context window budget according to strict priority tiers."""

    def __init__(self, max_context_tokens: int = 8192):
        self.max_context_tokens = max_context_tokens

    def assemble_context(
        self,
        safety_system_prompt: str,
        current_task_prompt: str,
        source_files: Optional[Dict[str, str]] = None,
        project_memory: Optional[List[str]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        Assembles context within the token budget.
        Priority:
        1. Safety / System
        2. Current Task
        3. Source Files
        4. Relevant Memory
        5. Conversation History
        """
        parts = []

        # 1. Safety / System (Non-negotiable)
        parts.append(f"### SYSTEM RULES\n{safety_system_prompt.strip()}")

        # 2. Current Task (Critical)
        parts.append(f"### CURRENT TASK\n{current_task_prompt.strip()}")

        # 3. Source files
        if source_files:
            file_chunks = []
            for path, content in source_files.items():
                file_chunks.append(f"--- FILE: {path} ---\n{content.strip()}")
            parts.append("### SOURCE CODE CONTEXT\n" + "\n".join(file_chunks))

        # 4. Project memory
        if project_memory:
            mem_text = "\n".join(f"- {m}" for m in project_memory)
            parts.append(f"### RELEVANT PROJECT MEMORY\n{mem_text}")

        # 5. Conversation history (compacted)
        if conversation_history:
            recent_turns = conversation_history[-4:]
            hist_str = "\n".join(f"{t['role'].upper()}: {t['content']}" for t in recent_turns)
            parts.append(f"### RECENT CONVERSATION\n{hist_str}")

        return "\n\n".join(parts)


class SemanticContextCompressor:
    """Compacts logs and large files, extracting error lines and preserving key constraints."""

    @staticmethod
    def compress_log_output(log_text: str, max_lines: int = 50) -> str:
        """Extracts errors, warnings, stack traces, and exit codes from massive terminal output."""
        lines = log_text.splitlines()
        if len(lines) <= max_lines:
            return log_text

        extracted = []
        error_keywords = ("error", "failed", "exception", "traceback", "critical", "warn", "assert")

        for idx, line in enumerate(lines):
            low = line.lower()
            if any(k in low for k in error_keywords):
                # Include surrounding line context if available
                start = max(0, idx - 1)
                end = min(len(lines), idx + 2)
                for i in range(start, end):
                    if lines[i] not in extracted:
                        extracted.append(lines[i])

        if not extracted:
            # Fallback to head + tail
            return "\n".join(lines[:15] + ["\n... [output truncated for brevity] ...\n"] + lines[-15:])

        return "\n".join(extracted[:max_lines])


class TokenBudgetManager:
    """Tracks token consumption and enforces limits."""

    def __init__(self, daily_token_cap: int = 1000000):
        self.daily_token_cap = daily_token_cap
        self.records: List[TokenUsageRecord] = []

    def record_usage(
        self,
        task_id: str,
        provider: str,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        cost: float = 0.0,
    ) -> TokenUsageRecord:
        record = TokenUsageRecord(
            timestamp=time.time(),
            task_id=task_id,
            provider=provider,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=cost,
        )
        self.records.append(record)
        return record

    def get_today_tokens(self) -> int:
        now = time.time()
        today_start = now - (now % 86400)
        return sum(r.input_tokens + r.output_tokens for r in self.records if r.timestamp >= today_start)

    def is_daily_cap_exceeded(self) -> bool:
        return self.get_today_tokens() >= self.daily_token_cap


class CostManager:
    """Tracks estimated spending and enforces budget caps."""

    def __init__(self, daily_cost_cap_usd: float = 5.0):
        self.daily_cost_cap_usd = daily_cost_cap_usd
        self._total_spent_today: float = 0.0

    def add_cost(self, cost_usd: float):
        self._total_spent_today += cost_usd

    def get_spent_today(self) -> float:
        return round(self._total_spent_today, 4)

    def is_cost_cap_reached(self) -> bool:
        return self._total_spent_today >= self.daily_cost_cap_usd


class TokenWasteAnalyzer:
    """Detects repeated prompt blocks and unused context."""

    @staticmethod
    def analyze_prompt_waste(prompt: str) -> Dict[str, Any]:
        lines = [line.strip() for line in prompt.splitlines() if line.strip()]
        unique_lines = set(lines)
        waste_ratio = 1.0 - (len(unique_lines) / max(1, len(lines)))
        return {
            "total_lines": len(lines),
            "unique_lines": len(unique_lines),
            "duplicate_waste_ratio": round(waste_ratio, 3),
            "has_waste": waste_ratio > 0.25,
        }
