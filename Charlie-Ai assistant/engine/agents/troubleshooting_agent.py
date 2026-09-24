"""engine/agents/troubleshooting_agent.py — Diagnostics and Recovery Specialist.

Analyzes error logs, cross-references ErrorMemory, and formulates minimal undoable repairs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.agents.base import BaseAgent


class TroubleshootingAgent(BaseAgent):
    """Specialist agent for error diagnosis and root-cause resolution."""

    def can_handle(self, user_intent: str) -> bool:
        low = user_intent.lower()
        return any(w in low for w in ("error", "crash", "failed", "stack trace", "diagnose", "why did it fail", "fix bug"))

    def diagnose(self, error_message: str, application: str = "", project_name: Optional[str] = None) -> Dict[str, Any]:
        """Diagnose an error, search error memory, and determine fix strategy."""
        sig = self.recovery.extract_signature(error_message)
        must_shift, guidance, known = self.recovery.record_failure(
            key=sig,
            error_msg=error_message,
            application=application,
            project_name=project_name,
        )

        return {
            "signature": sig,
            "must_shift_strategy": must_shift,
            "guidance": guidance,
            "known_fix": known.get("successful_fix") if known else None,
            "root_cause": known.get("root_cause") if known else "Unverified",
        }
