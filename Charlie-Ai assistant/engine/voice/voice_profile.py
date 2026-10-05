# engine/voice/voice_profile.py
"""
Voice Profile Manager — stores acoustic fingerprints per user so Charlie
can "recognize" a returning voice and greet by name automatically.

Implementation:
  - Uses simple MFCC-based cosine similarity (no heavy deps beyond numpy).
  - If numpy-based comparison score >= MATCH_THRESHOLD → identity confirmed.
  - Profiles stored in config/voice_profiles.json as base64-encoded numpy arrays.
  - Falls back gracefully if audio is too short or numpy unavailable.

Usage:
  mgr = VoiceProfileManager()
  mgr.enroll(user_id="anees", user_name="Anees Chaudhary", audio=np_array)
  result = mgr.identify(audio=np_array)  # → {"user_id": "anees", "user_name": "...", "score": 0.92}
"""

from __future__ import annotations

import base64
import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np


# ── Config path ────────────────────────────────────────────────────────────────
def _profiles_file() -> Path:
    import sys
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).resolve().parent.parent.parent
    return base / "config" / "voice_profiles.json"


# ── Acoustic feature extraction ────────────────────────────────────────────────
MATCH_THRESHOLD = 0.82   # cosine similarity threshold for identity match
MIN_AUDIO_SAMPLES = 4000  # ~0.25s at 16kHz — less than this is too short


def _extract_features(audio: np.ndarray, n_mfcc: int = 20, sr: int = 16000) -> Optional[np.ndarray]:
    """
    Lightweight MFCC-like feature vector from raw audio.
    No external library required — uses FFT-based approximation.
    Returns a 1-D normalized float32 vector, or None if audio too short.
    """
    if audio is None or len(audio) < MIN_AUDIO_SAMPLES:
        return None

    # Ensure float32 mono
    a = audio.flatten().astype(np.float32)
    a = a / (np.max(np.abs(a)) + 1e-9)

    # Frame the signal
    frame_len = min(512, len(a) // 4)
    hop       = frame_len // 2
    frames    = [a[i:i+frame_len] for i in range(0, len(a)-frame_len, hop)]
    if not frames:
        return None

    # Compute energy per band using FFT (log-spaced, n_mfcc bands)
    spectra = []
    for f in frames:
        fft_mag = np.abs(np.fft.rfft(f))
        spectra.append(fft_mag)
    spec_matrix = np.stack(spectra)                     # (n_frames, frame_len//2+1)
    mean_spec   = spec_matrix.mean(axis=0)              # average spectrum

    # Log-mel-like binning into n_mfcc bands
    n_fft  = mean_spec.shape[0]
    bins   = np.logspace(0, np.log10(n_fft), n_mfcc + 1).astype(int)
    bins   = np.clip(bins, 0, n_fft - 1)
    bands  = []
    for i in range(n_mfcc):
        lo, hi = bins[i], bins[i+1]
        val = mean_spec[lo:hi+1].mean() if lo < hi else mean_spec[lo]
        bands.append(np.log1p(val))

    vec = np.array(bands, dtype=np.float32)
    norm = np.linalg.norm(vec)
    return vec / (norm + 1e-9)


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    dot = float(np.dot(a, b))
    return dot  # both already unit-normalized


def _vec_to_b64(vec: np.ndarray) -> str:
    return base64.b64encode(vec.tobytes()).decode()


def _b64_to_vec(s: str, n_mfcc: int = 20) -> np.ndarray:
    data = base64.b64decode(s.encode())
    return np.frombuffer(data, dtype=np.float32)


# ── Profile store ──────────────────────────────────────────────────────────────

class VoiceProfileManager:
    """Thread-safe voice profile enroll + identify."""

    _lock = threading.Lock()

    def __init__(self):
        self._file = _profiles_file()

    def _load(self) -> Dict[str, Any]:
        try:
            if self._file.exists():
                return json.loads(self._file.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save(self, data: Dict[str, Any]) -> None:
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            self._file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def enroll(self, user_id: str, user_name: str, audio: np.ndarray) -> bool:
        """
        Extracts acoustic fingerprint from `audio` and saves it for user_id.
        Returns True on success.
        """
        vec = _extract_features(audio)
        if vec is None:
            return False
        with self._lock:
            data = self._load()
            data[user_id] = {
                "user_name":  user_name,
                "fingerprint": _vec_to_b64(vec),
            }
            self._save(data)
        return True

    def identify(self, audio: np.ndarray) -> Optional[Dict[str, Any]]:
        """
        Compare audio against all enrolled voices.
        Returns {"user_id": ..., "user_name": ..., "score": ...} or None.
        """
        vec = _extract_features(audio)
        if vec is None:
            return None
        with self._lock:
            data = self._load()

        best_uid   = None
        best_name  = None
        best_score = 0.0

        for uid, profile in data.items():
            try:
                stored = _b64_to_vec(profile["fingerprint"])
                score  = _cosine_sim(vec, stored)
                if score > best_score:
                    best_score = score
                    best_uid   = uid
                    best_name  = profile.get("user_name", uid)
            except Exception:
                continue

        if best_score >= MATCH_THRESHOLD and best_uid:
            return {
                "user_id":   best_uid,
                "user_name": best_name,
                "score":     round(best_score, 3),
            }
        return None

    def get_profile(self, user_id: str) -> Optional[Dict[str, str]]:
        with self._lock:
            data = self._load()
            return data.get(user_id)

    def list_profiles(self) -> list[str]:
        with self._lock:
            return list(self._load().keys())

    def delete_profile(self, user_id: str) -> bool:
        with self._lock:
            data = self._load()
            if user_id in data:
                del data[user_id]
                self._save(data)
                return True
            return False


# Singleton
_voice_profile_mgr: Optional[VoiceProfileManager] = None
_vpm_lock = threading.Lock()


def get_voice_profile_manager() -> VoiceProfileManager:
    global _voice_profile_mgr
    with _vpm_lock:
        if _voice_profile_mgr is None:
            _voice_profile_mgr = VoiceProfileManager()
        return _voice_profile_mgr
