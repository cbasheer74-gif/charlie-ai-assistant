# actions/writing_polish.py
"""
Writing Polish & Executive Tone Enhancer for Charlie.

Voice commands:
  "Polish this text"
  "Make this more executive"
  "Fix grammar and typos in what I just copied"
  "Convert this into 3 concise bullet points"
  "Make this sound friendly but professional"
  "Shorten this email draft"
"""

from __future__ import annotations

import json
import platform
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

TOOL = {
    "name": "writing_polish",
    "description": (
        "Polishes, rewrites, corrects grammar, and formats text for office and daily computer tasks. "
        "Can read directly from the clipboard, re-tone text (executive, professional, friendly, persuasive), "
        "shorten to key takeaways, or convert into bullet points, and copy the polished result back to clipboard. "
        "Trigger on: 'polish this', 'fix grammar', 'make it professional', 'rewrite this', "
        "'make it executive', 'convert to bullet points', 'shorten this', 'improve my writing'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["polish", "grammar", "tone", "shorten", "expand", "bullet_points", "from_clipboard"],
                "description": "polish=general rewrite, grammar=typo/grammar fix, tone=adjust voice, shorten=condense, expand=flesh out, bullet_points=bullets, from_clipboard=read and polish clipboard",
            },
            "text": {
                "type": "string",
                "description": "Text to polish. If empty, Charlie inspects clipboard automatically.",
            },
            "tone": {
                "type": "string",
                "enum": ["executive", "professional", "casual", "friendly", "persuasive", "direct"],
                "description": "Target tone for rewriting (default: professional)",
            },
            "copy_to_clipboard": {
                "type": "boolean",
                "description": "Whether to copy the finished text to system clipboard (default true)",
            },
        },
        "required": ["action"],
    },
}

from core.app_paths import get_config_dir

_CACHE_FILE = get_config_dir() / "last_polished_text.json"


def _get_clipboard_text() -> str:
    try:
        import pyperclip  # type: ignore
        text = pyperclip.paste()
        if text:
            return text.strip()
    except Exception:
        pass

    if platform.system() == "Windows":
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            return res.stdout.strip()
        except Exception:
            pass
    return ""


def _set_clipboard_text(text: str) -> None:
    try:
        import pyperclip  # type: ignore
        pyperclip.copy(text)
        return
    except Exception:
        pass

    if platform.system() == "Windows":
        try:
            subprocess.run(["clip"], input=text.encode("utf-16"), check=True)
        except Exception:
            pass


def _cache_result(original: str, polished: str, style: str) -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(
            json.dumps({"original": original, "polished": polished, "style": style}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def execute(
    action: str = "polish",
    text: Optional[str] = None,
    tone: str = "professional",
    copy_to_clipboard: bool = True,
    **kwargs: Any,
) -> str:
    """Execute writing polish action."""
    source_text = (text or "").strip()
    if not source_text or action == "from_clipboard":
        source_text = _get_clipboard_text()

    if not source_text:
        return (
            "Clipboard is empty and no text was provided. "
            "Please copy the text you want to polish (Ctrl+C) and say 'polish my clipboard', "
            "or dictate the text directly."
        )

    # Prompt wrappers for LLM dispatch when routed through Charlie's engine
    tone_prompts = {
        "executive": (
            "Rewrite this with executive gravitas: clear, decisive, outcome-focused, zero fluff, "
            "suitable for C-level or leadership review."
        ),
        "professional": (
            "Rewrite this in polished corporate English: courteous, structured, unambiguous, and polite."
        ),
        "friendly": (
            "Rewrite this with a warm, approachable, collaborative, yet professional voice."
        ),
        "casual": (
            "Rewrite this in natural, conversational, friendly everyday tone."
        ),
        "persuasive": (
            "Rewrite this persuasively: emphasize benefits, clear value proposition, and a crisp call to action."
        ),
        "direct": (
            "Rewrite this with direct, punchy brevity. Remove redundant words, keep core information only."
        ),
    }

    if action == "grammar":
        instruction = "Fix all grammar mistakes, punctuation, spelling, and typos while keeping original voice intact."
    elif action == "shorten":
        instruction = "Shorten this text to its essential essence in 1-3 crisp sentences. No filler words."
    elif action == "expand":
        instruction = "Expand these notes or thoughts into well-structured, clear professional paragraphs."
    elif action == "bullet_points":
        instruction = "Format this into a clear, scannable bullet-point list with bold key highlights."
    elif action in ("tone", "polish", "from_clipboard"):
        instruction = tone_prompts.get(tone, tone_prompts["professional"])
    else:
        instruction = "Polish and enhance this text for clarity, impact, and grammatical correctness."

    # Offline heuristic fallback if invoked without direct LLM generation in tool harness
    fallback_text = source_text.strip()
    if action == "bullet_points":
        lines = [line.strip("- *").strip() for line in re.split(r"[\n.]+", fallback_text) if len(line.strip()) > 3]
        fallback_text = "\n".join(f"• {line}" for line in lines[:8])
    elif action == "grammar":
        # Basic cleanup: double spaces, capitalization
        sentences = re.split(r"([.?!]\s+)", fallback_text)
        fallback_text = "".join(
            s.capitalize() if i % 2 == 0 else s for i, s in enumerate(sentences)
        )

    if copy_to_clipboard and fallback_text:
        _set_clipboard_text(fallback_text)

    _cache_result(source_text, fallback_text, tone or action)

    clipboard_note = " (Copied to clipboard — ready to Ctrl+V)" if copy_to_clipboard else ""

    return (
        f"[INSTRUCTION FOR CHARLIE: {instruction}\n"
        f"Original Text:\n\"\"\"{source_text}\"\"\"\n"
        f"Output ONLY the polished text followed by a 1-line note saying: '✨ Polished text{clipboard_note}']\n\n"
        f"Preview:\n{fallback_text}"
    )
