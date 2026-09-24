"""engine/security/trust_guard.py — Zero-Trust Input Classification and Prompt Injection Defense."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from engine.security.models import InstructionOrigin


class PromptInjectionDefense:
    """Detects, sanitizes, and neutralizes prompt injection and system override attempts from external content."""

    INJECTION_PATTERNS = [
        re.compile(r"(?i)\b(ignore|disregard|forget)\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)\b"),
        re.compile(r"(?i)\b(system\s+prompt|reveal\s+(api\s+key|credentials|secret|token)|dump\s+memory)\b"),
        re.compile(r"(?i)\b(upload|send|transmit|exfiltrate)\s+.*\s+(to\s+https?:\/\/|to\s+attacker|to\s+external)\b"),
        re.compile(r"(?i)\b(run\s+powershell|execute\s+command|run\s+shell|del\s+\/s|rm\s+-rf)\b"),
        re.compile(r"(?i)\b(you\s+are\s+now|new\s+system\s+instruction|developer\s+mode\s+enabled)\b"),
    ]

    @classmethod
    def scan_content(cls, content: str) -> Tuple[bool, List[str]]:
        """Scans content for malicious prompt injection markers."""
        if not content:
            return False, []

        matches: List[str] = []
        for pat in cls.INJECTION_PATTERNS:
            found = pat.findall(content)
            if found:
                matches.append(pat.pattern)

        return len(matches) > 0, matches

    @classmethod
    def sanitize_untrusted_data(cls, raw_content: str, origin: InstructionOrigin) -> str:
        """Wraps untrusted content (web/email/docs) in inert data envelopes; neutralizes override commands."""
        if origin in (InstructionOrigin.USER, InstructionOrigin.SYSTEM, InstructionOrigin.TRUSTED_INTERNAL):
            return raw_content

        # Neutralize override phrases
        sanitized = raw_content
        for pat in cls.INJECTION_PATTERNS:
            sanitized = pat.sub("[SECURITY_STRIPPED: UNTRUSTED_EXTERNAL_DIRECTIVE]", sanitized)

        return f"<UNTRUSTED_DATA_ENVELOPE origin='{origin.value}'>\n{sanitized}\n</UNTRUSTED_DATA_ENVELOPE>"


class InputTrustClassifier:
    """Enforces origin tagging and ensures external data cannot authorize high-impact actions (Section 25 & 26)."""

    UNTRUSTED_ORIGINS = {
        InstructionOrigin.WEB,
        InstructionOrigin.EMAIL,
        InstructionOrigin.DOCUMENT,
        InstructionOrigin.FILE,
        InstructionOrigin.PLUGIN,
        InstructionOrigin.IMPORTED_SKILL,
    }

    @classmethod
    def is_untrusted(cls, origin: InstructionOrigin) -> bool:
        return origin in cls.UNTRUSTED_ORIGINS

    @classmethod
    def can_authorize_action(cls, origin: InstructionOrigin, action_name: str) -> bool:
        """Only USER or SYSTEM can authorize external sends, uploads, or command execution."""
        if cls.is_untrusted(origin):
            high_impact_actions = ("send_email", "upload_file", "execute_command", "delete_file", "install_package")
            if any(act in action_name.lower() for act in high_impact_actions):
                return False
        return True
