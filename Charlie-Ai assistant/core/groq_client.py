"""Groq LLM client for CHARLIE.

Provides text/chat completion via Groq's high-speed LPU inference engine.
Acts as an optional provider or fallback for text chat without affecting
Gemini Live voice.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Iterator, List, Optional

from memory.config_manager import get_groq_key, is_groq_configured

logger = logging.getLogger("charlie.core.groq")

# Model configuration constants
GROQ_PRIMARY_MODEL: str = "openai/gpt-oss-120b"
GROQ_FAST_MODEL: str = "openai/gpt-oss-20b"
DEFAULT_MODEL: str = GROQ_PRIMARY_MODEL
DEFAULT_TIMEOUT_SECONDS: float = 30.0

# Deprecated model normalization mapping
DEPRECATED_MODELS: Dict[str, str] = {
    "llama-3.3-70b-versatile": GROQ_PRIMARY_MODEL,
    "llama-3.1-8b-instant": GROQ_FAST_MODEL,
    "llama3-70b-8192": GROQ_PRIMARY_MODEL,
    "llama3-8b-8192": GROQ_FAST_MODEL,
}

# Optional Groq SDK import with graceful fallback
try:
    from groq import (
        Groq,
        GroqError,
        AuthenticationError,
        RateLimitError,
        APITimeoutError,
        APIConnectionError,
        BadRequestError,
        NotFoundError,
    )
except ImportError:
    Groq = None  # type: ignore
    GroqError = Exception  # type: ignore
    AuthenticationError = Exception  # type: ignore
    RateLimitError = Exception  # type: ignore
    APITimeoutError = Exception  # type: ignore
    APIConnectionError = Exception  # type: ignore
    BadRequestError = Exception  # type: ignore
    NotFoundError = Exception  # type: ignore


def is_configured() -> bool:
    """Check if Groq SDK is installed and an API key is configured."""
    return Groq is not None and is_groq_configured()


def resolve_model(model_name: Optional[str]) -> str:
    """Normalize and validate Groq model string, replacing deprecated models."""
    if not model_name:
        return GROQ_PRIMARY_MODEL

    normalized = model_name.strip()
    if normalized in ("groq_primary", "primary", "cloud_strong_reasoning"):
        return GROQ_PRIMARY_MODEL
    if normalized in ("groq_fast", "fast", "cloud_fast_cheap"):
        return GROQ_FAST_MODEL

    if normalized in DEPRECATED_MODELS:
        replacement = DEPRECATED_MODELS[normalized]
        logger.warning(
            "[Groq] Requested model '%s' is deprecated; remapped to '%s'",
            normalized,
            replacement,
        )
        return replacement

    return normalized


def get_groq_client(
    key: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Optional[Any]:
    """Safely obtain an initialized Groq client instance.

    Returns None if the SDK is missing or no key is configured.
    Never exposes or logs the API key.
    """
    if Groq is None:
        logger.debug("[Groq] 'groq' SDK is not installed.")
        return None

    resolved_key = (key or get_groq_key() or "").strip()
    if not resolved_key or len(resolved_key) < 10:
        logger.debug("[Groq] No valid GROQ_API_KEY found.")
        return None

    try:
        return Groq(api_key=resolved_key, timeout=timeout)
    except Exception as e:
        logger.warning("[Groq] Failed to initialize Groq client: %s", type(e).__name__)
        return None


def format_messages(
    messages: List[Dict[str, str]],
    system: str = "",
) -> List[Dict[str, str]]:
    """Map Charlie conversation messages to Groq chat completions format."""
    groq_messages: List[Dict[str, str]] = []

    if system and system.strip():
        groq_messages.append({"role": "system", "content": system.strip()})

    for m in messages:
        if not isinstance(m, dict):
            continue
        raw_role = str(m.get("role", "user")).lower().strip()
        content = str(m.get("content") or "").strip()
        if not content:
            continue

        if raw_role in ("assistant", "model"):
            role = "assistant"
        elif raw_role == "system":
            role = "system"
        else:
            role = "user"

        groq_messages.append({"role": role, "content": content})

    return groq_messages


def chat_text(
    messages: List[Dict[str, str]],
    system: str = "",
    model: str = GROQ_PRIMARY_MODEL,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    timeout_ms: Optional[int] = None,
    key: str = "",
) -> str:
    """Run a text-chat completion through Groq Chat API.

    Drop-in compatible with core.gemini.chat_text signature.
    Returns empty string on any failure without raising exceptions or crashing.
    """
    if timeout_ms is not None:
        timeout = max(1.0, timeout_ms / 1000.0)

    client = get_groq_client(key=key, timeout=timeout)
    if client is None:
        return ""

    resolved_model = resolve_model(model)
    formatted = format_messages(messages, system=system)
    if not formatted:
        return ""

    try:
        response = client.chat.completions.create(
            model=resolved_model,
            messages=formatted,
            stream=False,
        )
        if response and response.choices:
            choice = response.choices[0]
            if choice and choice.message and choice.message.content:
                return choice.message.content.strip()
    except AuthenticationError:
        logger.warning("[Groq] Authentication failed: invalid or expired GROQ_API_KEY.")
    except RateLimitError:
        logger.warning("[Groq] Rate limit reached (429).")
    except APITimeoutError:
        logger.warning("[Groq] Request timed out after %.1f seconds.", timeout)
    except APIConnectionError:
        logger.warning("[Groq] Connection to Groq API failed.")
    except (BadRequestError, NotFoundError) as e:
        logger.warning("[Groq] Bad request or model not found for '%s': %s", resolved_model, type(e).__name__)
    except Exception as e:
        logger.warning("[Groq] Chat completion failed: %s", type(e).__name__)

    return ""


def stream_chat(
    messages: List[Dict[str, str]],
    system: str = "",
    model: str = GROQ_PRIMARY_MODEL,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    timeout_ms: Optional[int] = None,
    key: str = "",
) -> Iterator[str]:
    """Stream chat completion tokens from Groq API."""
    if timeout_ms is not None:
        timeout = max(1.0, timeout_ms / 1000.0)

    client = get_groq_client(key=key, timeout=timeout)
    if client is None:
        return

    resolved_model = resolve_model(model)
    formatted = format_messages(messages, system=system)
    if not formatted:
        return

    try:
        stream = client.chat.completions.create(
            model=resolved_model,
            messages=formatted,
            stream=True,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
    except Exception as e:
        logger.warning("[Groq] Stream interrupted: %s", type(e).__name__)
        return
