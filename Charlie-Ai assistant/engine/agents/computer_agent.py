"""engine/agents/computer_agent.py — Windows Computer Control Specialist.

Implements the OBSERVE -> LOCATE -> ACT -> OBSERVE -> VERIFY loop.
Prefers UI Automation, window handles, and keyboard shortcuts over raw mouse coordinates.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

from engine.agents.base import BaseAgent


class ComputerAgent(BaseAgent):
    """Specialist agent for Windows desktop automation."""

    def can_handle(self, user_intent: str) -> bool:
        low = user_intent.lower()
        return any(w in low for w in ("window", "click", "open app", "minimize", "maximize", "focus", "screenshot", "type text"))

    def get_desktop_summary(self) -> Dict[str, Any]:
        """Inspect visible windows and foreground application."""
        if sys.platform != "win32":
            return {"platform": sys.platform, "windows": []}

        import ctypes
        user32 = ctypes.windll.user32

        # Foreground window
        fg_hwnd = user32.GetForegroundWindow()
        fg_title = ""
        if fg_hwnd:
            length = user32.GetWindowTextLengthW(fg_hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(fg_hwnd, buff, length + 1)
            fg_title = buff.value

        return {
            "platform": "windows",
            "active_window": fg_title or "Unknown",
        }
