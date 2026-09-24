"""engine/permissions.py — Permission Engine and Command Safety Filter.

Classifies action risks into READ_ONLY, SAFE_WRITE, SYSTEM_CHANGE, HIGH_IMPACT.
Enforces confirmation gates for destructive terminal commands and permanent file deletions.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Callable, Dict, Optional, Tuple

from core import confirm


class RiskLevel(str, Enum):
    READ_ONLY = "READ_ONLY"
    SAFE_WRITE = "SAFE_WRITE"
    SYSTEM_CHANGE = "SYSTEM_CHANGE"
    HIGH_IMPACT = "HIGH_IMPACT"


# Dangerous command patterns that must be blocked or gated
_DANGEROUS_PATTERNS = [
    (re.compile(r"(?i)\brm\s+.*-[a-zA-Z]*r[a-zA-Z]*\b"), "Recursive forceful deletion"),
    (re.compile(r"(?i)\bdel\s+(/[a-zA-Z]*s|-[a-zA-Z]*s)\b"), "Windows recursive file deletion"),
    (re.compile(r"(?i)\b(rmdir|rd)\b"), "Windows directory deletion"),
    (re.compile(r"(?i)\bRemove-Item\s+.*-(Recurse|Force)\b"), "PowerShell recursive deletion"),
    (re.compile(r"(?i)\bformat\s+[a-zA-Z]:"), "Disk format attempt"),
    (re.compile(r"(?i)\bdiskpart\b"), "Disk partitioning tool"),
    (re.compile(r"(?i)\bgit\s+reset\s+--hard\b"), "Destructive hard git reset"),
    (re.compile(r"(?i)\bgit\s+clean\s+-[a-zA-Z]*f\b"), "Force git clean"),
    (re.compile(r"(?i)\bgit\s+push\s+.*--force\b"), "Git force push"),
    (re.compile(r"(?i)\breg\s+delete\b"), "Registry deletion"),
    (re.compile(r"(?i)\b(drop\s+database|drop\s+table|truncate\s+table)\b"), "SQL destructive statement"),
]


class PermissionManager:
    """Manages permissions and inspects commands before execution."""

    def __init__(self, ask_system_changes: bool = True):
        self.ask_system_changes = ask_system_changes

    def classify_command(self, command_line: str) -> Tuple[RiskLevel, str]:
        """Classify a shell/terminal command and detect destructive intent."""
        cmd = command_line.strip()
        for pattern, reason in _DANGEROUS_PATTERNS:
            if pattern.search(cmd):
                return RiskLevel.HIGH_IMPACT, f"Potentially destructive operation: {reason}"

        # System modifications
        low = cmd.lower()
        if any(w in low for w in ("install", "pip install", "npm install -g", "choco", "winget", "setx")):
            return RiskLevel.SYSTEM_CHANGE, "System software or environment modification"

        # Safe development write
        if any(w in low for w in ("git commit", "mkdir", "echo ", "touch ", "npm run")):
            return RiskLevel.SAFE_WRITE, "Routine development execution"

        # Routine inspection
        if any(re.search(rf"\b{re.escape(w.strip())}\b", low) for w in ("git status", "git diff", "git log", "dir", "ls", "type", "cat", "pwd", "cd")):
            return RiskLevel.READ_ONLY, "Inspection"

        return RiskLevel.SAFE_WRITE, "Standard command"

    def requires_confirmation(self, risk_level: RiskLevel) -> bool:
        """Determine if UI confirmation gate is mandatory."""
        if risk_level == RiskLevel.HIGH_IMPACT:
            return True
        if risk_level == RiskLevel.SYSTEM_CHANGE and self.ask_system_changes:
            return True
        return False

    def guard_action(
        self,
        name: str,
        risk_level: RiskLevel,
        action_fn: Callable[[], str],
        description: str,
    ) -> Tuple[bool, str]:
        """Execute action directly if safe, or submit to core.confirm for human authorization."""
        if not self.requires_confirmation(risk_level):
            try:
                res = action_fn()
                return True, res
            except Exception as e:
                return False, f"Execution failed: {e}"

        # Route through confirm.py
        msg = confirm.request(
            name,
            title=f"CONFIRM: {name.upper()}",
            detail=f"{description} (Risk: {risk_level.value})",
            run=action_fn,
        )
        return False, f"[CONFIRMATION_PENDING] {msg}"
