"""engine/security/command_safety.py — Shell Command Safety Engine, Pattern Detection, and PowerShell Protection."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from engine.security.models import RiskLevel


class CommandSafetyEngine:
    """Inspects shell commands before execution to block catastrophic commands and dangerous PowerShell scripts."""

    CRITICAL_DANGEROUS_PATTERNS = [
        # Disk format / partition
        (re.compile(r"(?i)\bformat\s+[a-zA-Z]:"), "Disk format attempt"),
        (re.compile(r"(?i)\bdiskpart\b"), "Disk partitioning tool"),
        (re.compile(r"(?i)\bcipher\s+\/w:"), "Secure drive wipe"),
        # Recursive Windows file / directory destruction
        (re.compile(r"(?i)\bdel\s+.*\/[sS]"), "Recursive file deletion"),
        (re.compile(r"(?i)\brmdir\s+.*\/[sS]"), "Recursive folder removal"),
        (re.compile(r"(?i)\bRemove-Item\b.*(-Recurse|-r)\b.*(-Force|-f)\b"), "PowerShell forced recursive deletion"),
        (re.compile(r"(?i)\brm\s+-[a-zA-Z]*r[a-zA-Z]*f"), "UNIX recursive force delete"),
        # Destructive registry / service removal
        (re.compile(r"(?i)\breg\s+delete\b"), "Registry deletion"),
        (re.compile(r"(?i)\bsc\s+delete\b"), "Windows service deletion"),
        # System shutdown / critical taskkill
        (re.compile(r"(?i)\bshutdown\s+(\/s|\/r|-s|-r)\b"), "System shutdown command"),
        (re.compile(r"(?i)\btaskkill\s+.*\/f\s+.*\/im\s+(csrss|explorer|winlogon|svchost|lsass)\.exe"), "Killing critical OS process"),
        # Git force destruction
        (re.compile(r"(?i)\bgit\s+reset\s+--hard\b"), "Git destructive hard reset"),
        (re.compile(r"(?i)\bgit\s+clean\s+-[a-zA-Z]*f[a-zA-Z]*d"), "Git clean force removal"),
        (re.compile(r"(?i)\bgit\s+push\s+.*--force\b"), "Git force push"),
        # Database DROP / TRUNCATE
        (re.compile(r"(?i)\b(drop\s+database|drop\s+table|truncate\s+table)\b"), "SQL destructive schema command"),
        # PowerShell download and execute (irm URL | iex)
        (re.compile(r"(?i)\b(irm|Invoke-RestMethod|curl|wget)\b.*\|\s*(iex|Invoke-Expression)\b"), "Unsafe download-and-execute pipeline"),
    ]

    SAFE_COMMAND_ALLOWLIST = [
        re.compile(r"^git\s+(status|diff|log|branch|checkout|pull|fetch)"),
        re.compile(r"^npm\s+(test|run\s+test|run\s+build|run\s+dev|--version)"),
        re.compile(r"^flutter\s+(doctor|devices|test|analyze|--version)"),
        re.compile(r"^python\s+(-m\s+unittest|-m\s+pytest|--version)"),
        re.compile(r"^(dir|ls|echo|type|cat|pwd|whoami)\b"),
    ]

    @classmethod
    def evaluate_command(cls, command_line: str) -> Tuple[RiskLevel, bool, str]:
        """Evaluates command string.

        Returns: (RiskLevel, is_blocked, reason)
        """
        cmd = command_line.strip()
        if not cmd:
            return RiskLevel.R0_READ_ONLY, False, "Empty command"

        # 1. Check against critical dangerous patterns
        for pattern, reason in cls.CRITICAL_DANGEROUS_PATTERNS:
            if pattern.search(cmd):
                return RiskLevel.R4_CRITICAL, True, f"Blocked dangerous command: {reason}"

        # 2. Check safe allowlist
        for allow_pat in cls.SAFE_COMMAND_ALLOWLIST:
            if allow_pat.search(cmd):
                return RiskLevel.R0_READ_ONLY, False, "Safe allowlisted command"

        # 3. Environment or software installation
        low = cmd.lower()
        if any(w in low for w in ("pip install", "npm install", "choco install", "winget install", "setx")):
            return RiskLevel.R2_REVERSIBLE_CHANGE, False, "Software or environment modification"

        # 4. Routine write commands
        if any(w in low for w in ("git commit", "mkdir", "touch", "npm run", "python ", "node ")):
            return RiskLevel.R1_SAFE_WRITE, False, "Routine local write"

        return RiskLevel.R1_SAFE_WRITE, False, "Standard execution"
