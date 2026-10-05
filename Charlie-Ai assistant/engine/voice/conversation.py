"""engine/voice/conversation.py — Conversation Turn Management, Follow-up Window, Referent Resolution, and In-Flight Correction."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

from engine.voice.models import Transcript, VoiceSession


class ConversationTurnManager:
    """Maintains active multi-turn context, follow-up window, and anaphoric referent resolution."""

    # Referent words and Hinglish pronouns
    REFERENT_WORDS = re.compile(
        r"\b(ye|yeh|wo|woh|isko|usko|use|isse|unhe|isme|usme|in\s+it|inside\s+it|it|that|this|wahi|same\s+project|us\s+file)\b",
        re.I,
    )
    OBJECT_REFERENTS = re.compile(
        r"\b(ye|yeh|wo|woh|isko|usko|use|isse|unhe|it|that|this)\b", re.I
    )
    CONTAINER_REFERENTS = re.compile(
        r"\b(isme|usme|in\s+it|inside\s+it)\b", re.I
    )

    # Self-correction patterns
    # 1. Delimited correction: "X... no Y", "X, actually Y", "X - rather Y", "X... nahi Y"
    PAUSE_CORRECTION_PATTERN = re.compile(
        r"^(.*?)(?:\.\.\.|,\s*|\s+-\s+)\s*(?:nahi|nahin|no|actually|wait\s+no|instead|rather|matlab|sorry)\s*,?\s*(.+)$",
        re.I,
    )
    # Legacy backward-compatible pattern alias
    CORRECTION_PATTERN = re.compile(
        r"(.+?)(?:\.\.\.|\s+)?(?:nahi|no|actually|instead|rather)\s+(.+)", re.I
    )

    # 2. Hinglish action cancellation: "ye file delete nahi, rename karo"
    HINGLISH_ACTION_CANCEL_PATTERN = re.compile(
        r"^(.*?)\s*(\bdelete|\bclose|\bopen|\bremove|\bshutdown|\bformat)\b\s+(?:nahi|nahin)\s*[,|-]?\s*(.+)$",
        re.I,
    )

    # Known application targets
    KNOWN_APPS = {
        "chrome", "edge", "firefox", "brave", "safari", "notepad", "vs code", "vscode",
        "calculator", "spotify", "explorer", "terminal", "slack", "discord", "word",
        "excel", "powerpoint", "charlie"
    }

    # Known directory / folder targets
    KNOWN_FOLDERS = {
        "downloads", "documents", "desktop", "pictures", "videos", "music"
    }

    ACTION_VERBS = {
        "open", "launch", "start", "run", "kholo", "chalao", "close", "exit", "quit",
        "band", "delete", "remove", "hatao", "rename", "badlo", "create", "banao"
    }

    def __init__(self, follow_up_window_sec: float = 10.0):
        self.follow_up_window_sec = follow_up_window_sec
        self.active_session = VoiceSession(session_id=f"v_sess_{int(time.time())}")
        self.recent_entities: List[str] = []
        self.last_target: Optional[str] = None
        self.last_container: Optional[str] = None
        self.last_action: Optional[str] = None

    def reset_session(self) -> None:
        """Reset conversation state completely for new session/profile."""
        self.active_session = VoiceSession(session_id=f"v_sess_{int(time.time())}")
        self.recent_entities.clear()
        self.last_target = None
        self.last_container = None
        self.last_action = None

    def is_in_follow_up_window(self) -> bool:
        """True if the user is within the active conversation window (no wake word needed)."""
        return self.active_session.is_active(self.follow_up_window_sec)

    def update_activity(self) -> None:
        self.active_session.last_interaction_time = time.time()

    def record_turn(self, transcript: Transcript) -> None:
        self.active_session.turns.append(transcript)
        self.update_activity()
        if transcript.raw_transcript:
            self._extract_and_update_entities(transcript.raw_transcript)

    def record_turn_text(self, text: str, role: str = "user") -> None:
        """Helper to record simple text turns into the active session context."""
        transcript = Transcript(
            raw_transcript=text,
            normalized_transcript=text.lower().strip(),
            session_id=self.active_session.session_id,
        )
        self.record_turn(transcript)

    def set_active_project(self, project_name: str) -> None:
        self.active_session.active_project = project_name
        self.active_session.last_referent = project_name
        self.last_target = project_name
        self.recent_entities = [project_name]
        self.update_activity()

    def set_last_action(self, action_name: str, target: str = "") -> None:
        self.active_session.last_action = action_name
        self.last_action = action_name
        if target:
            self.active_session.last_referent = target
            self.last_target = target
            self.recent_entities = [target]
        self.update_activity()

    def _extract_and_update_entities(self, text: str) -> None:
        """Extract candidate entities from turn text to track context."""
        lower = text.lower()
        found: List[str] = []

        # 1. Known apps
        for app in self.KNOWN_APPS:
            if re.search(r"\b" + re.escape(app) + r"\b", lower):
                title_app = "VS Code" if app in ("vs code", "vscode") else app.title()
                if title_app not in found:
                    found.append(title_app)

        # 2. Known folders
        for folder in self.KNOWN_FOLDERS:
            if re.search(r"\b" + re.escape(folder) + r"\b", lower):
                title_folder = folder.title()
                if title_folder not in found:
                    found.append(title_folder)
                self.last_container = title_folder

        # 3. Custom folder patterns: "X folder"
        folder_match = re.search(r"\b([A-Za-z0-9_\-]+)\s+folder\b", text, re.I)
        if folder_match:
            f_name = folder_match.group(1).strip()
            if f_name.lower() not in ("this", "that", "the", "a", "an", "isme", "usme", "wala"):
                if f_name not in found:
                    found.append(f_name)
                self.last_container = f_name

        # 4. Action verb targets: "open <target>", "<target> kholo"
        cmd_match = re.search(r"\b(?:open|launch|kholo|chalao)\s+([A-Za-z0-9_\-]+)\b", text, re.I)
        if cmd_match:
            target = cmd_match.group(1).strip()
            if target.lower() not in ("it", "this", "that", "the", "a", "an", "window", "folder"):
                cased = target.title()
                if cased not in found:
                    found.append(cased)

        if found:
            self.recent_entities = found
            if len(found) == 1:
                self.last_target = found[0]
            else:
                # Multiple entities mentioned -> ambiguous for subsequent singular referents
                self.last_target = None

    def resolve_in_flight_correction(self, text: str) -> str:
        """Resolves conversational self-corrections like:
        - 'Chrome kholo... nahi Edge kholo' -> 'Edge kholo'
        - 'Open Chrome... no Edge' -> 'Open Edge'
        - 'Delete this file... actually rename it' -> 'rename it'
        - 'Delete this file... no rename it' -> 'rename it'
        - 'ye file delete nahi, rename karo' -> 'ye file rename karo'
        """
        # Hinglish action cancellation: "ye file delete nahi, rename karo"
        cancel_match = self.HINGLISH_ACTION_CANCEL_PATTERN.search(text)
        if cancel_match:
            prefix = cancel_match.group(1).strip()
            corrected_action = cancel_match.group(3).strip()
            if prefix:
                return f"{prefix} {corrected_action}".strip()
            return corrected_action

        # Pause-based self-correction: "Open Chrome... no Edge"
        match = self.PAUSE_CORRECTION_PATTERN.search(text)
        if match:
            prefix = match.group(1).strip()
            corrected_clause = match.group(2).strip()

            prefix_words = prefix.split()
            first_word_lower = prefix_words[0].lower() if prefix_words else ""
            corrected_words = corrected_clause.split()
            corrected_has_verb = any(w.lower() in self.ACTION_VERBS for w in corrected_words)

            if first_word_lower in self.ACTION_VERBS and not corrected_has_verb:
                # Inherit action verb from prefix: "Open" + "Edge" -> "Open Edge"
                return f"{prefix_words[0]} {corrected_clause}"

            return corrected_clause

        return text

    def resolve_referents(self, user_text: str) -> str:
        """Resolves anaphoric referents ('it', 'isko', 'isme', 'wo', etc.) using recent context."""
        cleaned = self.resolve_in_flight_correction(user_text)

        # Legacy active project handling (preserves backward compatibility)
        if self.active_session.active_project:
            proj = self.active_session.active_project
            if "backend" in cleaned.lower() and proj.lower() not in cleaned.lower():
                return f"{proj} {cleaned}"

        # If multiple entities exist in context, referent resolution is AMBIGUOUS
        # Requirement 5: Never silently rewrite when confidence is low.
        if len(self.recent_entities) > 1 and self.last_target is None:
            return cleaned

        # 1. Container referents: "isme", "usme", "in it", "inside it"
        if self.last_container and self.CONTAINER_REFERENTS.search(cleaned):
            if re.search(r"\b(in\s+it|inside\s+it)\b", cleaned, re.I):
                return re.sub(r"\b(in\s+it|inside\s+it)\b", f"in {self.last_container}", cleaned, count=1, flags=re.I)
            elif re.search(r"\b(isme|usme)\b", cleaned, re.I):
                return re.sub(r"\b(isme|usme)\b", f"{self.last_container} mein", cleaned, count=1, flags=re.I)

        # 2. Object referents: "it", "isko", "usko", "ye", "wo", etc.
        target = self.last_target or self.active_session.active_project
        if target:
            # English: "close it" -> "close Chrome"
            if re.search(r"\b(it|that|this)\b", cleaned, re.I):
                return re.sub(r"\b(it|that|this)\b", target, cleaned, count=1, flags=re.I)

            # Hinglish: "isko band karo" -> "Chrome band karo"
            if re.search(r"\b(isko|usko|use|isse)\b", cleaned, re.I):
                return re.sub(r"\b(isko|usko|use|isse)\b", target, cleaned, count=1, flags=re.I)

            # Relative: "wo previous window" -> "previous Chrome window"
            if re.search(r"\b(wo\s+previous\s+window|previous\s+window)\b", cleaned, re.I):
                return re.sub(r"\b(wo\s+previous\s+window|previous\s+window)\b", f"previous {target} window", cleaned, count=1, flags=re.I)

            # General Hinglish referents: "ye", "wo", "wahi"
            if re.search(r"\b(ye|yeh|wo|woh|wahi)\b", cleaned, re.I):
                return re.sub(r"\b(ye|yeh|wo|woh|wahi)\b", target, cleaned, count=1, flags=re.I)

        return cleaned
