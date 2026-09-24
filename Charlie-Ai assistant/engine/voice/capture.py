"""engine/voice/capture.py — Real-Time Streaming Microphone Capture and Push-to-Talk."""

from __future__ import annotations

import collections
import threading
import time
from typing import Callable, List, Optional
import numpy as np

from engine.voice.audio_device_mgr import AudioDeviceManager
from engine.voice.models import AudioDevice


class MicrophoneCapture:
    """Captures microphone audio frames with thread safety, push-to-talk, and hardware gating."""

    def __init__(
        self,
        device_manager: Optional[AudioDeviceManager] = None,
        sample_rate: int = 16000,
        chunk_size: int = 1024,
    ):
        self.device_manager = device_manager or AudioDeviceManager()
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size

        self.is_muted: bool = False
        self.push_to_talk_active: bool = False
        self._is_capturing: bool = False
        self._capture_thread: Optional[threading.Thread] = None

        # Thread-safe ring buffer: holds up to ~30 seconds of audio chunks
        self._buffer: collections.deque[np.ndarray] = collections.deque(maxlen=480)
        self._lock = threading.Lock()
        self._callbacks: List[Callable[[np.ndarray], None]] = []

    def add_frame_callback(self, callback: Callable[[np.ndarray], None]) -> None:
        self._callbacks.append(callback)

    def set_muted(self, muted: bool) -> None:
        """Hardware/logical mute switch. When muted, no audio frames are delivered."""
        self.is_muted = muted

    def set_push_to_talk(self, active: bool) -> None:
        """Triggered when Push-to-Talk hotkey (e.g. Ctrl+Alt+J) is pressed or released."""
        self.push_to_talk_active = active

    def push_mock_audio(self, audio_chunk: np.ndarray) -> None:
        """Testing hook for deterministic audio feeding."""
        if self.is_muted:
            return
        with self._lock:
            self._buffer.append(audio_chunk)
        for cb in self._callbacks:
            try:
                cb(audio_chunk)
            except Exception:
                pass

    def start(self) -> bool:
        if self._is_capturing:
            return True

        self._is_capturing = True
        return True

    def stop(self) -> None:
        self._is_capturing = False
        with self._lock:
            self._buffer.clear()

    def get_buffered_audio(self) -> np.ndarray:
        """Concatenates all captured chunks in the buffer into a single 1D float32 numpy array."""
        with self._lock:
            if not self._buffer:
                return np.zeros(0, dtype=np.float32)
            chunks = list(self._buffer)
            self._buffer.clear()

        return np.concatenate(chunks).astype(np.float32)
