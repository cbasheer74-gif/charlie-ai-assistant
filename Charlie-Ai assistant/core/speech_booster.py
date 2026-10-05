"""
core/speech_booster.py
High-performance speech acceleration engine:
- Faster-Whisper zero-latency transcription with int8 quantization and VAD gating.
- Local Kokoro neural speech warmup & thread optimization.
- Ultra-low latency voice pipeline orchestration.
"""
from __future__ import annotations

import os
import threading
from typing import Optional, Callable
import numpy as np


class SpeechAccelerator:
    """Orchestrates zero-latency local speech pipeline."""

    _instance: Optional["SpeechAccelerator"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._stt_model = None
        self._stt_ready = False
        self._device = "cpu"
        self._compute_type = "int8"
        self._kokoro_engine = None

    @classmethod
    def get_instance(cls) -> "SpeechAccelerator":
        with cls._lock:
            if cls._instance is None:
                cls._instance = SpeechAccelerator()
            return cls._instance

    def optimize_environment(self) -> dict[str, str]:
        """Configure thread pool and device affinities for peak speech throughput."""
        cpu_count = os.cpu_count() or 4
        threads = max(1, min(4, cpu_count // 2))

        os.environ.setdefault("OMP_NUM_THREADS", str(threads))
        os.environ.setdefault("MKL_NUM_THREADS", str(threads))
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

        try:
            import torch
            if torch.cuda.is_available():
                self._device = "cuda"
                self._compute_type = "float16"
            else:
                self._device = "cpu"
                self._compute_type = "int8"
                torch.set_num_threads(threads)
        except Exception:
            self._device, self._compute_type = "cpu", "int8"

        return {
            "device": self._device,
            "compute_type": self._compute_type,
            "threads": str(threads),
        }

    # Language family → VAD profile
    _LANG_VAD_PROFILES: dict[str, dict] = {
        # Tonal languages: short syllables, rising/falling tones — need generous pad
        "tonal": {
            "min_silence_duration_ms": 600,
            "speech_pad_ms": 450,
        },
        # South Asian scripts: aspirated consonants, retroflex sounds — moderate pad
        "south_asian": {
            "min_silence_duration_ms": 500,
            "speech_pad_ms": 380,
        },
        # Agglutinative: long compound words, minimal pauses between morphemes
        "agglutinative": {
            "min_silence_duration_ms": 650,
            "speech_pad_ms": 420,
        },
        # Semitic (Arabic, Hebrew, Urdu): pharyngeal consonants, right-to-left cadence
        "semitic": {
            "min_silence_duration_ms": 520,
            "speech_pad_ms": 380,
        },
        # Default: Latin/Germanic/Romance — original baseline
        "latin": {
            "min_silence_duration_ms": 400,
            "speech_pad_ms": 250,
        },
    }

    # Whisper language code → family
    _LANG_FAMILY_MAP: dict[str, str] = {
        # Tonal
        "zh": "tonal", "yue": "tonal", "zh-tw": "tonal",
        "th": "tonal", "vi": "tonal",
        # South Asian
        "hi": "south_asian", "mr": "south_asian", "bn": "south_asian",
        "ta": "south_asian", "te": "south_asian", "gu": "south_asian",
        "kn": "south_asian", "ml": "south_asian", "pa": "south_asian",
        "or": "south_asian", "as": "south_asian", "ne": "south_asian",
        "sa": "south_asian", "si": "south_asian",
        # Agglutinative
        "fi": "agglutinative", "hu": "agglutinative", "tr": "agglutinative",
        "ko": "agglutinative", "kk": "agglutinative", "uz": "agglutinative",
        "az": "agglutinative", "ja": "agglutinative",
        # Semitic
        "ar": "semitic", "he": "semitic", "ur": "semitic",
        "fa": "semitic", "sd": "semitic", "am": "semitic",
    }

    def get_fast_stt_kwargs(self, language: str | None = None) -> dict:
        """Returns optimal faster-whisper decoding kwargs for sub-200ms latency.
        Language-aware VAD tuning prevents clipping syllables for non-Latin scripts.
        """
        # Resolve language → family → VAD profile
        lang_key = (language or "").strip().lower()
        if not lang_key or lang_key == "auto":
            try:
                from memory.personal_hub import load_hub
                lang_key = load_hub().get("speech", {}).get("language", "") or ""
            except Exception:
                lang_key = ""
        if not lang_key or lang_key in ("auto", "english"):
            lang_key = "en"

        # Try resolving via languages registry to get whisper_code
        try:
            from core.languages import get_whisper_code
            wcode = get_whisper_code(lang_key)
            if wcode:
                lang_key = wcode
        except Exception:
            pass

        family = self._LANG_FAMILY_MAP.get(lang_key, "latin")
        vad = self._LANG_VAD_PROFILES[family]

        # Quality vs speed: use beam_size=1 for Latin, 2 for complex scripts
        beam = 1 if family == "latin" else 2

        return {
            "beam_size": beam,
            "best_of": beam,
            "temperature": 0.0,
            "condition_on_previous_text": False,
            "compression_ratio_threshold": 2.4,
            "log_prob_threshold": -1.0,
            "no_speech_threshold": 0.6,
            "vad_filter": True,
            "vad_parameters": vad,
        }

    def warm_kokoro_async(self, voice: str = "af_heart", on_ready: Optional[Callable] = None):
        """Asynchronously warm up local Kokoro neural synthesis."""
        def _warm():
            try:
                from core.tts import KokoroTTSEngine
                engine = KokoroTTSEngine(voice=voice)
                self._kokoro_engine = engine
                if on_ready:
                    on_ready(True)
            except Exception:
                if on_ready:
                    on_ready(False)

        t = threading.Thread(target=_warm, daemon=True, name="KokoroWarmupThread")
        t.start()


# Module-level convenience functions
def get_optimized_stt_settings(language: str | None = None) -> dict:
    return SpeechAccelerator.get_instance().get_fast_stt_kwargs(language=language)


def configure_speech_engine():
    return SpeechAccelerator.get_instance().optimize_environment()
