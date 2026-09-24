"""engine/voice/audio_device_mgr.py — Audio Device Management, Discovery, and Disconnect Recovery."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from engine.voice.models import AudioDevice


class AudioDeviceManager:
    """Manages input/output audio devices, preferred microphone resolution, and recovery."""

    def __init__(self, config_path: Optional[Path | str] = None):
        if config_path:
            self.config_path = Path(config_path).resolve()
        else:
            base_dir = Path(__file__).resolve().parent.parent.parent
            self.config_path = base_dir / "config" / "audio_settings.json"

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self._preferred_mic_name: str = ""
        self._mock_devices: Optional[List[AudioDevice]] = None
        self._load_preferences()

    def _load_preferences(self) -> None:
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
                self._preferred_mic_name = data.get("preferred_microphone", "")
            except Exception:
                self._preferred_mic_name = ""

    def save_preferences(self, preferred_mic: str) -> None:
        self._preferred_mic_name = preferred_mic
        try:
            payload = {"preferred_microphone": preferred_mic}
            self.config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            pass

    def set_mock_devices(self, devices: List[AudioDevice]) -> None:
        """Testing hook for deterministic offline test suites."""
        self._mock_devices = devices

    def list_microphones(self) -> List[AudioDevice]:
        """Enumerate available audio input devices (microphones)."""
        if self._mock_devices is not None:
            return list(self._mock_devices)

        mics: List[AudioDevice] = []
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            default_input_idx = sd.default.device[0]

            seen_names = set()
            for idx, dev in enumerate(devices):
                if dev.get("max_input_channels", 0) > 0:
                    name = str(dev.get("name", f"Microphone {idx}")).strip()
                    if name in seen_names or "Mapper" in name or "Primary" in name:
                        continue
                    seen_names.add(name)
                    mics.append(
                        AudioDevice(
                            name=name,
                            index=idx,
                            channels=int(dev.get("max_input_channels", 1)),
                            sample_rate=int(dev.get("default_samplerate", 16000)),
                            is_default=(idx == default_input_idx),
                        )
                    )
        except Exception:
            # Fallback default microphone representation
            mics = [AudioDevice(name="System Default Microphone", index=0, is_default=True)]

        return mics

    def get_selected_microphone(self) -> AudioDevice:
        """Resolves preferred microphone, or falls back to system default or first available."""
        mics = self.list_microphones()
        if not mics:
            return AudioDevice(name="No Microphone Found", index=-1)

        if self._preferred_mic_name:
            for m in mics:
                if self._preferred_mic_name.lower() in m.name.lower():
                    return m

        for m in mics:
            if m.is_default:
                return m

        return mics[0]

    def test_microphone_level(self, device: Optional[AudioDevice] = None, duration_sec: float = 0.5) -> Tuple[bool, float]:
        """Samples the microphone briefly to test level and connectivity."""
        target = device or self.get_selected_microphone()
        if target.index < 0:
            return False, 0.0

        if self._mock_devices is not None:
            return True, 0.25

        try:
            import sounddevice as sd
            import numpy as np

            frames = int(target.sample_rate * duration_sec)
            recording = sd.rec(
                frames,
                samplerate=target.sample_rate,
                channels=1,
                device=target.index,
                dtype="float32",
                blocking=True,
            )
            rms = float(np.sqrt(np.mean(recording ** 2)))
            return True, rms
        except Exception:
            return False, 0.0

    def handle_device_disconnect(self, current_device_name: str) -> Tuple[bool, AudioDevice]:
        """Detects if the active device was lost, and automatically switches to fallback."""
        mics = self.list_microphones()
        available_names = [m.name.lower() for m in mics]

        if current_device_name.lower() not in available_names:
            fallback = self.get_selected_microphone()
            return True, fallback

        for m in mics:
            if m.name.lower() == current_device_name.lower():
                return False, m

        return False, mics[0] if mics else AudioDevice(name="None", index=-1)
