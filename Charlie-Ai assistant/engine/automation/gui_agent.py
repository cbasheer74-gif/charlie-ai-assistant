"""engine/automation/gui_agent.py — Autonomous OS GUI & Computer-Use Agent for CHARLIE.

Provides direct desktop execution:
- Native Win32 / ctypes coordinate mouse and keyboard control.
- Screen element localization and clicking.
- Guardrails: Failsafe boundaries, command blacklists, execution audit logs.
- Window management (focus, minimize, maximize).
"""

from __future__ import annotations

import ctypes
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("charlie.gui_agent")

# Win32 Mouse event flags
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040

# Win32 Key event flags
KEYEVENTF_KEYUP = 0x0002


@dataclass
class GUIActionRecord:
    action_type: str
    params: Dict[str, Any]
    success: bool
    error_msg: str = ""
    timestamp: float = field(default_factory=time.time)


class GUIDesktopAutomator:
    """Safely executes autonomous GUI interactions, mouse movements, clicks, and text typing."""

    DANGEROUS_COMMANDS = [
        re.compile(r"\b(format\s+[a-z]:|rmdir\s+/s\s+/q|del\s+/f\s+/s\s+/q\s+c:\\)\b", re.I),
        re.compile(r"\b(reg\s+delete|vssadmin\s+delete\s+shadows)\b", re.I),
    ]

    def __init__(self, failsafe_enabled: bool = True):
        self.failsafe_enabled = failsafe_enabled
        self.action_history: List[GUIActionRecord] = []
        self._emergency_kill: bool = False

    def emergency_stop(self) -> None:
        """Immediately halts all GUI actions."""
        self._emergency_kill = True
        logger.warning("Emergency kill switch engaged in GUIDesktopAutomator!")

    def reset_kill_switch(self) -> None:
        self._emergency_kill = False

    def get_screen_size(self) -> Tuple[int, int]:
        """Returns (width, height) of primary screen."""
        try:
            user32 = ctypes.windll.user32
            return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        except Exception:
            return 1920, 1080

    def get_cursor_pos(self) -> Tuple[int, int]:
        """Returns current mouse position."""
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        pt = POINT()
        try:
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            return pt.x, pt.y
        except Exception:
            return 0, 0

    def _check_failsafe(self) -> None:
        if self._emergency_kill:
            raise RuntimeError("GUI action aborted: Emergency kill switch is active.")
        if self.failsafe_enabled:
            x, y = self.get_cursor_pos()
            # If user manually pushed mouse to top-left corner (0,0), abort immediately
            if x <= 5 and y <= 5:
                self.emergency_stop()
                raise RuntimeError("GUI action aborted: Failsafe triggered by cursor in top-left corner.")

    def move_mouse(self, x: int, y: int) -> bool:
        """Moves cursor to (x, y) with boundary clamping."""
        self._check_failsafe()
        sw, sh = self.get_screen_size()
        cx = max(0, min(sw - 1, int(x)))
        cy = max(0, min(sh - 1, int(y)))
        try:
            ctypes.windll.user32.SetCursorPos(cx, cy)
            self.action_history.append(GUIActionRecord("move", {"x": cx, "y": cy}, True))
            return True
        except Exception as e:
            self.action_history.append(GUIActionRecord("move", {"x": cx, "y": cy}, False, str(e)))
            return False

    def click(self, x: Optional[int] = None, y: Optional[int] = None, button: str = "left") -> bool:
        """Clicks at (x, y) or at current cursor position."""
        self._check_failsafe()
        if x is not None and y is not None:
            self.move_mouse(x, y)

        time.sleep(0.02)
        try:
            user32 = ctypes.windll.user32
            if button.lower() == "right":
                user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
                time.sleep(0.01)
                user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            elif button.lower() == "middle":
                user32.mouse_event(MOUSEEVENTF_MIDDLEDOWN, 0, 0, 0, 0)
                time.sleep(0.01)
                user32.mouse_event(MOUSEEVENTF_MIDDLEUP, 0, 0, 0, 0)
            else:
                user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                time.sleep(0.01)
                user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

            self.action_history.append(GUIActionRecord("click", {"x": x, "y": y, "button": button}, True))
            return True
        except Exception as e:
            self.action_history.append(GUIActionRecord("click", {"x": x, "y": y, "button": button}, False, str(e)))
            return False

    def double_click(self, x: Optional[int] = None, y: Optional[int] = None) -> bool:
        """Performs a double click."""
        if not self.click(x, y, button="left"):
            return False
        time.sleep(0.06)
        return self.click(x, y, button="left")

    def type_text(self, text: str, delay: float = 0.01) -> bool:
        """Types unicode string into active focused control."""
        self._check_failsafe()
        if not text:
            return True

        # Safety check against dangerous terminal commands
        for pat in self.DANGEROUS_COMMANDS:
            if pat.search(text):
                logger.error("Blocked dangerous text typing: %s", text)
                self.action_history.append(GUIActionRecord("type_text", {"text": text}, False, "Security Block: Destructive command detected."))
                return False

        try:
            # Prefer pyautogui if present for clean cross-character keycodes
            try:
                import pyautogui
                pyautogui.write(text, interval=delay)
                self.action_history.append(GUIActionRecord("type_text", {"length": len(text)}, True))
                return True
            except ImportError:
                pass

            # Win32 fallback via SendInput / SendKeys or clipboard paste
            import win32api  # type: ignore
            import win32con  # type: ignore
            for char in text:
                vk = win32api.VkKeyScan(char)
                win32api.keybd_event(vk & 0xFF, 0, 0, 0)
                win32api.keybd_event(vk & 0xFF, 0, win32con.KEYEVENTF_KEYUP, 0)
                time.sleep(delay)
            self.action_history.append(GUIActionRecord("type_text", {"length": len(text)}, True))
            return True
        except Exception as e:
            self.action_history.append(GUIActionRecord("type_text", {"text": text}, False, str(e)))
            return False

    def press_key(self, key_name: str) -> bool:
        """Presses a single functional key (e.g. 'enter', 'tab', 'esc', 'space')."""
        self._check_failsafe()
        try:
            import pyautogui
            pyautogui.press(key_name)
            self.action_history.append(GUIActionRecord("press_key", {"key": key_name}, True))
            return True
        except Exception as e:
            self.action_history.append(GUIActionRecord("press_key", {"key": key_name}, False, str(e)))
            return False

    def focus_window_by_title(self, partial_title: str) -> bool:
        """Brings a window matching partial title to foreground."""
        try:
            import win32gui  # type: ignore
            import win32con  # type: ignore

            def enum_handler(hwnd, results):
                if win32gui.IsWindowVisible(hwnd):
                    text = win32gui.GetWindowText(hwnd)
                    if partial_title.lower() in text.lower():
                        results.append(hwnd)

            matches = []
            win32gui.EnumWindows(enum_handler, matches)
            if matches:
                target_hwnd = matches[0]
                win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(target_hwnd)
                self.action_history.append(GUIActionRecord("focus_window", {"title": partial_title}, True))
                return True
        except Exception as e:
            self.action_history.append(GUIActionRecord("focus_window", {"title": partial_title}, False, str(e)))
        return False

    def get_action_audit_log(self) -> List[Dict[str, Any]]:
        return [
            {
                "action": rec.action_type,
                "params": rec.params,
                "success": rec.success,
                "error": rec.error_msg,
                "time": rec.timestamp,
            }
            for rec in self.action_history
        ]


# Singleton
_gui_agent: Optional[GUIDesktopAutomator] = None


def get_gui_automator() -> GUIDesktopAutomator:
    global _gui_agent
    if _gui_agent is None:
        _gui_agent = GUIDesktopAutomator()
    return _gui_agent
