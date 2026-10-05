# actions/media_control.py
"""
Media & System Volume Controller for Charlie.

Voice commands:
  "Play music" / "Pause music"
  "Mute" / "Unmute"
  "Volume up" / "Volume down"
  "Next song" / "Previous song"
  "Stop playback"
"""

from __future__ import annotations

import ctypes
import platform
import time
from typing import Any, Dict, Optional

TOOL = {
    "name": "media_control",
    "description": (
        "Controls system audio and media playback (Spotify, YouTube, browser, Windows media). "
        "Supports play/pause, volume up/down, mute, next/previous track. "
        "Trigger on: 'play music', 'pause', 'mute', 'unmute', 'volume up', 'volume down', "
        "'next track', 'skip song', 'previous song', 'louder', 'quieter'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["play_pause", "volume_up", "volume_down", "mute", "next", "previous", "stop"],
                "description": "Media action to perform",
            },
            "steps": {
                "type": "integer",
                "description": "Number of volume steps to increase or decrease (default 5)",
            },
        },
        "required": ["action"],
    },
}

# Windows Virtual-Key Codes for Media
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002


def _send_vk(vk_code: int) -> None:
    if platform.system() == "Windows":
        try:
            user32 = ctypes.windll.user32
            user32.keybd_event(vk_code, 0, 0, 0)
            time.sleep(0.02)
            user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
        except Exception:
            pass


def execute(action: str = "play_pause", steps: int = 5, **kwargs: Any) -> str:
    """Execute media and volume control."""
    act = action.lower()
    step_count = max(1, min(20, steps))

    if act in ("play_pause", "play", "pause"):
        _send_vk(VK_MEDIA_PLAY_PAUSE)
        return "⏯️ Playback toggled (Play/Pause)."

    if act in ("mute", "unmute"):
        _send_vk(VK_VOLUME_MUTE)
        return "🔇 Volume mute toggled."

    if act in ("volume_up", "louder", "up"):
        for _ in range(step_count):
            _send_vk(VK_VOLUME_UP)
            time.sleep(0.01)
        return f"🔊 Volume increased by {step_count} steps."

    if act in ("volume_down", "quieter", "softer", "down"):
        for _ in range(step_count):
            _send_vk(VK_VOLUME_DOWN)
            time.sleep(0.01)
        return f"🔉 Volume decreased by {step_count} steps."

    if act in ("next", "skip"):
        _send_vk(VK_MEDIA_NEXT_TRACK)
        return "⏭️ Skipped to next track."

    if act in ("previous", "prev", "back"):
        _send_vk(VK_MEDIA_PREV_TRACK)
        return "⏮️ Returned to previous track."

    if act == "stop":
        _send_vk(VK_MEDIA_STOP)
        return "⏹️ Media playback stopped."

    return "Unknown media action. Say 'play', 'pause', 'mute', 'volume up', 'volume down', or 'next track'."
