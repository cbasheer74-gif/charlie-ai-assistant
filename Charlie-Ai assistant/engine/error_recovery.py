"""engine/error_recovery.py — Error Recovery Engine for JARVIS.

Captures tool and execution failures, consults ErrorMemory for known fixes,
and enforces the 2-strike policy (stops repeating identical actions after 2 failures).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from engine.memory_manager import MemoryManager


class ErrorRecoveryEngine:
    """Manages failure recovery, error memory lookups, and strategy shifts."""

    def __init__(self, memory_manager: MemoryManager):
        self.memory = memory_manager
        # Tracking in-flight consecutive failures: (task_or_tool_key) -> count
        self._consecutive_failures: Dict[str, int] = {}
        self._last_signatures: Dict[str, str] = {}

    def extract_signature(self, error_message: str) -> str:
        """Extract a clean, reusable error signature from an exception message or traceback."""
        clean = str(error_message).strip()
        # Look for explicit Exception class names: e.g. FileNotFoundError: [Errno 2] ...
        m = re.search(r"([A-Za-z_]+Error|Exception|OperationalError|TimeoutError):\s*([^\n\r]+)", clean)
        if m:
            return f"{m.group(1)}: {m.group(2)[:80]}".strip()
        return clean[:100]

    def record_failure(
        self,
        key: str,
        error_msg: str,
        application: str = "",
        project_name: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Record a failure for an action or tool.

        Returns:
            (must_shift_strategy: bool, guidance_message: str, known_solution: dict | None)
        """
        sig = self.extract_signature(error_msg)
        count = self._consecutive_failures.get(key, 0) + 1
        self._consecutive_failures[key] = count
        self._last_signatures[key] = sig

        # Search ErrorMemory
        known = self.memory.find_error_solution(sig)

        if count >= 2:
            guidance = (
                f"2-STRIKE ALERT: Action '{key}' failed {count} times with '{sig}'. "
                f"CRITICAL: Do NOT retry the identical action. Collect new evidence, alter your hypothesis, or pick another tool."
            )
            return True, guidance, known

        guidance = f"Attempt 1 failed with '{sig}'."
        if known and known.get("successful_fix"):
            guidance += f" Known working solution found: {known['successful_fix']}"
        return False, guidance, known

    def record_success(
        self,
        key: str,
        solution_summary: str = "",
        application: str = "",
        project_name: Optional[str] = None,
    ) -> None:
        """Reset failure counter and store solution in error memory if preceded by failure."""
        had_failures = self._consecutive_failures.get(key, 0) > 0
        sig = self._last_signatures.get(key)
        self._consecutive_failures.pop(key, None)
        self._last_signatures.pop(key, None)

        if had_failures and sig and solution_summary:
            self.memory.store_error_solution(
                error_signature=sig,
                root_cause="Resolved during task execution",
                successful_fix=solution_summary,
                application=application,
                project_name=project_name,
                verification="Action succeeded after fix",
            )

    def find_known_solution(self, signature: str, application: str = "") -> Optional[str]:
        """Query memory for existing successful fix for this error signature."""
        known = self.memory.find_error_solution(signature)
        if known and known.get("successful_fix"):
            return known["successful_fix"]
        return None

