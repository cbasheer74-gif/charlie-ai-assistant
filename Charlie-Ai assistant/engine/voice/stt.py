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
        "Charlie", "Antigravity", "Gemini", "Groq", "PyQt6", "Firebase",
        "PostgreSQL", "Prisma", "Lekhtra", "VS Code", "PowerShell", "OCR",
        "API", "npm", "Python", "GitHub", "FastAPI", "SQLite", "Flutter",
        "YouTube", "Shorts", "Excel", "Openpyxl", "Playwright", "ZynPay", "EchoVision",
    ]
    MAX_ITEMS = 50
    MAX_PROMPT_CHARS = 450

    def __init__(self, custom_terms: Optional[List[str]] = None):
        self._terms: List[str] = []
        self._seen: set[str] = set()
        self.add_terms(self.DEFAULT_TECHNICAL_TERMS)
        if custom_terms:
            self.add_terms(custom_terms)

    @staticmethod
    def _sanitize(term: str) -> str:
        """Strip control characters, newlines, and excess whitespace."""
        if not term:
            return ""
        cleaned = re.sub(r"[\r\n\t\x00-\x1f]", " ", str(term))
        return re.sub(r"\s+", " ", cleaned).strip()

    def add_terms(self, terms: List[str]) -> None:
        """Add terms with deduplication and bounding limits."""
        for t in terms:
            cleaned = self._sanitize(t)
            if not cleaned:
                continue
            key = cleaned.lower()
            if key not in self._seen and len(self._terms) < self.MAX_ITEMS:
                self._seen.add(key)
                self._terms.append(cleaned)

    def add_project_terms(self, project_name: str, tech_stack: Optional[List[str]] = None) -> None:
        """Dynamically add project and stack terms safely without scraping sensitive history."""
        to_add = []
        if project_name:
            to_add.append(project_name)
        if tech_stack:
            to_add.extend(tech_stack)
        self.add_terms(to_add)

    def get_terms(self) -> List[str]:
        return list(self._terms)

    def get_prompt_context(self) -> str:
        """Returns bounded comma-separated keywords for Whisper/STT initial prompt."""
        result = []
        current_len = 0
        for term in self._terms:
            added_len = len(term) + (2 if result else 0)
            if current_len + added_len > self.MAX_PROMPT_CHARS:
                break
            result.append(term)
            current_len += added_len
        return ", ".join(result)


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

    SUPPORTED_LANGUAGES = {
        "en", "hi", "hinglish", "mr", "bn", "ta", "te", "gu", "kn", "ml", "pa", "ur", "or", "as",
        "es", "fr", "de", "it", "pt", "ru", "ja", "zh", "ko", "ar", "tr", "nl", "pl", "id", "ms",
        "vi", "th", "fil", "fa", "he", "uk", "el", "sv", "nb", "da", "fi", "cs", "ro", "hu", "sw",
        "af", "bg", "hr", "sk", "sl", "sr", "lt", "lv", "et", "ga", "cy", "ca", "gl", "eu", "is",
        "bho", "mai", "sa", "sd", "ne", "si", "kok", "am", "so", "zu"
    }

    # Regional script patterns for automatic identification
    _SCRIPT_MAP = [
        (re.compile(r"[\u0900-\u097F]"), "hi"),  # Devanagari (Hindi, Marathi, Sanskrit, etc.)
        (re.compile(r"[\u0980-\u09FF]"), "bn"),  # Bengali / Assamese
        (re.compile(r"[\u0A00-\u0A7F]"), "pa"),  # Gurmukhi / Punjabi
        (re.compile(r"[\u0A80-\u0AFF]"), "gu"),  # Gujarati
        (re.compile(r"[\u0B00-\u0B7F]"), "or"),  # Odia
        (re.compile(r"[\u0B80-\u0BFF]"), "ta"),  # Tamil
        (re.compile(r"[\u0C00-\u0C7F]"), "te"),  # Telugu
        (re.compile(r"[\u0C80-\u0CFF]"), "kn"),  # Kannada
        (re.compile(r"[\u0D00-\u0D7F]"), "ml"),  # Malayalam
        (re.compile(r"[\u0600-\u06FF]"), "ur"),  # Arabic / Urdu
    ]

    @staticmethod
    def detect_language(text: str) -> str:
        """Detects if transcript is English, Hindi/Hinglish, or a regional/world language."""
        if not text:
            return "en"

        # Check native scripts via core.languages first
        try:
            from core.languages import detect_language_script
            detected = detect_language_script(text)
            if detected:
                return detected.code
        except Exception:
            pass

        # Check regional scripts
        for pattern, lang_code in TranscriptNormalizer._SCRIPT_MAP:
            if pattern.search(text):
                return lang_code

        hinglish_words = {
            "kholo", "banao", "chalao", "ruko", "band", "karo", "aaj", "mera", "ye", "wo",
            "kaise", "sach", "hai", "kya", "nahi", "theek", "accha", "bolo", "kaha", "idhar"
        }
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

        # Filter unprompted CJK hallucinations
        if re.search(r"[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u30ff\uac00-\ud7af]", text):
            text = re.sub(r"[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u30ff\uac00-\ud7af]+", "", text).strip()

        # Remove stuttered repetitions at sentence beginnings e.g. "Charlie Charlie"
        text = re.sub(r"^(hey\s+charlie|charlie)\s+(hey\s+charlie|charlie)\b", r"\1", text, flags=re.I)

        try:
            from core.stt import is_stt_hallucination
            if is_stt_hallucination(text):
                return ""
        except Exception:
            pass

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

    def __init__(self, default_response: str = "Hey Charlie"):
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

    def set_language(self, language: str | None) -> None:
        """Hot-swap Whisper language hint without model reload."""
        engine = self._get_engine()
        if engine and hasattr(engine, "set_language"):
            engine.set_language(language)

    def transcribe(self, audio: np.ndarray, vocabulary_context: str = "") -> Transcript:
        engine = self._get_engine()
        if engine is None:
            return Transcript(raw_transcript="", normalized_transcript="", confidence=0.0)

        try:
            raw = engine.transcribe(audio, vocabulary_context=vocabulary_context)
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

    def set_language(self, language: str | None) -> None:
        """Hot-swap STT language on the active provider."""
        if hasattr(self.active_provider, "set_language"):
            self.active_provider.set_language(language)

    def transcribe_audio(self, audio: np.ndarray) -> Transcript:
        context_prompt = self.vocabulary.get_prompt_context()
        try:
            transcript = self.active_provider.transcribe(audio, vocabulary_context=context_prompt)

            return transcript
        except Exception:
            # Fallback mock/empty transcript on error
            return Transcript(raw_transcript="", normalized_transcript="", confidence=0.0)
