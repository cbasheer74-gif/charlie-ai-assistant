"""engine/voice/barge_in.py — Real-Time Interruption, Barge-In Detection, and Emergency Stop."""

from __future__ import annotations

import re
import time
from enum import Enum
from typing import Callable, List, Optional

from engine.voice.models import BargeInEvent
from engine.voice.tts import TextToSpeechManager


class InterruptScope(str, Enum):
    STOP_TTS_ONLY = "STOP_TTS_ONLY"
    STOP_CURRENT_TASK = "STOP_CURRENT_TASK"
    EMERGENCY_STOP_ALL = "EMERGENCY_STOP_ALL"
    CORRECTION = "CORRECTION"


class BargeInManager:
    """Handles real-time speech interruption, barge-in triggers, and tiered emergency stop scopes."""

    INTERRUPT_PATTERNS = [
        (re.compile(r"\b(stop\s+everything|sab\s+automation\s+band|emergency\s+stop)\b", re.I), InterruptScope.EMERGENCY_STOP_ALL),
        (re.compile(r"\b(cancel\s+task|ye\s+task\s+cancel|ruk\s+jao|pause\s+task|task\s+pause|pause\s+karo)\b", re.I), InterruptScope.STOP_CURRENT_TASK),
        (re.compile(r"\b(actually|nahi\s+pehle|correction|instead)\b", re.I), InterruptScope.CORRECTION),
        (re.compile(r"\b(stop|ruko|bas|chup|wait|cancel|quiet|shh)\b", re.I), InterruptScope.STOP_TTS_ONLY),
    ]

    def __init__(self, tts_manager: TextToSpeechManager):
        self.tts_manager = tts_manager
        self._interruption_history: List[BargeInEvent] = []
        self._on_emergency_stop: Optional[Callable[[], None]] = None

    def set_emergency_stop_callback(self, cb: Callable[[], None]) -> None:
        self._on_emergency_stop = cb

    def check_for_interruption(self, transcript_text: str) -> Optional[InterruptScope]:
        """Checks if user's spoken input triggers an immediate barge-in or stop."""
        if not transcript_text:
            return None

        for pattern, scope in self.INTERRUPT_PATTERNS:
            match = pattern.search(transcript_text)
            if match:
                trigger_word = match.group(0)

                # Always stop TTS output immediately upon barge-in
                if self.tts_manager.is_speaking():
                    self.tts_manager.stop()

                event = BargeInEvent(
                    trigger_word=trigger_word,
                    timestamp=time.time(),
                )
                self._interruption_history.append(event)

                if scope == InterruptScope.EMERGENCY_STOP_ALL and self._on_emergency_stop:
                    self._on_emergency_stop()

                return scope

        return None
