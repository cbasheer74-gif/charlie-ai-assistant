"""engine/voice/conversation.py — Conversation Turn Management, Follow-up Window, Referent Resolution, and In-Flight Correction."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

from engine.voice.models import Transcript, VoiceSession


class ConversationTurnManager:
    """Maintains active multi-turn voice context, follow-up window, and anaphoric referent resolution."""

    REFERENT_WORDS = re.compile(r"\b(ye|wo|isko|use|us\s+file|same\s+project|wahi|next|it|that|this)\b", re.I)
    CORRECTION_PATTERN = re.compile(r"(.+?)(?:\.\.\.|\s+)?(?:nahi|no|actually|instead|rather)\s+(.+)", re.I)

    def __init__(self, follow_up_window_sec: float = 10.0):
        self.follow_up_window_sec = follow_up_window_sec
        self.active_session = VoiceSession(session_id=f"v_sess_{int(time.time())}")

    def reset_session(self) -> None:
        self.active_session = VoiceSession(session_id=f"v_sess_{int(time.time())}")

    def is_in_follow_up_window(self) -> bool:
        """True if the user is within the active conversation window (no wake word needed)."""
        return self.active_session.is_active(self.follow_up_window_sec)

    def update_activity(self) -> None:
        self.active_session.last_interaction_time = time.time()

    def record_turn(self, transcript: Transcript) -> None:
        self.active_session.turns.append(transcript)
        self.update_activity()

    def set_active_project(self, project_name: str) -> None:
        self.active_session.active_project = project_name
        self.active_session.last_referent = project_name
        self.update_activity()

    def set_last_action(self, action_name: str, target: str = "") -> None:
        self.active_session.last_action = action_name
        if target:
            self.active_session.last_referent = target
        self.update_activity()

    def resolve_in_flight_correction(self, text: str) -> str:
        """Resolves conversational self-corrections like:

        'Chrome kholo... nahi Edge kholo' -> 'Edge kholo'
        """
        match = self.CORRECTION_PATTERN.search(text)
        if match:
            corrected_clause = match.group(2).strip()
            return corrected_clause
        return text

    def resolve_referents(self, user_text: str) -> str:
        """Enriches anaphoric words ('ye', 'wo', 'backend') with recent active project/file context."""
        cleaned = self.resolve_in_flight_correction(user_text)

        # If user says "backend bhi start karo" and we have an active project
        if self.active_session.active_project:
            proj = self.active_session.active_project
            if "backend" in cleaned.lower() and proj.lower() not in cleaned.lower():
                return f"{proj} {cleaned}"

            if self.REFERENT_WORDS.search(cleaned):
                # Substitute referent with active project/file
                sub = self.REFERENT_WORDS.sub(proj, cleaned, count=1)
                return sub

        return cleaned
