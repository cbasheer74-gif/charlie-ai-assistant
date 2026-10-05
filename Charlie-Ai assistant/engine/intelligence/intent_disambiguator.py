# engine/intelligence/intent_disambiguator.py
"""
Ambiguous Query Disambiguator & Context Resolver for Charlie.

Resolves elliptic, pronouns, and vague voice commands ("open it", "fix it",
"send this", "clean up", "summarize it") using multi-modal system context:
  - Last copied clipboard item
  - Active document / window
  - Recent diagnostic error
  - Pending email draft
  - Session history

Produces high-confidence structured dispatch or interactive clarification.
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class DisambiguationResult:
    original_query: str
    is_ambiguous: bool
    confidence: float
    resolved_tool: Optional[str]
    resolved_args: Dict[str, Any]
    resolved_intent: str
    clarification_prompt: Optional[str] = None


class IntentDisambiguator:
    """Resolves underspecified voice commands into precise tool executions."""

    PRONOUN_TRIGGERS = {
        "it", "this", "that", "them", "these", "the file", "the link", "the draft", "the error"
    }

    def disambiguate(
        self,
        query: str,
        recent_context: Optional[Dict[str, Any]] = None,
    ) -> DisambiguationResult:
        q_clean = query.strip().lower()
        ctx = recent_context or {}

        # 1. "Open it" / "Open this file"
        if re.match(r"^(open\s+(it|this|that|the\s+file))$", q_clean):
            target = self._resolve_active_file(ctx)
            if target:
                return DisambiguationResult(
                    original_query=query,
                    is_ambiguous=True,
                    confidence=0.88,
                    resolved_tool="file_controller",
                    resolved_args={"action": "open", "path": target},
                    resolved_intent=f"Open recently active file: {Path(target).name}",
                )
            return DisambiguationResult(
                original_query=query,
                is_ambiguous=True,
                confidence=0.30,
                resolved_tool=None,
                resolved_args={},
                resolved_intent="open_file_unknown",
                clarification_prompt="Which file or application would you like Charlie to open?",
            )

        # 2. "Fix it" / "Fix this error"
        if re.search(r"\b(fix\s+(it|this|the\s+error|this\s+code))\b", q_clean):
            err_ctx = self._resolve_recent_error(ctx)
            if err_ctx:
                return DisambiguationResult(
                    original_query=query,
                    is_ambiguous=True,
                    confidence=0.85,
                    resolved_tool="diagnose_error",
                    resolved_args={"error_text": err_ctx},
                    resolved_intent="Diagnose and fix recent error in clipboard/diagnostics",
                )
            return DisambiguationResult(
                original_query=query,
                is_ambiguous=True,
                confidence=0.45,
                resolved_tool="diagnose_error",
                resolved_args={},
                resolved_intent="diagnose_error",
                clarification_prompt="Please paste or tell Charlie the error message you'd like to fix.",
            )

        # 3. "Send this" / "Send it"
        if re.search(r"\b(send\s+(it|this|the\s+draft))\b", q_clean):
            draft = self._check_email_draft()
            if draft:
                return DisambiguationResult(
                    original_query=query,
                    is_ambiguous=True,
                    confidence=0.92,
                    resolved_tool="email_dictation",
                    resolved_args={"action": "send"},
                    resolved_intent=f"Send pending email draft to {draft.get('to', 'recipient')}",
                )
            return DisambiguationResult(
                original_query=query,
                is_ambiguous=True,
                confidence=0.40,
                resolved_tool="email_dictation",
                resolved_args={},
                resolved_intent="send_email",
                clarification_prompt="No active email draft found. Would you like Charlie to draft a new email?",
            )

        # 4. "Summarize it" / "Summarize this"
        if re.search(r"\b(summarize\s+(it|this|that|the\s+page|the\s+article))\b", q_clean):
            clip = self._get_clipboard_preview()
            return DisambiguationResult(
                original_query=query,
                is_ambiguous=True,
                confidence=0.86,
                resolved_tool="page_summarizer",
                resolved_args={"action": "from_clipboard"},
                resolved_intent="Summarize content currently stored in clipboard",
            )

        # 5. "Polish it" / "Make it professional"
        if re.search(r"\b(polish\s+(it|this)|make\s+(it|this)\s+(better|professional|formal))\b", q_clean):
            return DisambiguationResult(
                original_query=query,
                is_ambiguous=True,
                confidence=0.89,
                resolved_tool="writing_polish",
                resolved_args={"action": "from_clipboard", "tone": "professional"},
                resolved_intent="Polish text from clipboard with executive/professional tone",
            )

        # 6. "Clean up"
        if q_clean in {"clean up", "tidy up", "clean it"}:
            return DisambiguationResult(
                original_query=query,
                is_ambiguous=True,
                confidence=0.82,
                resolved_tool="file_organizer",
                resolved_args={"action": "preview", "target": "desktop"},
                resolved_intent="Preview organizing cluttered desktop files into category folders",
            )

        # Non-ambiguous query
        return DisambiguationResult(
            original_query=query,
            is_ambiguous=False,
            confidence=1.0,
            resolved_tool=None,
            resolved_args={},
            resolved_intent=query,
        )

    def _resolve_active_file(self, ctx: Dict[str, Any]) -> Optional[str]:
        # Context active document
        doc = ctx.get("active_document")
        if doc and os.path.exists(doc):
            return doc
        # Recent file from clipboard if it's a valid path
        clip = self._get_clipboard_preview()
        if clip and os.path.exists(clip):
            return clip
        return None

    def _resolve_recent_error(self, ctx: Dict[str, Any]) -> Optional[str]:
        clip = self._get_clipboard_preview()
        if clip and any(kw in clip.lower() for kw in ("traceback", "error", "exception", "failed", "syntaxerror")):
            return clip
        diag_path = Path(__file__).resolve().parent.parent.parent / "config" / "last_diagnostic.json"
        if diag_path.exists():
            try:
                data = json.loads(diag_path.read_text(encoding="utf-8"))
                return data.get("error_text")
            except Exception:
                pass
        return None

    def _check_email_draft(self) -> Optional[Dict[str, Any]]:
        draft_file = Path(__file__).resolve().parent.parent.parent / "config" / "email_draft.json"
        if draft_file.exists():
            try:
                data = json.loads(draft_file.read_text(encoding="utf-8"))
                if data.get("to") and data.get("body"):
                    return data
            except Exception:
                pass
        return None

    def _get_clipboard_preview(self) -> str:
        try:
            import pyperclip  # type: ignore
            return (pyperclip.paste() or "").strip()
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


# Global singleton
_disambiguator_instance: Optional[IntentDisambiguator] = None


def get_intent_disambiguator() -> IntentDisambiguator:
    global _disambiguator_instance
    if _disambiguator_instance is None:
        _disambiguator_instance = IntentDisambiguator()
    return _disambiguator_instance
