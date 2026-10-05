# actions/voice_speed.py
"""
Voice Speed & Audio Customizer for Charlie.

Voice commands:
  "Speak faster" / "Talk faster"
  "Speak slower" / "Slow down"
  "Talk normally" / "Reset voice speed"
  "Set voice speed to 1.2"
  "Quiet mode" / "Silent mode"
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

TOOL = {
    "name": "voice_speed",
    "description": (
        "Adjusts Charlie's voice speaking speed (faster, slower, reset), volume, or quiet mode. "
        "Trigger on: 'speak faster', 'talk faster', 'speak slower', 'slow down', "
        "'talk normally', 'reset voice speed', 'quiet mode', 'voice volume'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["faster", "slower", "reset", "set", "status", "toggle_quiet"],
                "description": "Voice speed adjustment action",
            },
            "speed_rate": {
                "type": "number",
                "description": "Exact speed multiplier (0.5 to 2.0)",
            },
        },
        "required": ["action"],
    },
}

from core.app_paths import get_config_dir

_CONFIG_PATH = get_config_dir() / "voice_settings.json"


def _load_settings() -> Dict[str, Any]:
    try:
        if _CONFIG_PATH.exists():
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"voice_speed": 1.0, "voice_volume": 1.0, "quiet_mode": False}


def _save_settings(data: Dict[str, Any]) -> None:
    try:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def execute(action: str = "status", speed_rate: Optional[float] = None, **kwargs: Any) -> str:
    """Execute voice speed and settings adjustments."""
    settings = _load_settings()
    current_speed = float(settings.get("voice_speed", 1.0))
    act = action.lower()

    if act in ("faster", "speed_up"):
        new_speed = min(2.0, round(current_speed + 0.2, 2))
        settings["voice_speed"] = new_speed
        _save_settings(settings)
        return f"⚡ Voice speed increased to {new_speed}x. Charlie will speak faster."

    if act in ("slower", "slow_down"):
        new_speed = max(0.6, round(current_speed - 0.2, 2))
        settings["voice_speed"] = new_speed
        _save_settings(settings)
        return f"🐢 Voice speed reduced to {new_speed}x. Charlie will speak more calmly and deliberately."

    if act in ("reset", "normal", "default"):
        settings["voice_speed"] = 1.0
        _save_settings(settings)
        return "🎙️ Voice speed reset to normal (1.0x)."

    if act == "set" and speed_rate is not None:
        clamped = max(0.5, min(2.0, round(float(speed_rate), 2)))
        settings["voice_speed"] = clamped
        _save_settings(settings)
        return f"🎙️ Voice speed set to {clamped}x."

    if act in ("toggle_quiet", "quiet"):
        quiet = not settings.get("quiet_mode", False)
        settings["quiet_mode"] = quiet
        _save_settings(settings)
        state_str = "ON (Voice replies muted; visual only)" if quiet else "OFF (Voice replies active)"
        return f"🤫 Quiet Mode is now {state_str}."

    return (
        f"🎙️ Current Voice Speed: **{current_speed}x** | "
        f"Quiet Mode: **{'Enabled' if settings.get('quiet_mode') else 'Disabled'}**.\n"
        f"Say **'speak faster'**, **'speak slower'**, or **'reset voice speed'** to adjust."
    )
