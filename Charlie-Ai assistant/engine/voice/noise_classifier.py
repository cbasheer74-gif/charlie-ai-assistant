# engine/voice/noise_classifier.py
"""
Background Noise Classifier for Charlie.

Distinguishes between:
  - CHILDREN  : high-pitched voices, laughing, crying, shouting (100-500Hz pitch, broad spectral spread)
  - CROWD      : adult voices / crowd noise (80-250Hz pitch, formant-heavy)
  - MUSIC      : tonal, repetitive spectral pattern
  - WIND/HVAC  : low-frequency continuous drone
  - QUIET      : below ambient threshold
  - UNKNOWN    : ambiguous noise

Only CHILDREN triggers the polite "cute kids" Hindi message.
CROWD triggers a generic "noisy environment" nudge.
MUSIC / WIND / QUIET are silently compensated (AGC boost).

Design goals:
  - Zero external dependencies (pure numpy on int16 PCM)
  - Runs in the audio callback thread — must complete in < 2ms per chunk
  - Rolling window of 2 seconds worth of chunks before firing a notification
  - Rate-limited: minimum 90 seconds between successive noise notifications
  - Thread-safe

Algorithm:
  1. Accumulate chunks into a 2-second ring buffer
  2. Every 50 chunks (~3s @16kHz/1024 blocksize) run a spectral analysis
  3. Features:
       - Centroid frequency  : children are high (1500-4000 Hz), adults lower
       - Spectral flatness   : music is tonal (low flatness), noise is flat
       - Energy in bands:
           sub-bass   0- 250 Hz  → HVAC
           bass       250-500 Hz → adult male voice fundamental
           mid-low    500-1.5kHz → adult female / children voice
           mid-high   1.5-4kHz   → children, laughter, crying
           high       4-8kHz     → consonants, hiss
       - Pitch estimate via autocorrelation over a 256-sample frame
  4. Classify:
       pitch > 300Hz + mid-high energy > 25% → CHILDREN
       pitch 80-300Hz + mid energy dominant  → CROWD
       flatness < 0.02 + tonal              → MUSIC
       sub-bass dominant                   → HVAC
       RMS < threshold                     → QUIET
"""

from __future__ import annotations

import time
import threading
from collections import deque
from typing import Optional

import numpy as np


# ── Constants ─────────────────────────────────────────────────────────────────
SAMPLE_RATE      = 16_000
CHUNK_SIZE       = 1_024
WINDOW_SECONDS   = 2.0
WINDOW_CHUNKS    = int(WINDOW_SECONDS * SAMPLE_RATE / CHUNK_SIZE)   # ~31 chunks
ANALYZE_EVERY    = 50      # run analysis every N chunks (~3.2s)
NOTIFY_COOLDOWN  = 300.0   # seconds between ambient noise notifications (5 mins)
LOW_VOICE_COOLDOWN = 180.0 # seconds between low-voice nudges (3 mins)
QUIET_RMS_THRESH = 100.0   # int16 RMS below this = ambient room silence / low noise
LOW_VOICE_RMS_LO = 100.0   # RMS above quiet but below this = very soft voice
LOW_VOICE_RMS_HI = 250.0   # RMS above this = comfortable listening level
LOW_VOICE_WINDOWS = 6      # consecutive low-voice analysis windows before alerting (~20s)
LOUD_SHOR_RMS_THRESH = 1100.0  # RMS threshold for genuine loud background disturbance ("loud shor")
LOUD_SHOR_WINDOWS    = 4       # consecutive loud windows (~13s sustained) before considering ambient alert
CHILDREN_PITCH_LO = 260    # Hz — lower bound for children fundamental
CHILDREN_PITCH_HI = 550    # Hz — upper bound (children shout high)
CHILD_MIDHIGH_RATIO = 0.28 # fraction of energy in 1.5-4 kHz band


class NoiseClassifier:
    """
    Accumulates PCM chunks and classifies the background noise type.
    Call `.feed(chunk_int16)` from the audio callback.
    Call `.get_event()` from the async loop to check for notifications.
    """

    QUIET    = "quiet"
    CHILDREN = "children"
    CROWD    = "crowd"
    MUSIC    = "music"
    HVAC     = "hvac"
    LOW_VOICE = "low_voice"
    UNKNOWN  = "unknown"

    def __init__(self, sr: int = SAMPLE_RATE):
        self._sr               = sr
        self._buf: deque       = deque(maxlen=WINDOW_CHUNKS)
        self._chunk_count      = 0
        self._lock             = threading.Lock()
        self._last_notify      = 0.0    # monotonic time of last ambient notification
        self._last_low_voice   = 0.0    # monotonic time of last low-voice notification
        self._pending_event: Optional[str] = None   # ambient noise event to report
        self._pending_low_voice: bool = False        # low-voice event pending
        self._last_class       = self.QUIET
        self._low_voice_streak = 0      # consecutive low-voice analysis windows
        self._loud_streak      = 0      # consecutive loud noise analysis windows

    # ── Public API ─────────────────────────────────────────────────────────────

    def feed(self, chunk: np.ndarray) -> None:
        """Feed a raw int16 mono chunk. Thread-safe. Must be fast (< 1ms)."""
        with self._lock:
            self._buf.append(chunk.flatten().astype(np.float32))
            self._chunk_count += 1
            if self._chunk_count % ANALYZE_EVERY == 0:
                self._analyze()

    def get_event(self) -> Optional[str]:
        """
        Returns the pending ambient noise event (CHILDREN/CROWD/…) if any.
        Rate-limited to NOTIFY_COOLDOWN seconds.
        """
        with self._lock:
            if self._pending_event is None:
                return None
            now = time.monotonic()
            if now - self._last_notify < NOTIFY_COOLDOWN:
                self._pending_event = None
                return None
            evt = self._pending_event
            self._pending_event = None
            self._last_notify   = now
            return evt

    def get_low_voice_event(self) -> bool:
        """
        Returns True if a low-voice event is pending and cooldown has passed.
        Separate cooldown (LOW_VOICE_COOLDOWN) from ambient events.
        """
        with self._lock:
            if not self._pending_low_voice:
                return False
            now = time.monotonic()
            if now - self._last_low_voice < LOW_VOICE_COOLDOWN:
                self._pending_low_voice = False
                return False
            self._pending_low_voice = False
            self._last_low_voice    = now
            return True

    def reset_cooldown(self) -> None:
        """Allow next notification immediately (e.g. user asked to reset)."""
        with self._lock:
            self._last_notify = 0.0

    def get_last_class(self) -> str:
        """Return the most recently classified noise category."""
        with self._lock:
            return self._last_class

    # ── Internal ───────────────────────────────────────────────────────────────

    def _analyze(self) -> None:
        """Run spectral analysis on the accumulated window. Called under lock."""
        if len(self._buf) < max(5, WINDOW_CHUNKS // 3):
            return                          # not enough data yet

        # Concatenate all buffered frames
        signal = np.concatenate(list(self._buf))
        rms    = float(np.sqrt(np.mean(signal ** 2)))

        # ── Low voice detection — before normalizing ──────────────────────
        # Only fire if RMS is in the "present but very quiet" range, meaning
        # the user IS speaking but Charlie can barely hear them.
        if LOW_VOICE_RMS_LO <= rms < LOW_VOICE_RMS_HI:
            self._low_voice_streak += 1
            if self._low_voice_streak >= LOW_VOICE_WINDOWS:
                self._pending_low_voice = True
                self._low_voice_streak  = 0   # reset after firing
        else:
            # Voice is either silent or loud enough — reset streak
            self._low_voice_streak = max(0, self._low_voice_streak - 1)

        if rms < QUIET_RMS_THRESH:
            self._last_class = self.QUIET
            return

        # Normalise
        sig_norm = signal / (np.max(np.abs(signal)) + 1e-9)

        # ── Spectral analysis ─────────────────────────────────────────────
        n_fft = min(4096, len(sig_norm))
        spec  = np.abs(np.fft.rfft(sig_norm[:n_fft]))
        freqs = np.fft.rfftfreq(n_fft, d=1.0 / self._sr)

        # Band energy fractions
        def _band_energy(lo: float, hi: float) -> float:
            mask = (freqs >= lo) & (freqs < hi)
            return float(spec[mask].sum())

        total_e  = float(spec.sum()) + 1e-9
        sub_bass = _band_energy(0,    250)  / total_e   # 0-250 Hz
        bass     = _band_energy(250,  500)  / total_e   # adult male fundamental
        mid_lo   = _band_energy(500,  1500) / total_e   # adult female / child low
        mid_hi   = _band_energy(1500, 4000) / total_e   # children high
        high_e   = _band_energy(4000, 8000) / total_e   # consonants, hiss

        # ── Pitch estimate via short-time autocorrelation ─────────────────
        # Use a 256-sample centre frame for speed
        frame_len = 256
        mid       = max(0, len(sig_norm) // 2 - frame_len // 2)
        frame     = sig_norm[mid: mid + frame_len]
        pitch_hz  = self._estimate_pitch(frame)

        # ── Spectral flatness (Wiener entropy) ────────────────────────────
        eps      = 1e-12
        flatness = float(
            np.exp(np.mean(np.log(spec + eps))) / (np.mean(spec + eps) + eps)
        )

        # ── Classification rules ──────────────────────────────────────────
        noise_class = self.UNKNOWN

        # CHILDREN: high pitch + significant energy in 1.5-4 kHz band
        if (CHILDREN_PITCH_LO <= pitch_hz <= CHILDREN_PITCH_HI and
                mid_hi >= CHILD_MIDHIGH_RATIO):
            noise_class = self.CHILDREN

        # Also catch children by very high energy even without clear pitch
        elif mid_hi >= 0.30 and high_e >= 0.15 and pitch_hz >= 220:
            noise_class = self.CHILDREN

        # CROWD: adult voices — lower pitch, bass+mid_lo dominant
        elif (80 <= pitch_hz < 250 and
              (bass + mid_lo) >= 0.35 and
              mid_hi < 0.20):
            noise_class = self.CROWD

        # MUSIC: tonal (low flatness), broad energy spread
        elif flatness < 0.04 and (bass + mid_lo + mid_hi) > 0.5:
            noise_class = self.MUSIC

        # HVAC / continuous drone: sub-bass dominant, very low flatness
        elif sub_bass >= 0.55 and flatness < 0.05:
            noise_class = self.HVAC

        # Default based on energy pattern
        else:
            if rms > 1200:
                noise_class = self.CROWD   # loud unclassified noise = generic crowd
            else:
                noise_class = self.UNKNOWN

        # ── Loud noise streak check ("loud shor") ────────────────────────
        # Only consider ambient alerts if sound is genuinely loud and sustained.
        if rms >= LOUD_SHOR_RMS_THRESH:
            self._loud_streak += 1
        else:
            self._loud_streak = max(0, self._loud_streak - 1)

        # Only fire events for genuine loud background noise (sustained over LOUD_SHOR_WINDOWS)
        if self._loud_streak >= LOUD_SHOR_WINDOWS and noise_class in (self.CHILDREN, self.CROWD):
            if noise_class != self._last_class:
                self._pending_event = noise_class
                self._loud_streak = 0
        self._last_class = noise_class

    @staticmethod
    def _estimate_pitch(frame: np.ndarray) -> float:
        """
        Estimate fundamental frequency using autocorrelation.
        Returns Hz, or 0 if no clear pitch found.
        """
        if len(frame) < 32:
            return 0.0
        # Autocorrelation via FFT
        n     = len(frame)
        fft   = np.fft.rfft(frame, n=2*n)
        acf   = np.fft.irfft(fft * np.conj(fft))[:n]
        acf   = acf / (acf[0] + 1e-9)  # normalize

        # Search for first peak after initial zero-crossing
        # Pitch range 80-600 Hz → lag range
        sr = SAMPLE_RATE
        lo_lag = max(1, int(sr / 600))
        hi_lag = int(sr / 80)
        hi_lag = min(hi_lag, n - 1)

        if lo_lag >= hi_lag:
            return 0.0

        window = acf[lo_lag: hi_lag]
        if len(window) == 0:
            return 0.0

        peak_idx = int(np.argmax(window)) + lo_lag
        peak_val = float(acf[peak_idx])

        if peak_val < 0.3:    # not enough periodicity
            return 0.0

        return float(sr) / peak_idx


# ── Notification messages ─────────────────────────────────────────────────────

def children_noise_message(lang: str = "en") -> str:
    """Polite, professional message for high-frequency loud background noise."""
    if lang in ("hi", "hinglish"):
        return (
            "Aapke background mein kaafi shor aa raha hai. "
            "Agar sambhav ho, toh kripya thoda shaant jagah se baat karein taaki communication bilkul saaf rahe."
        )
    return (
        "There is noticeable background noise in your environment. "
        "If possible, please move to a quieter space or speak closer to the microphone for clear audio."
    )


def crowd_noise_message(lang: str = "en") -> str:
    """Polite, professional message for loud background noise."""
    if lang in ("hi", "hinglish"):
        return (
            "Aapke aas-paas kaafi shor aa raha hai. "
            "Agar sambhav ho, toh kripya thoda shaant jagah se baat karein."
        )
    return (
        "There seems to be significant ambient noise around you. "
        "If possible, moving to a quieter area will ensure clear audio."
    )


def low_voice_message(lang: str = "en") -> str:
    """Gentle, professional nudge when user's voice is consistently too soft."""
    if lang in ("hi", "hinglish"):
        return (
            "Aapki awaaz thodi dheemi aa rahi hai. "
            "Kripya microphone ke thoda paas aakar bolen taaki baat saaf sunai de sake."
        )
    return (
        "Your voice seems a bit faint. "
        "Please speak slightly closer to the microphone for optimal clarity."
    )


# ── Singleton ─────────────────────────────────────────────────────────────────
_classifier: Optional[NoiseClassifier] = None
_nc_lock = threading.Lock()


def get_noise_classifier() -> NoiseClassifier:
    global _classifier
    with _nc_lock:
        if _classifier is None:
            _classifier = NoiseClassifier()
        return _classifier


def reset_noise_classifier() -> None:
    global _classifier
    with _nc_lock:
        _classifier = NoiseClassifier()
