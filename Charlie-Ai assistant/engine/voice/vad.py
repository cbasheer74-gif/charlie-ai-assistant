"""engine/voice/vad.py — Voice Activity Detection, Energy Calculation, and End-of-Utterance Timing."""

from __future__ import annotations

import time
from typing import List, Tuple
import numpy as np


class VoiceActivityDetector:
    """Detects speech presence, silence intervals, and natural end-of-utterance boundaries."""

    def __init__(
        self,
        energy_threshold: float = 0.012,
        silence_timeout_sec: float = 1.3,
        min_speech_duration_sec: float = 0.3,
    ):
        self.energy_threshold = energy_threshold
        self.silence_timeout_sec = silence_timeout_sec
        self.min_speech_duration_sec = min_speech_duration_sec

        self._is_speaking: bool = False
        self._speech_start_time: float = 0.0
        self._last_speech_time: float = 0.0
        self._total_speech_frames: int = 0

    def reset(self) -> None:
        self._is_speaking = False
        self._speech_start_time = 0.0
        self._last_speech_time = 0.0
        self._total_speech_frames = 0

    @staticmethod
    def calculate_energy(audio_chunk: np.ndarray) -> float:
        """Calculate Root Mean Square (RMS) energy of audio frame."""
        if audio_chunk is None or len(audio_chunk) == 0:
            return 0.0
        if audio_chunk.dtype != np.float32:
            audio_chunk = audio_chunk.astype(np.float32)
        return float(np.sqrt(np.mean(audio_chunk ** 2)))

    def process_frame(self, audio_chunk: np.ndarray) -> Tuple[bool, bool, float]:
        """Processes an audio chunk and returns:

        (is_voice_active, is_utterance_complete, current_energy).
        """
        now = time.time()
        energy = self.calculate_energy(audio_chunk)
        is_voice = energy >= self.energy_threshold

        utterance_complete = False

        if is_voice:
            if not self._is_speaking:
                self._is_speaking = True
                self._speech_start_time = now
            self._last_speech_time = now
            self._total_speech_frames += 1
        else:
            if self._is_speaking:
                silence_duration = now - self._last_speech_time
                frame_estimated_duration = self._total_speech_frames * 0.02
                speech_duration = max(self._last_speech_time - self._speech_start_time, frame_estimated_duration)

                if silence_duration >= self.silence_timeout_sec:
                    if speech_duration >= self.min_speech_duration_sec:
                        utterance_complete = True
                    self._is_speaking = False

        return is_voice, utterance_complete, energy
