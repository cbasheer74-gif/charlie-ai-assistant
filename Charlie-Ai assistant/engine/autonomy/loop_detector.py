"""engine/autonomy/loop_detector.py — Repetition & Action Loop Detection.

Detects repetitive tool failures, cyclical state oscillation, and infinite retry patterns
in autonomous multi-step execution.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from typing import Any, Dict, List, Optional, Tuple


class LoopDetector:
    """Detects runaway loops and cyclic patterns across agent actions."""

    def __init__(self, max_identical_threshold: int = 2, window_size: int = 12):
        self.max_identical_threshold = max_identical_threshold
        self.window_size = window_size
        self._action_history: deque[Tuple[str, str, str]] = deque(maxlen=window_size)
        # tuple: (tool_name, args_hash, result_hash)
        self._consecutive_failures: Dict[str, int] = {}

    def _hash_obj(self, obj: Any) -> str:
        try:
            s = json.dumps(obj, sort_keys=True, default=str)
        except Exception:
            s = str(obj)
        return hashlib.md5(s.encode("utf-8", errors="ignore")).hexdigest()[:12]

    def record_step(self, tool: str, args: Any, result: Any, success: bool = True):
        args_hash = self._hash_obj(args)
        res_hash = self._hash_obj(result)
        self._action_history.append((tool, args_hash, res_hash))

        if not success:
            key = f"{tool}:{args_hash}"
            self._consecutive_failures[key] = self._consecutive_failures.get(key, 0) + 1
        else:
            key = f"{tool}:{args_hash}"
            self._consecutive_failures.pop(key, None)

    def is_looping(self) -> Tuple[bool, str]:
        """Check if current execution history shows looping symptoms."""
        # 1. Check repeated identical tool + arguments failing consecutively
        for key, count in self._consecutive_failures.items():
            if count >= self.max_identical_threshold:
                tool_name = key.split(":")[0]
                return True, f"Repetitive tool failure detected: '{tool_name}' failed {count} times with identical inputs."

        # 2. Check identical action cycle in recent window (e.g. A -> A -> A)
        if len(self._action_history) >= self.max_identical_threshold:
            tail = list(self._action_history)[-self.max_identical_threshold:]
            first_tool, first_args, _ = tail[0]
            if all(t == first_tool and a == first_args for t, a, _ in tail):
                return True, f"Action loop detected: tool '{first_tool}' executed {self.max_identical_threshold} times without change in arguments."

        # 3. Check oscillation (A -> B -> A -> B)
        if len(self._action_history) >= 4:
            h = list(self._action_history)
            if h[-1] == h[-3] and h[-2] == h[-4] and h[-1] != h[-2]:
                return True, f"Oscillation detected between actions '{h[-1][0]}' and '{h[-2][0]}'."

        return False, ""

    def reset(self):
        self._action_history.clear()
        self._consecutive_failures.clear()
