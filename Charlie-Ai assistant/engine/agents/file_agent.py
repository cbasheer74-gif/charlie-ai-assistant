"""engine/agents/file_agent.py — File Management and Organization Specialist.

Discovers files via search, inspects metadata, executes copy/move/rename with
recoverable backup safety, and guards against unauthorized permanent deletion.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.agents.base import BaseAgent


class FileAgent(BaseAgent):
    """Specialist agent for file and folder management."""

    def can_handle(self, user_intent: str) -> bool:
        low = user_intent.lower()
        return any(w in low for w in ("file", "folder", "copy file", "move file", "rename file", "find file", "catalog"))

    def safe_copy(self, source: Path | str, destination: Path | str) -> Dict[str, Any]:
        """Copy file with verification."""
        src = Path(source).resolve()
        dest = Path(destination).resolve()
        if not src.is_file():
            return {"status": "failed", "error": f"Source {src.name} not found."}

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        ok, msg = self.verification.verify_file(dest)
        return {
            "status": "success" if ok else "failed",
            "source": str(src),
            "destination": str(dest),
            "verification": msg,
        }
