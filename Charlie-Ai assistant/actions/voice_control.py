"""actions/voice_control.py — CHARLIE Active Voice Runtime Control Action.

Bridges tool-calling to the real active CharlieLive voice session, allowing
safe control of microphone mute, sleep/wake states, interruption, reconnect,
and voice profile switching without spawning mock audio engines.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger("charlie.actions.voice_control")


def voice_control(parameters: dict, **_unused) -> str:
    """Entry point action for controlling CHARLIE's active voice session and microphone."""
    params = parameters or {}
    action = str(params.get("action") or "status").strip().lower()

    from core.runtime_voice_control import get_voice_runtime

    runtime = get_voice_runtime()
    if runtime is None:
        return "Error: Charlie active voice runtime is not registered or not currently running."

    try:
        # 1. Status inspection
        if action == "status":
            ui = getattr(runtime, "ui", None)
            state = getattr(ui, "state", "READY")
            muted = bool(getattr(ui, "muted", False))
            awake = bool(getattr(runtime, "_awake", True))
            wake_enabled = bool(getattr(runtime, "_wake_enabled", False))
            session_connected = bool(getattr(runtime, "session", None) is not None)
            return (
                f"### CHARLIE Active Voice Runtime Status:\n"
                f"- **State**: {state}\n"
                f"- **Awake**: {'YES' if awake else 'NO (SLEEPING)'}\n"
                f"- **Microphone**: {'MUTED' if muted else 'ACTIVE'}\n"
                f"- **Wake Word**: {'ENABLED' if wake_enabled else 'DISABLED'}\n"
                f"- **Live Session**: {'CONNECTED' if session_connected else 'STANDBY'}\n"
            )

        # 2. Mute microphone
        if action == "mute":
            ui = getattr(runtime, "ui", None)
            if ui is not None:
                ui.muted = True
                return "Microphone has been muted. Voice streaming paused."
            return "Error: Unable to mute microphone on active runtime."

        # 3. Unmute microphone
        if action == "unmute":
            ui = getattr(runtime, "ui", None)
            if ui is not None:
                ui.muted = False
                return "Microphone unmuted. Voice listening resumed."
            return "Error: Unable to unmute microphone on active runtime."

        # 4. Interrupt speech / Emergency stop
        if action in ("interrupt", "emergency_stop", "stop"):
            if hasattr(runtime, "interrupt"):
                runtime.interrupt()
                return "Speech interrupted and audio playback buffers cleared."
            return "Error: Active runtime does not support speech interruption."

        # 5. Wake up assistant
        if action in ("wake", "resume"):
            if hasattr(runtime, "wake"):
                runtime.wake(reason="voice_control action")
                return "CHARLIE is now awake and listening."
            return "Error: Active runtime does not support wake."

        # 6. Put assistant to sleep
        if action in ("sleep", "pause"):
            if hasattr(runtime, "sleep"):
                runtime.sleep(reason="voice_control action")
                return "CHARLIE has been put to sleep. Say 'Hey Charlie' to wake."
            return "Error: Active runtime does not support sleep."

        # 7. Reconnect / Restart live session
        if action in ("reconnect", "restart"):
            if hasattr(runtime, "request_reconnect"):
                runtime.request_reconnect(keep_context=True, reason="voice_control action")
                return "Reconnecting voice session while preserving conversation context."
            return "Error: Active runtime does not support reconnect."

        # 8. Change voice profile
        if action in ("set_voice", "change_voice"):
            voice_name = str(params.get("voice") or params.get("voice_name") or "").strip()
            if not voice_name:
                return "Please specify a voice name to set."
            from memory.config_manager import save_voice
            save_voice(voice_name)
            if hasattr(runtime, "_on_voice_change"):
                runtime._on_voice_change()
            return f"Voice changed to '{voice_name}'. Session is reconnecting with new voice."

        # 9. Toggle wake word detection
        if action in ("toggle_wake_word", "enable_wake_word"):
            enabled = bool(params.get("enabled", True))
            from memory.config_manager import save_wake_word_enabled
            save_wake_word_enabled(enabled)
            if hasattr(runtime, "_wake_enabled"):
                runtime._wake_enabled = enabled
                if enabled and hasattr(runtime, "_ensure_wake_detector"):
                    runtime._ensure_wake_detector()
                elif not enabled and hasattr(runtime, "wake"):
                    runtime.wake(reason="wake word disabled")
            return f"Wake word listener {'enabled' if enabled else 'disabled'}."

        # 10. Unsupported legacy actions
        if action in ("test_microphone", "set_microphone", "process_command", "simulate_speech"):
            return f"Command '{action}' is unsupported by active Gemini Live runtime."

        return f"Unknown voice action: {action}"

    except Exception as e:
        logger.warning("[voice_control] Action execution failed: %s", type(e).__name__)
        return f"Voice Control error: {str(e)}"


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "voice_control",
    "description": (
        "Controls CHARLIE's active voice session, microphone mute state, wake/sleep modes, "
        "speech interruption, and session reconnection."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "Action to perform: 'status', 'mute', 'unmute', 'interrupt', 'sleep', "
                    "'wake', 'reconnect', 'set_voice', 'toggle_wake_word'."
                ),
            },
            "voice": {
                "type": "STRING",
                "description": "Voice name to apply when action is 'set_voice'.",
            },
            "enabled": {
                "type": "BOOLEAN",
                "description": "Boolean flag when action is 'toggle_wake_word'.",
            },
        },
        "required": ["action"],
    },
    "handler": voice_control,
}
