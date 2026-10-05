"""
actions/desktop_macros.py
Autonomous desktop automation macros for window snapping, workspace layouts,
and quick multi-application orchestration.
"""
from __future__ import annotations

import subprocess
import time
from typing import Optional


class DesktopMacroEngine:
    """Automates Windows desktop window layouts and task workflows."""

    @staticmethod
    def snap_active_window(direction: str) -> bool:
        """
        Snaps the active window using Windows Key shortcuts or win32 API.
        direction: 'left', 'right', 'up' (maximize), 'down' (restore/minimize)
        """
        dir_lower = direction.strip().lower()
        key_map = {
            "left": "Left",
            "right": "Right",
            "up": "Up",
            "maximize": "Up",
            "down": "Down",
            "restore": "Down",
        }
        key = key_map.get(dir_lower, "Left")

        # Use PowerShell SendKeys for reliable, zero-dependency window snapping
        ps_cmd = f"""
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.SendKeys]::SendWait("^%({key})")
        """
        try:
            # Send Win + Arrow via PowerShell
            win_arrow_script = f"""
            $wscript = New-Object -ComObject Wscript.Shell
            $wscript.SendKeys('#{{{key}}}')
            """
            subprocess.run(["powershell", "-NoProfile", "-Command", win_arrow_script],
                           capture_output=True, timeout=2)
            return True
        except Exception:
            return False

    @staticmethod
    def setup_workspace(mode: str) -> dict[str, str]:
        """
        Launches and tiles preset workspaces.
        Modes: 'dev', 'research', 'focus'
        """
        mode_clean = mode.strip().lower()
        if mode_clean in ("dev", "developer", "coding"):
            # Launch / focus terminal & VS Code
            try:
                subprocess.Popen(["cmd.exe", "/c", "start", "wt"], shell=True)
                subprocess.Popen(["cmd.exe", "/c", "code", "."], shell=True)
                return {"status": "success", "mode": "dev", "message": "Development workspace launched (VS Code + Terminal)."}
            except Exception as e:
                return {"status": "error", "error": str(e)}

        elif mode_clean in ("research", "study"):
            try:
                subprocess.Popen(["cmd.exe", "/c", "start", "msedge"], shell=True)
                return {"status": "success", "mode": "research", "message": "Research workspace arranged."}
            except Exception as e:
                return {"status": "error", "error": str(e)}

        elif mode_clean in ("focus", "zen"):
            # Minimize all except foreground
            try:
                script = """
                $wscript = New-Object -ComObject Wscript.Shell
                $wscript.SendKeys('#{d}')
                """
                subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, timeout=2)
                return {"status": "success", "mode": "focus", "message": "Focus mode activated: background windows cleared."}
            except Exception as e:
                return {"status": "error", "error": str(e)}

        return {"status": "error", "message": f"Unknown workspace mode: {mode}"}


# Action plugin handler for Charlie's tool registry
def execute_macro(action: str, parameters: dict) -> dict:
    engine = DesktopMacroEngine()
    if action == "snap_window":
        direction = parameters.get("direction", "left")
        ok = engine.snap_active_window(direction)
        return {"status": "ok" if ok else "failed", "direction": direction}
    elif action == "setup_workspace":
        mode = parameters.get("mode", "dev")
        return engine.setup_workspace(mode)
    return {"status": "error", "message": f"Unknown action: {action}"}
