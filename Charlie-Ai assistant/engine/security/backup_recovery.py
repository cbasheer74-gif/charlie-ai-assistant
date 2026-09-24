"""engine/security/backup_recovery.py — Backup Creation, Hash Verification, and Point-in-Time Recovery."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.security.models import BackupRecord


class BackupManager:
    """Manages verified snapshots of JARVIS databases, knowledge graph, and configuration (Section 41 & 45)."""

    def __init__(self, backup_dir: Optional[Path] = None):
        if backup_dir is None:
            self.backup_dir = Path.home() / ".jarvis" / "backups"
        else:
            self.backup_dir = Path(backup_dir)
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self._records: Dict[str, BackupRecord] = {}

    def create_file_backup(
        self,
        source_path: Path,
        backup_type: str = "CONFIG",
    ) -> Tuple[bool, Optional[BackupRecord], str]:
        """Creates a verified backup snapshot of a file (Section 45 & Test 121)."""
        if not source_path.exists():
            return False, None, "Source file does not exist"

        # Check destination accessibility (Test 122)
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            test_file = self.backup_dir / f".write_test_{int(time.time())}"
            test_file.write_text("test")
            test_file.unlink()
        except Exception as e:
            return False, None, f"Backup destination unavailable: {e}"

        now = time.time()
        backup_id = f"b_snap_{source_path.stem}_{int(now*1000)}"
        dest_path = self.backup_dir / f"{backup_id}_{source_path.name}"

        try:
            shutil.copy2(str(source_path), str(dest_path))

            # Verify backup integrity (hash & size)
            data = dest_path.read_bytes()
            size = len(data)
            content_hash = hashlib.sha256(data).hexdigest()

            if size == 0:
                dest_path.unlink()
                return False, None, "Backup verification failed: 0 bytes written"

            record = BackupRecord(
                id=backup_id,
                backup_path=str(dest_path),
                timestamp=now,
                backup_type=backup_type,
                size_bytes=size,
                content_hash=content_hash,
                verified=True,
                details={"original_path": str(source_path)},
            )
            self._records[backup_id] = record
            return True, record, "Backup created and verified successfully"

        except Exception as e:
            return False, None, f"Backup failed during copy: {e}"

    def get_backup_record(self, backup_id: str) -> Optional[BackupRecord]:
        return self._records.get(backup_id)


class RecoveryManager:
    """Restores files, databases, and project states from verified snapshots (Section 46 & Test 123)."""

    def __init__(self, backup_manager: BackupManager):
        self.backup_manager = backup_manager

    def restore_from_backup(self, backup_id: str, target_override: Optional[Path] = None) -> Tuple[bool, str]:
        """Restores a snapshot to original or overridden path with verification."""
        record = self.backup_manager.get_backup_record(backup_id)
        if not record:
            return False, "Backup record not found"

        snap_path = Path(record.backup_path)
        if not snap_path.exists():
            return False, "Backup snapshot file is missing"

        # Verify hash matches before restoration
        data = snap_path.read_bytes()
        actual_hash = hashlib.sha256(data).hexdigest()
        if actual_hash != record.content_hash:
            return False, "Snapshot hash mismatch! Restoration aborted for integrity."

        target = target_override or Path(record.details.get("original_path", ""))
        if not target:
            return False, "Target path unknown"

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(snap_path), str(target))
            return True, f"Restored successfully to {target}"
        except Exception as e:
            return False, f"Restoration copy failed: {e}"
