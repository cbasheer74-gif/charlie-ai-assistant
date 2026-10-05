"""core/secret_redactor.py — Centralized secret redaction engine for CHARLIE.

Redacts API keys, tokens, session keys, private keys, passwords, and authorization
headers across log boundaries, console output, diagnostics, and error reporting.
"""

from __future__ import annotations

import copy
import re
import traceback
from typing import Any, Mapping

# Secret field names commonly found in dictionaries / configuration
SECRET_KEYS = {
    "api_key",
    "apikey",
    "gemini_api_key",
    "groq_api_key",
    "secret",
    "client_secret",
    "password",
    "passwd",
    "token",
    "access_token",
    "refresh_token",
    "auth_token",
    "bearer_token",
    "session_key",
    "private_key",
    "credentials",
    "auth",
}

# Compiled regex patterns for string/log scrubbing
_PATTERNS = [
    # Google Gemini / Cloud API keys
    (re.compile(r"(?:AIza|AQ)[0-9A-Za-z\-_]{16,}", re.IGNORECASE), "[REDACTED_API_KEY]"),
    # Groq API keys
    (re.compile(r"gsk_[a-zA-Z0-9]{20,}", re.IGNORECASE), "[REDACTED_GROQ_KEY]"),
    # OpenAI & Anthropic API keys
    (re.compile(r"sk-(?:ant-)?[a-zA-Z0-9_\-]{20,}", re.IGNORECASE), "[REDACTED_API_KEY]"),
    # Generic Authorization: Bearer <token>
    (re.compile(r"(Authorization\s*:\s*Bearer\s+)[A-Za-z0-9\-\._~\+\/]+=*", re.IGNORECASE), r"\1[REDACTED_TOKEN]"),
    # Bearer <token>
    (re.compile(r"\bBearer\s+[A-Za-z0-9\-\._~\+\/]{20,}={0,2}", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
    # JWT format: eyJ...
    (re.compile(r"ey[A-Za-z0-9_-]{15,}\.ey[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_\-]+"), "[REDACTED_JWT]"),
    # Key-value secret assignments (e.g. password=..., api_key="...", "client_secret": "...")
    (
        re.compile(
            r"""(?i)(["']?(?:password|passwd|secret|client_secret|api_key|access_token|refresh_token|auth_token|session_key)["']?\s*[:=]\s*["']?)([^"'&\s\r\n]{4,})(["']?)""",
        ),
        r"\1[REDACTED]\3",
    ),
    # Database connection strings with credentials (postgres, mysql, mongodb, redis, etc.)
    (
        re.compile(r"((?:postgres|postgresql|mysql|mongodb|redis|amqp):\/\/[^:\s]+:)([^@\s]+)(@)", re.IGNORECASE),
        r"\1[REDACTED_PASSWORD]\3",
    ),
    # PEM Private Keys
    (
        re.compile(r"-----BEGIN[A-Z\s_-]+PRIVATE KEY-----[\s\S]*?-----END[A-Z\s_-]+PRIVATE KEY-----"),
        "[REDACTED_PRIVATE_KEY]",
    ),
    # Cookies
    (re.compile(r"(Cookie\s*:\s*)([^\r\n;]+)", re.IGNORECASE), r"\1[REDACTED_COOKIE]"),
]


def redact_text(text: str) -> str:
    """Scrub sensitive credentials from a text string."""
    if not text or not isinstance(text, str):
        return text or ""
    scrubbed = text
    for pattern, replacement in _PATTERNS:
        scrubbed = pattern.sub(replacement, scrubbed)
    return scrubbed


def is_sensitive_key(key: str) -> bool:
    """Return True if dictionary key denotes a secret."""
    k = str(key or "").lower().strip()
    return any(term in k for term in ("key", "secret", "token", "password", "passwd", "auth", "credential"))


def redact_mapping(data: Any, max_depth: int = 5) -> Any:
    """Recursively scrub sensitive keys and string values in mappings or lists.

    Returns a deep copy; does NOT mutate the original structure.
    """
    if max_depth <= 0:
        return data

    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            if is_sensitive_key(k) and isinstance(v, (str, bytes)):
                cleaned[k] = "[REDACTED]"
            elif isinstance(v, (dict, list)):
                cleaned[k] = redact_mapping(v, max_depth - 1)
            elif isinstance(v, str):
                cleaned[k] = redact_text(v)
            else:
                cleaned[k] = v
        return cleaned

    if isinstance(data, list):
        return [redact_mapping(item, max_depth - 1) for item in data]

    if isinstance(data, str):
        return redact_text(data)

    return data


def safe_exception(exc: BaseException | Exception, include_traceback: bool = True) -> str:
    """Extract and scrub an exception message and optional traceback."""
    if exc is None:
        return ""
    if include_traceback:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        return redact_text(tb)
    return redact_text(f"{type(exc).__name__}: {exc}")
