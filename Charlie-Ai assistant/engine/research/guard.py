"""engine/research/guard.py — Prompt Injection & Untrusted External Web Content Defense."""

from __future__ import annotations

import re
from typing import Tuple

# Patterns commonly used in prompt injection, system jailbreaks, or command injection
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)", re.I),
    re.compile(r"system\s*:\s*you\s+are\s+now", re.I),
    re.compile(r"you\s+are\s+now\s+in\s+(developer|god|unrestricted|dan)\s+mode", re.I),
    re.compile(r"execute\s+(powershell|cmd|bash|shell|terminal|python)\s*:", re.I),
    re.compile(r"run\s+command\s*:\s*rmdir|del|format|curl|wget", re.I),
    re.compile(r"bypass\s+(safety|permission|sandbox|guard)", re.I),
    re.compile(r"send\s+(api\s*key|password|token|secret|credentials)", re.I),
    re.compile(r"<system>.*?</system>", re.I | re.S),
    re.compile(r"\[instruction\].*?\[/instruction\]", re.I | re.S),
]


class UntrustedContentGuard:
    """Sanitizes external web content and enforces boundary between data and instructions."""

    @staticmethod
    def inspect_and_sanitize(raw_text: str, source_label: str = "webpage") -> Tuple[str, bool, str]:
        """Inspects text for injection attempts and returns (sanitized_text, is_suspicious, reason)."""
        if not raw_text:
            return "", False, ""

        detected_reasons = []
        for pat in INJECTION_PATTERNS:
            match = pat.search(raw_text)
            if match:
                detected_reasons.append(f"Detected injection directive: '{match.group(0)[:60]}'")

        is_suspicious = len(detected_reasons) > 0

        # Neutralize directives by neutralizing command-like framing and wrapping text in data demarcation
        sanitized = raw_text
        for pat in INJECTION_PATTERNS:
            sanitized = pat.sub("[REDACTED_UNTRUSTED_INSTRUCTION]", sanitized)

        # Wrap in unambiguous data enclosure
        guarded_text = f"[UNTRUSTED_EXTERNAL_DATA source={source_label}]\n{sanitized}\n[/UNTRUSTED_EXTERNAL_DATA]"
        reason = "; ".join(detected_reasons) if detected_reasons else "Clean data payload"

        return guarded_text, is_suspicious, reason

    @staticmethod
    def is_safe_for_synthesis(text: str) -> bool:
        """Quick safety check before passing text to synthesis or tool arguments."""
        if not text:
            return True
        for pat in INJECTION_PATTERNS:
            if pat.search(text):
                return False
        return True
