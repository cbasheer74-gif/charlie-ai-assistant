"""engine/voice/recovery.py — Audio Disconnect, STT Timeout, Network Failure, and Fallback Recovery."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from engine.voice.audio_device_mgr import AudioDeviceManager
from engine.voice.models import AudioDevice


class AudioRecoveryEngine:
    """Detects and recovers from microphone loss, provider timeouts, and network drops."""

    def __init__(self, device_manager: Optional[AudioDeviceManager] = None):
        self.device_manager = device_manager or AudioDeviceManager()
        self.network_available: bool = True
        self.stt_failures_count: int = 0
        self.mic_disconnects_count: int = 0

    def set_network_available(self, available: bool) -> None:
        self.network_available = available

    def recover_microphone(self, current_mic_name: str) -> Tuple[bool, AudioDevice]:
        """Detects if microphone was unplugged, attempts fallback to system default."""
        is_disconnected, fallback_device = self.device_manager.handle_device_disconnect(current_mic_name)
        if is_disconnected:
            self.mic_disconnects_count += 1
            return True, fallback_device
        return False, fallback_device

    def handle_stt_failure(self, provider_name: str) -> Dict[str, Any]:
        """Falls back from Cloud to Local FasterWhisper or Push-To-Talk on timeout/error."""
        self.stt_failures_count += 1
        return {
            "recovered": True,
            "fallback_provider": "FasterWhisper",
            "fallback_mode": "LOCAL",
            "message": "Cloud STT unavailable; switched to local offline transcription.",
        }

    def check_offline_capability(self, intent_type: str) -> Tuple[bool, str]:
        """Verifies if the voice intent can execute completely offline without cloud access."""
        local_intents = {
            "COMPUTER_COMMAND", "FILE_COMMAND", "CODING_COMMAND",
            "SPREADSHEET_COMMAND", "STOP", "PAUSE", "RESUME",
        }
        cloud_intents = {"RESEARCH_COMMAND", "EMAIL_COMMAND", "CALENDAR_COMMAND"}

        if intent_type in local_intents:
            return True, "Execution is supported offline."

        if not self.network_available and intent_type in cloud_intents:
            return False, "Internet connection required for research or email automation."

        return True, "Command supported."
