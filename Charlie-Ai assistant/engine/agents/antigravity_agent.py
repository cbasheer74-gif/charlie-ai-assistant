"""engine/agents/antigravity_agent.py — Google Antigravity & IDE Bridge Specialist.

Inspects open Antigravity and VS Code windows, loads project phase and memory,
and formulates precise, non-regenerating prompts for advanced agentic workflows.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

from engine.agents.base import BaseAgent


class AntigravityAgent(BaseAgent):
    """Specialist agent for coordinating with Google Antigravity IDE and VS Code."""

    def can_handle(self, user_intent: str) -> bool:
        low = user_intent.lower()
        return any(w in low for w in ("antigravity", "continue in antigravity", "ide prompt", "vs code prompt"))

    def detect_ide_windows(self) -> List[str]:
        """Check for running Antigravity or VS Code window titles."""
        if sys.platform != "win32":
            return []

        import ctypes
        user32 = ctypes.windll.user32
        titles = []

        def enum_windows_callback(hwnd, extra):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value
                    if any(x in title.lower() for x in ("antigravity", "visual studio code", "vscode")):
                        titles.append(title)
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)
        return titles

    def prepare_antigravity_prompt(
        self,
        project_name: str,
        task_goal: str,
        active_phase: str = "implementation",
    ) -> Dict[str, Any]:
        """Formulate a concise, high-context instruction prompt for Antigravity."""
        p_ctx = self.memory.get_project_context(project_name)
        facts = p_ctx.get("facts", {})
        recent_task = p_ctx.get("last_task")

        context_bullets = []
        for cat, kvs in facts.items():
            for k, v in kvs.items():
                context_bullets.append(f"- {cat}.{k}: {v}")

        last_done = recent_task.get("last_checkpoint") if recent_task else "Initial setup"

        antigravity_prompt = (
            f"Project: {project_name}\n"
            f"Phase: {active_phase}\n"
            f"Last Verified State: {last_done}\n\n"
            f"Known Context:\n" + ("\n".join(context_bullets) if context_bullets else "- No prior constraints recorded") + "\n\n"
            f"Requested Action:\n{task_goal}\n\n"
            f"Guidelines: Make targeted edits only. Do not regenerate functioning modules. Run verification after modification."
        )

        open_windows = self.detect_ide_windows()
        ide_status = "Detected open Antigravity/VS Code window" if open_windows else "Antigravity window not currently detected"

        return {
            "project": project_name,
            "ide_status": ide_status,
            "detected_windows": open_windows,
            "generated_prompt": antigravity_prompt,
        }
