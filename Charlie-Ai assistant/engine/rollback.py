"""engine/rollback.py — Rollback Manager and Recoverable Operation Tracker.

Provides automatic copy-first file backups and integration with core/undo.py.
"""

from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from core import undo
from core.undo import push_undo


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BACKUP_ROOT = get_base_dir() / "memory" / ".backups"


class RollbackManager:
    """Manages file backups, git safety checkpoints, and undo integration."""

    def __init__(self, backup_dir: Optional[Path] = None):
        self.backup_dir = backup_dir or BACKUP_ROOT
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def backup_file(self, target_path: Path) -> Optional[Path]:
        """Create a recoverable timestamped backup of a file before modifying it."""
        path = Path(target_path).resolve()
        if not path.is_file() or path.is_symlink():
            return None

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_file = self.backup_dir / f"{path.stem}_{stamp}{path.suffix}.bak"
        try:
            shutil.copy2(path, backup_file)

            # Register with undo stack
            def _restore():
                if backup_file.exists() and not path.is_symlink():
                    shutil.copy2(backup_file, path)
                    return f"Restored {path.name} from backup."
                return f"Backup {backup_file.name} missing or invalid target."

            push_undo(f"modify {path.name} (restore previous content)", _restore)
            return backup_file
        except Exception:
            return None

    def restore_file(self, backup_path: Path, target_path: Path) -> bool:
        """Explicitly restore a file from its backup."""
        b_path = Path(backup_path).resolve()
        t_path = Path(target_path).resolve()
        base_res = self.backup_dir.resolve()

        # Enforce containment: backup_path must reside within backup_dir
        try:
            if not b_path.is_file() or not b_path.is_relative_to(base_res):
                return False
        except (AttributeError, ValueError):
            return False

        if t_path.is_symlink() or Path(target_path).is_symlink():
            return False

        try:
            shutil.copy2(b_path, t_path)
            return True
        except Exception:
            return False

    def list_undoable_actions(self) -> List[str]:
        """Return human-readable list of currently undoable operations."""
        return undo.history()
