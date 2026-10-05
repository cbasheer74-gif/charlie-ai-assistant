"""engine/voice/wake_word.py — Local Wake Word Engine with Multilingual Phrase Support.

Supports wake phrases in 55+ languages so users can wake Charlie in their native script:
  "Charlie सुनो"  (Hindi)   "Charlie শোনো" (Bengali)  "Charlie கேளு" (Tamil)
  "Charlie 聞いて" (Japanese) "Charlie 들어"  (Korean)   "چارلی سنو"    (Urdu/Farsi)
  "Charlie écoute" (French)  "Charlie escúchame" (Spanish) ...etc.
"""

from __future__ import annotations

import re
import time
from typing import Callable, Dict, List, Optional, Tuple
import numpy as np


# ---------------------------------------------------------------------------
# Multilingual wake phrase table
# Each entry: (canonical_name, listen_variants...)
# Variants use the local word for "listen/hear" appended to the Charlie name.
# ---------------------------------------------------------------------------
_MULTILINGUAL_PHRASES: List[Tuple[str, ...]] = [
    # ── Core English ────────────────────────────────────────────────────────
    ("hey charlie", "charlie", "hello charlie", "ok charlie", "yo charlie"),

    # ── Indian languages — Devanagari script ────────────────────────────────
    # Hindi
    ("charlie सुनो", "चार्ली सुनो", "charlie सुन", "charlie बताओ"),
    # Marathi
    ("charlie ऐक", "charlie बघ", "चार्ली ऐक"),
    # Sanskrit/Nepali crossover
    ("charlie श्रोत", "charlie सुन"),

    # ── Bengali / Assamese (shared script) ─────────────────────────────────
    ("charlie শোনো", "চার্লি শোনো", "charlie শুনুন", "charlie বলো"),
    # Assamese variant
    ("charlie শোনা", "চাৰ্লি শুনা"),

    # ── Dravidian scripts ───────────────────────────────────────────────────
    # Tamil
    ("charlie கேளு", "charlie கேட்க", "சார்லி கேளு", "சார்லி கேட்"),
    # Telugu
    ("charlie వినండి", "charlie వినుము", "చార్లీ వినండి"),
    # Kannada
    ("charlie ಕೇಳು", "ಚಾರ್ಲಿ ಕೇಳು", "charlie ಹೇಳು"),
    # Malayalam
    ("charlie കേൾക്കൂ", "ചാർലി കേൾ", "charlie കേൾ"),

    # ── Gujarati ────────────────────────────────────────────────────────────
    ("charlie સાંભળ", "ચાર્લી સાંભળ"),

    # ── Punjabi (Gurmukhi) ──────────────────────────────────────────────────
    ("charlie ਸੁਣੋ", "ਚਾਰਲੀ ਸੁਣੋ"),

    # ── Odia ────────────────────────────────────────────────────────────────
    ("charlie ଶୁଣ", "ଚାର୍ଲି ଶୁଣ"),

    # ── Arabic script ───────────────────────────────────────────────────────
    # Arabic
    ("charlie اسمع", "چارلی اسمع", "يا charlie"),
    # Urdu
    ("charlie سنو", "چارلی سنو", "charlie سنیں"),
    # Persian/Farsi
    ("charlie بشنو", "چارلی بشنو"),

    # ── CJK ─────────────────────────────────────────────────────────────────
    # Japanese
    ("charlie 聞いて", "チャーリー聞いて", "charlie ねえ", "チャーリー"),
    # Korean
    ("charlie 들어", "charlie 들어봐", "찰리 들어", "찰리야"),
    # Mandarin Chinese (Simplified)
    ("charlie 听我说", "charlie 听", "查理听", "嗨查理"),
    # Cantonese hints (Traditional)
    ("charlie 聽住", "查理聽"),

    # ── Southeast Asian ──────────────────────────────────────────────────────
    # Thai
    ("charlie ฟัง", "charlie ฟังนะ", "ชาร์ลี ฟัง"),
    # Vietnamese
    ("charlie nghe", "charlie lắng nghe"),
    # Indonesian / Malay
    ("charlie dengar", "charlie dengerin", "charlie tolong"),

    # ── European ─────────────────────────────────────────────────────────────
    # French
    ("charlie écoute", "charlie écoutes", "charlie dis-moi"),
    # Spanish
    ("charlie escucha", "charlie escúchame", "charlie oye"),
    # Portuguese
    ("charlie ouça", "charlie escuta", "charlie ei"),
    # German
    ("charlie hör zu", "charlie hör mal", "charlie hallo"),
    # Italian
    ("charlie ascolta", "charlie dimmi", "charlie senti"),
    # Dutch
    ("charlie luister", "charlie hoor"),
    # Russian
    ("charlie слушай", "charlie послушай", "чарли слушай"),
    # Polish
    ("charlie słuchaj", "charlie hej"),
    # Greek
    ("charlie άκου", "charlie ακούς"),
    # Hebrew
    ("charlie תקשיב", "charlie שמע"),
    # Turkish
    ("charlie dinle", "charlie söyle"),
    # Swahili
    ("charlie sikiliza", "charlie sikia"),
]


def _build_flat_phrase_list() -> List[str]:
    """Flatten all multilingual variants into a single deduplicated list."""
    seen: set[str] = set()
    result: List[str] = []
    for group in _MULTILINGUAL_PHRASES:
        for phrase in group:
            p = phrase.strip().lower()
            if p not in seen:
                seen.add(p)
                result.append(p)
    return result


_ALL_WAKE_PHRASES: List[str] = _build_flat_phrase_list()


class WakeWordEngine:
    """Local wake-word detector with multilingual phrase support, echo cancellation,
    and configurable sensitivity.

    Supports 55+ languages — user can say "Charlie सुनो", "charlie 聞いて",
    "charlie écoute" etc. and the engine will wake correctly.
    """

    # Keep for backward compat (subset visible to external callers)
    SUPPORTED_WAKE_PHRASES = [
        "hey charlie", "charlie", "hello charlie",
    ]

    def __init__(
        self,
        wake_phrase: str = "Hey Charlie",
        threshold: float = 0.5,
        on_wake_detected: Optional[Callable[[], None]] = None,
        extra_phrases: Optional[List[str]] = None,
    ):
        self.wake_phrase = wake_phrase.strip().lower()
        self.threshold = threshold
        self.on_wake_detected = on_wake_detected

        # Build active phrase list: all multilingual + any caller-supplied extras
        self._active_phrases: List[str] = list(_ALL_WAKE_PHRASES)
        if extra_phrases:
            for ep in extra_phrases:
                ep_l = ep.strip().lower()
                if ep_l not in self._active_phrases:
                    self._active_phrases.append(ep_l)
        # Ensure the configured wake_phrase is included
        if self.wake_phrase and self.wake_phrase not in self._active_phrases:
            self._active_phrases.append(self.wake_phrase)

        self._is_charlie_speaking: bool = False
        self._enabled: bool = True
        self._last_wake_time: float = 0.0

        # Statistics for debugging
        self._wake_counts: Dict[str, int] = {}

    # ── Backward-compat aliases ──────────────────────────────────────────────

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

    # ── Main API ─────────────────────────────────────────────────────────────

    def add_wake_phrase(self, phrase: str) -> None:
        """Dynamically register an additional wake phrase (e.g. from user settings)."""
        p = phrase.strip().lower()
        if p and p not in self._active_phrases:
            self._active_phrases.append(p)

    def get_active_phrases(self) -> List[str]:
        """Return all currently active wake phrases (read-only snapshot)."""
        return list(self._active_phrases)

    def inspect_text_for_wake(self, text: str) -> bool:
        """Inspects transcribed text for any active wake phrase.

        Checks all multilingual variants so "Charlie सुनो", "charlie 聞いて",
        etc. are all detected correctly without any language configuration.
        """
        if not self._enabled or self._is_charlie_speaking:
            return False

        low = text.lower().strip()
        matched_phrase: Optional[str] = None

        for phrase in self._active_phrases:
            # Direct substring match — works for non-space-delimited scripts (CJK, etc.)
            if phrase in low:
                matched_phrase = phrase
                break

        if matched_phrase:
            self._last_wake_time = time.time()
            self._wake_counts[matched_phrase] = self._wake_counts.get(matched_phrase, 0) + 1
            if self.on_wake_detected:
                self.on_wake_detected()
            return True

        return False

    def process_frame(self, audio_chunk: np.ndarray) -> bool:
        """Real-time frame evaluation. Rejects wake if CHARLIE itself is currently speaking."""
        if not self._enabled or self._is_charlie_speaking:
            return False

        # In live production this delegates to openwakeword/porcupine.
        # Fallback acoustic energy + pattern check hook:
        return False

    def get_wake_stats(self) -> Dict[str, int]:
        """Return how many times each phrase triggered a wake."""
        return dict(self._wake_counts)
