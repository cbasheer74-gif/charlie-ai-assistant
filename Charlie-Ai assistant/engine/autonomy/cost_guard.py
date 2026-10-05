"""engine/autonomy/cost_guard.py — Token & Cost Budget Guard.

Tracks cumulative token usage and estimated API cost for a single autonomy
run. Raises CostLimitExceeded when either the token or USD ceiling is hit.

Design:
  - No external deps — uses simple character-based heuristic for token
    estimation (accurate to ±15% vs tiktoken, zero startup cost).
  - Thread-safe: all mutations go through a lock.
  - Pricing table is conservative (uses the *higher* tier for each model
    family so estimates never under-count).
  - The orchestrator checks is_exceeded() before every node dispatch
    and after every agent result, so the ceiling is enforced in <2 steps.

Usage:
    guard = CostGuard(max_tokens=50_000, max_cost_usd=0.25)
    guard.record(prompt_text, completion_text, model="gemini-1.5-flash")
    if guard.is_exceeded():
        raise guard.make_exception()
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# Conservative pricing table  (USD per 1 000 tokens)
# ---------------------------------------------------------------------------
_PRICING: Dict[str, Dict[str, float]] = {
    # Gemini
    "gemini-3.8-flash":     {"input": 0.00035,"output": 0.00105},
    "gemini-flash-latest":  {"input": 0.00035,"output": 0.00105},
    "gemini-1.5-pro":       {"input": 0.007,  "output": 0.021},
    "gemini-1.5-flash":     {"input": 0.00035,"output": 0.00105},
    "gemini-2.0-flash":     {"input": 0.00035,"output": 0.00105},
    "gemini-2.5-pro":       {"input": 0.007,  "output": 0.021},
    # OpenAI fallback
    "gpt-4o":               {"input": 0.005,  "output": 0.015},
    "gpt-4o-mini":          {"input": 0.00015,"output": 0.0006},
    "gpt-4-turbo":          {"input": 0.010,  "output": 0.030},
    # Claude
    "claude-3-5-sonnet":    {"input": 0.003,  "output": 0.015},
    "claude-3-haiku":       {"input": 0.00025,"output": 0.00125},
    # Default (conservative)
    "_default":             {"input": 0.005,  "output": 0.015},
}


def _resolve_pricing(model: str) -> Dict[str, float]:
    """Match model string to pricing entry (prefix match, case-insensitive)."""
    m = model.lower().strip()
    for key, prices in _PRICING.items():
        if key == "_default":
            continue
        if m.startswith(key) or key in m:
            return prices
    return _PRICING["_default"]


def _estimate_tokens(text: str) -> int:
    """Estimate token count from raw text.

    Heuristic: ~4 characters per token for English/code, ~2 for CJK/Arabic.
    Conservative: always round up.
    """
    if not text:
        return 0
    cjk_arabic = sum(
        1 for ch in text
        if ("\u4E00" <= ch <= "\u9FFF") or ("\u0600" <= ch <= "\u06FF")
        or ("\u0900" <= ch <= "\u097F") or ("\u3040" <= ch <= "\u30FF")
    )
    ratio = 2.5 if cjk_arabic > len(text) * 0.3 else 4.0
    return max(1, int(len(text) / ratio) + 1)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CostLimitExceeded(RuntimeError):
    """Raised when a token or USD ceiling is breached."""

    def __init__(self, reason: str, snapshot: "CostSnapshot"):
        super().__init__(reason)
        self.reason = reason
        self.snapshot = snapshot

    def user_message(self) -> str:
        s = self.snapshot
        parts = [self.reason]
        parts.append(
            f"Used {s.total_tokens:,} tokens "
            f"(${s.total_cost_usd:.4f} USD) across {s.call_count} calls."
        )
        if s.total_cost_usd > 0:
            parts.append("Task halted. Checkpoint saved — you can resume later.")
        return " | ".join(parts)


# ---------------------------------------------------------------------------
# Snapshot (immutable read view)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CostSnapshot:
    total_tokens: int
    input_tokens: int
    output_tokens: int
    total_cost_usd: float
    call_count: int
    max_tokens: int
    max_cost_usd: float

    @property
    def token_pct(self) -> float:
        return (self.total_tokens / self.max_tokens * 100) if self.max_tokens else 0.0

    @property
    def cost_pct(self) -> float:
        return (self.total_cost_usd / self.max_cost_usd * 100) if self.max_cost_usd else 0.0

    def __str__(self) -> str:
        return (
            f"Tokens {self.total_tokens:,}/{self.max_tokens:,} "
            f"({self.token_pct:.1f}%) | "
            f"Cost ${self.total_cost_usd:.4f}/${self.max_cost_usd:.2f} "
            f"({self.cost_pct:.1f}%)"
        )


# ---------------------------------------------------------------------------
# CostGuard
# ---------------------------------------------------------------------------

class CostGuard:
    """Thread-safe token + USD cost ceiling enforcer for one autonomy run.

    Args:
        max_tokens:   Hard stop when cumulative tokens exceed this value.
                      Default 100_000 (~$0.50 at flash pricing).
        max_cost_usd: Hard stop when cumulative cost exceeds this USD amount.
                      Default $0.50.
        warn_at_pct:  Log a warning when usage crosses this percentage of
                      either ceiling. Default 80.
    """

    def __init__(
        self,
        max_tokens: int = 100_000,
        max_cost_usd: float = 0.50,
        warn_at_pct: float = 80.0,
    ) -> None:
        self.max_tokens = max(1, max_tokens)
        self.max_cost_usd = max(0.0, max_cost_usd)
        self.warn_at_pct = warn_at_pct

        self._lock = threading.Lock()
        self._input_tokens = 0
        self._output_tokens = 0
        self._total_cost_usd = 0.0
        self._call_count = 0
        self._warning_fired = False
        self._exceeded_reason: Optional[str] = None

    # -- Recording ------------------------------------------------------------

    def record(
        self,
        prompt: str = "",
        completion: str = "",
        model: str = "gemini-1.5-flash",
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
    ) -> None:
        """Record one LLM call.

        Prefer passing explicit token counts when available (e.g. from the API
        response metadata). Falls back to heuristic estimation.
        """
        in_tok  = input_tokens  if input_tokens  is not None else _estimate_tokens(prompt)
        out_tok = output_tokens if output_tokens is not None else _estimate_tokens(completion)

        prices = _resolve_pricing(model)
        cost = (in_tok * prices["input"] + out_tok * prices["output"]) / 1000.0

        with self._lock:
            self._input_tokens  += in_tok
            self._output_tokens += out_tok
            self._total_cost_usd += cost
            self._call_count += 1
            self._check_limits()

    def record_tokens(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str = "gemini-1.5-flash",
    ) -> None:
        """Convenience: record when you already have token counts."""
        self.record(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    # -- Querying -------------------------------------------------------------

    @property
    def total_tokens(self) -> int:
        with self._lock:
            return self._input_tokens + self._output_tokens

    @property
    def total_cost_usd(self) -> float:
        with self._lock:
            return self._total_cost_usd

    def snapshot(self) -> CostSnapshot:
        with self._lock:
            return CostSnapshot(
                total_tokens=self._input_tokens + self._output_tokens,
                input_tokens=self._input_tokens,
                output_tokens=self._output_tokens,
                total_cost_usd=self._total_cost_usd,
                call_count=self._call_count,
                max_tokens=self.max_tokens,
                max_cost_usd=self.max_cost_usd,
            )

    def is_exceeded(self) -> bool:
        with self._lock:
            return self._exceeded_reason is not None

    def exceeded_reason(self) -> Optional[str]:
        with self._lock:
            return self._exceeded_reason

    def make_exception(self) -> CostLimitExceeded:
        snap = self.snapshot()
        reason = self.exceeded_reason() or "Cost/token limit exceeded"
        return CostLimitExceeded(reason, snap)

    def reset(self) -> None:
        """Reset counters (e.g. for a new sub-task within the same orchestrator)."""
        with self._lock:
            self._input_tokens = 0
            self._output_tokens = 0
            self._total_cost_usd = 0.0
            self._call_count = 0
            self._warning_fired = False
            self._exceeded_reason = None

    # -- Internal -------------------------------------------------------------

    def _check_limits(self) -> None:
        """Must be called with self._lock held."""
        total = self._input_tokens + self._output_tokens

        # Warning threshold (fires once)
        if not self._warning_fired and self.warn_at_pct > 0:
            tok_pct  = total / self.max_tokens * 100 if self.max_tokens else 0
            cost_pct = self._total_cost_usd / self.max_cost_usd * 100 if self.max_cost_usd else 0
            if tok_pct >= self.warn_at_pct or cost_pct >= self.warn_at_pct:
                import logging
                logging.getLogger("charlie.cost_guard").warning(
                    "CostGuard: %.0f%% of budget used — tokens %s, cost $%.4f",
                    max(tok_pct, cost_pct), total, self._total_cost_usd,
                )
                self._warning_fired = True

        # Hard ceilings
        if self.max_tokens and total >= self.max_tokens:
            self._exceeded_reason = (
                f"Token ceiling hit: {total:,} >= {self.max_tokens:,} tokens."
            )
        elif self.max_cost_usd and self._total_cost_usd >= self.max_cost_usd:
            self._exceeded_reason = (
                f"Cost ceiling hit: ${self._total_cost_usd:.4f} >= ${self.max_cost_usd:.2f}."
            )
