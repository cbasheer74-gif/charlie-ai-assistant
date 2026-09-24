"""engine/voice/stt.py — Speech-to-Text Abstraction, Vocabulary Context, Hinglish Normalization."""

from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import numpy as np

from engine.voice.models import Transcript


class VocabularyContextManager:
    """Provides project, person, and tool vocabulary priming for speech recognition."""

    DEFAULT_TECHNICAL_TERMS = [
        "ZynPay", "EchoVision", "Antigravity", "Flutter", "PostgreSQL",
        "GitHub", "FFmpeg", "VS Code", "FastAPI", "SQLite", "Python",
        "YouTube", "Shorts", "Excel", "Openpyxl", "PyQt6", "Playwright",
    ]

    def __init__(self, custom_terms: Optional[List[str]] = None):
        self._terms = list(self.DEFAULT_TECHNICAL_TERMS)
        if custom_terms:
            self._terms.extend(custom_terms)

    def get_prompt_context(self) -> str:
        """Returns comma-separated keywords for Whisper/STT initial prompt."""
        return ", ".join(self._terms)

    def add_project_terms(self, project_name: str, tech_stack: List[str]) -> None:
        if project_name and project_name not in self._terms:
            self._terms.append(project_name)
        for t in tech_stack:
            if t not in self._terms:
                self._terms.append(t)


class TranscriptNormalizer:
    """Normalizes tech terms and common Hinglish code-switching without mangling intent."""

    REPLACEMENTS = [
        (re.compile(r"\b(vs\s*code|v\s*s\s*code)\b", re.I), "VS Code"),
        (re.compile(r"\b(git\s*hub)\b", re.I), "GitHub"),
        (re.compile(r"\b(post\s*gre\s*sequel|postgres|post\s*gresql)\b", re.I), "PostgreSQL"),
        (re.compile(r"\b(antigravity|anti\s*gravity)\b", re.I), "Antigravity"),
        (re.compile(r"\b(zyn\s*pay|zinpay)\b", re.I), "ZynPay"),
        (re.compile(r"\b(f\s*f\s*mpeg|f\s*mpeg)\b", re.I), "FFmpeg"),
        (re.compile(r"\b(you\s*tube)\b", re.I), "YouTube"),
    ]

    @staticmethod
    def detect_language(text: str) -> str:
        """Detects if transcript is primarily English, Hindi, or Hinglish."""
        hinglish_words = {"kholo", "banao", "chalao", "ruko", "band", "karo", "aaj", "mera", "ye", "wo", "kaise", "sach", "hai"}
        words = set(re.findall(r"\w+", text.lower()))
        matched = len(words.intersection(hinglish_words))
        if matched >= 1:
            return "hinglish"
        return "en"

    @classmethod
    def normalize(cls, raw_text: str) -> str:
        if not raw_text:
            return ""

        text = raw_text.strip()
        for pattern, replacement in cls.REPLACEMENTS:
            text = pattern.sub(replacement, text)

        # Remove stuttered repetitions at sentence beginnings e.g. "Jarvis Jarvis"
        text = re.sub(r"^(hey\s+jarvis|jarvis)\s+(hey\s+jarvis|jarvis)\b", r"\1", text, flags=re.I)
        return text.strip()


class SpeechRecognitionProvider(ABC):
    """Abstract interface for Speech-to-Text providers."""

    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def transcribe(self, audio: np.ndarray, vocabulary_context: str = "") -> Transcript:
        pass

    def health_check(self) -> bool:
        return True


class MockSTTProvider(SpeechRecognitionProvider):
    """Deterministic STT provider for automated test verification."""

    def __init__(self, default_response: str = "Hey Jarvis"):
        self.default_response = default_response
        self._preset_transcripts: List[str] = []

    def name(self) -> str:
        return "MockSTT"

    def enqueue_transcript(self, text: str) -> None:
        self._preset_transcripts.append(text)

    def transcribe(self, audio: np.ndarray, vocabulary_context: str = "") -> Transcript:
        raw = self._preset_transcripts.pop(0) if self._preset_transcripts else self.default_response
        normalized = TranscriptNormalizer.normalize(raw)
        lang = TranscriptNormalizer.detect_language(raw)
        return Transcript(
            raw_transcript=raw,
            normalized_transcript=normalized,
            language=lang,
            confidence=0.98,
        )


class FasterWhisperSTTProvider(SpeechRecognitionProvider):
    """Offline local transcription using faster-whisper."""

    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self._stt_engine: Optional[Any] = None

    def name(self) -> str:
        return "FasterWhisper"

    def _get_engine(self):
        if self._stt_engine is None:
            try:
                from core.stt import WhisperSTT
                self._stt_engine = WhisperSTT(model_name=self.model_size)
            except Exception:
                pass
        return self._stt_engine

    def transcribe(self, audio: np.ndarray, vocabulary_context: str = "") -> Transcript:
        engine = self._get_engine()
        if engine is None:
            return Transcript(raw_transcript="", normalized_transcript="", confidence=0.0)

        try:
            raw = engine.transcribe(audio)
            normalized = TranscriptNormalizer.normalize(raw)
            lang = TranscriptNormalizer.detect_language(raw)
            return Transcript(
                raw_transcript=raw,
                normalized_transcript=normalized,
                language=lang,
                confidence=0.92,
            )
        except Exception:
            return Transcript(raw_transcript="", normalized_transcript="", confidence=0.0)


class SpeechRecognitionManager:
    """Manages STT providers, hybrid fallback (LOCAL vs CLOUD), and technical priming."""

    def __init__(
        self,
        provider: Optional[SpeechRecognitionProvider] = None,
        mode: str = "AUTO",
    ):
        self.mode = mode.upper()
        self.vocabulary = VocabularyContextManager()
        self.active_provider = provider or MockSTTProvider()

    def set_provider(self, provider: SpeechRecognitionProvider) -> None:
        self.active_provider = provider

    def transcribe_audio(self, audio: np.ndarray) -> Transcript:
        context_prompt = self.vocabulary.get_prompt_context()
        try:
            transcript = self.active_provider.transcribe(audio, vocabulary_context=context_prompt)
            return transcript
        except Exception:
            # Fallback mock/empty transcript on error
            return Transcript(raw_transcript="", normalized_transcript="", confidence=0.0)
