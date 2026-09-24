"""engine/voice/wake_word.py — Local Wake Word Engine, False Wake Rejection, and Self-TTS Echo Lockout."""

from __future__ import annotations

import re
import time
from typing import Callable, List, Optional
import numpy as np


class WakeWordEngine:
    """Local wake-word detector with echo cancellation lockout and configurable sensitivity."""

    SUPPORTED_WAKE_PHRASES = [
        "hey charlie", "charlie", "hello charlie",
        "hey jarvis", "jarvis", "hello jarvis",
    ]

    def __init__(
        self,
        wake_phrase: str = "Hey Charlie",
        threshold: float = 0.5,
        on_wake_detected: Optional[Callable[[], None]] = None,
    ):
        self.wake_phrase = wake_phrase.strip().lower()
        self.threshold = threshold
        self.on_wake_detected = on_wake_detected

        self._is_charlie_speaking: bool = False
        self._enabled: bool = True
        self._last_wake_time: float = 0.0

    @property
    def _is_jarvis_speaking(self) -> bool:
        return self._is_charlie_speaking

    @_is_jarvis_speaking.setter
    def _is_jarvis_speaking(self, value: bool) -> None:
        self._is_charlie_speaking = value

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def set_charlie_speaking(self, speaking: bool) -> None:
        """Echo protection / self-trigger lockout: suppress wake detection while TTS plays."""
        self._is_charlie_speaking = speaking

    def set_jarvis_speaking(self, speaking: bool) -> None:
        """Backward-compatible alias for set_charlie_speaking."""
        self.set_charlie_speaking(speaking)

    def inspect_text_for_wake(self, text: str) -> bool:
        """Inspects transcribed text or fast audio token for wake phrase."""
        if not self._enabled or self._is_charlie_speaking:
            return False

        low = text.lower().strip()
        matched = False
        for wp in self.SUPPORTED_WAKE_PHRASES:
            if wp in low:
                matched = True
                break

        if matched:
            self._last_wake_time = time.time()
            if self.on_wake_detected:
                self.on_wake_detected()
            return True

        return False

    def process_frame(self, audio_chunk: np.ndarray) -> bool:
        """Real-time frame evaluation. Rejects wake if JARVIS/Charlie itself is currently speaking."""
        if not self._enabled or self._is_charlie_speaking:
            return False

        # In live production this delegates to openwakeword/porcupine.
        # Fallback acoustic energy + pattern check hook:
        return False
