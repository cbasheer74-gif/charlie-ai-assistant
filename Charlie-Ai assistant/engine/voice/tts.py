"""engine/voice/tts.py — Text-to-Speech Abstraction, Natural Output Formatting, and Barge-In Audio Stop."""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from typing import Callable, List, Optional


class TTSProvider(ABC):
    """Abstract interface for TTS playback."""

    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def synthesize_and_play(
        self,
        text: str,
        voice: str = "",
        speed: float = 1.0,
        volume: float = 1.0,
        stop_event: Optional[threading.Event] = None,
    ) -> bool:
        pass


class MockTTSProvider(TTSProvider):
    """Mock TTS provider for unit tests and headless execution."""

    def __init__(self):
        self.spoken_history: List[str] = []
        self.last_spoken: str = ""
        self.is_playing: bool = False

    def name(self) -> str:
        return "MockTTS"

    def synthesize_and_play(
        self,
        text: str,
        voice: str = "",
        speed: float = 1.0,
        volume: float = 1.0,
        stop_event: Optional[threading.Event] = None,
    ) -> bool:
        self.is_playing = True
        self.last_spoken = text
        self.spoken_history.append(text)

        # Simulate brief audio playback while checking stop_event
        for _ in range(5):
            if stop_event and stop_event.is_set():
                self.is_playing = False
                return False
            time.sleep(0.01)

        self.is_playing = False
        return True


class SAPI5TTSProvider(TTSProvider):
    """Windows native SAPI5 speech provider – zero dependency, works offline."""

    def name(self) -> str:
        return "SAPI5TTS"

    def synthesize_and_play(
        self,
        text: str,
        voice: str = "",
        speed: float = 1.0,
        volume: float = 1.0,
        stop_event: Optional[threading.Event] = None,
    ) -> bool:
        try:
            from core.tts import WindowsSAPITTSEngine
            engine = WindowsSAPITTSEngine(voice=voice)
            engine.speak(text)
            return True
        except Exception:
            return False


class EdgeTTSProvider(TTSProvider):
    """EdgeTTS provider with automated Windows SAPI5 fallback."""

    def name(self) -> str:
        return "EdgeTTS"

    def synthesize_and_play(
        self,
        text: str,
        voice: str = "en-US-ChristopherNeural",
        speed: float = 1.0,
        volume: float = 1.0,
        stop_event: Optional[threading.Event] = None,
    ) -> bool:
        try:
            from core.tts import EdgeTTS
            tts = EdgeTTS(voice=voice or "en-US-ChristopherNeural")
            tts.speak(text)
            return True
        except Exception:
            sapi = SAPI5TTSProvider()
            return sapi.synthesize_and_play(
                text=text,
                voice=voice,
                speed=speed,
                volume=volume,
                stop_event=stop_event,
            )


class TextToSpeechManager:
    """Manages speech synthesis, interruption, natural phrasing, and quiet mode."""

    def __init__(self, provider: Optional[TTSProvider] = None):
        self.active_provider: TTSProvider = provider or EdgeTTSProvider()
        self.quiet_mode: bool = False
        self.voice_speed: float = 1.0
        self.voice_volume: float = 1.0
        self.preferred_voice: str = ""

        self._stop_event = threading.Event()
        self._is_speaking = False
        self._lock = threading.Lock()

    def set_quiet_mode(self, quiet: bool) -> None:
        self.quiet_mode = quiet

    def is_speaking(self) -> bool:
        return self._is_speaking

    def stop(self) -> None:
        """Immediately interrupts and cancels active speech output."""
        self._stop_event.set()
        self._is_speaking = False

    def speak(
        self,
        text: str,
        is_critical: bool = False,
        on_complete: Optional[Callable[[], None]] = None,
    ) -> bool:
        """Speaks the response concisely. Respects quiet mode unless critical confirmation."""
        if not text or (self.quiet_mode and not is_critical):
            if on_complete:
                on_complete()
            return False

        with self._lock:
            self._stop_event.clear()
            self._is_speaking = True

        def _worker():
            try:
                self.active_provider.synthesize_and_play(
                    text=text,
                    voice=self.preferred_voice,
                    speed=self.voice_speed,
                    volume=self.voice_volume,
                    stop_event=self._stop_event,
                )
            finally:
                self._is_speaking = False
                if on_complete:
                    on_complete()

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        return True
