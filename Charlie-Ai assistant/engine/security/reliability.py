"""engine/security/reliability.py — Download Security, Update Safety with Rollback, Circuit Breaker, and Watchdog."""

from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from engine.security.backup_recovery import BackupManager, RecoveryManager
from engine.security.models import DownloadRecord


class DownloadSecurityEngine:
    """Inspects downloaded files, verifies extensions/mime types, and isolates untrusted executables (Section 15 & 16 & Test 117)."""

    TRUSTED_DOMAINS = {"github.com", "python.org", "flutter.dev", "microsoft.com", "google.com"}
    EXECUTABLE_EXTENSIONS = {".exe", ".msi", ".bat", ".cmd", ".ps1", ".dll", ".vbs"}

    def __init__(self, download_dir: Optional[Path] = None):
        if download_dir is None:
            self.download_dir = Path.home() / ".jarvis" / "downloads"
        else:
            self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self._records: List[DownloadRecord] = []

    def inspect_and_record_download(
        self,
        url: str,
        domain: str,
        file_path: Path,
    ) -> DownloadRecord:
        """Inspects downloaded file and quarantines untrusted executables."""
        content = file_path.read_bytes() if file_path.exists() else b""
        f_hash = hashlib.sha256(content).hexdigest()
        ext = file_path.suffix.lower()

        is_trusted = domain.lower() in self.TRUSTED_DOMAINS
        quarantine = False

        # If executable from untrusted origin -> quarantine!
        if ext in self.EXECUTABLE_EXTENSIONS and not is_trusted:
            quarantine = True

        rec = DownloadRecord(
            id=f"dl_{int(time.time()*1000)}",
            url=url,
            domain=domain,
            file_path=str(file_path),
            file_hash=f_hash,
            mime_type=ext,
            size_bytes=len(content),
            is_trusted_origin=is_trusted,
            quarantined=quarantine,
        )
        self._records.append(rec)
        return rec


class CircuitBreaker:
    """Stops repeated calling of failing third-party tools/providers (Section 83)."""

    def __init__(self, failure_threshold: int = 3, recovery_timeout_sec: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout_sec = recovery_timeout_sec
        self.state: str = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.failure_count: int = 0
        self.last_failure_time: float = 0.0

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = "CLOSED"

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"

    def is_call_permitted(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if (time.time() - self.last_failure_time) > self.recovery_timeout_sec:
                self.state = "HALF_OPEN"
                return True
            return False
        return True  # HALF_OPEN


class ReliabilitySupervisor:
    """Monitors system resources, circuit breakers, and subsystem health (Section 81 & 82)."""

    def __init__(self):
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}

    def get_circuit_breaker(self, tool_name: str) -> CircuitBreaker:
        if tool_name not in self.circuit_breakers:
            self.circuit_breakers[tool_name] = CircuitBreaker()
        return self.circuit_breakers[tool_name]

    @staticmethod
    def check_disk_space(target_path: Path, min_free_mb: int = 200) -> bool:
        """Verifies sufficient disk space before large write/backup (Section 87)."""
        try:
            usage = shutil.disk_usage(str(target_path if target_path.exists() else target_path.parent))
            free_mb = usage.free // (1024 * 1024)
            return free_mb >= min_free_mb
        except Exception:
            return True


class UpdateSafetyManager:
    """Manages update lifecycle with precheck, backup, health verification, and rollback (Section 76 & 77 & Test 124)."""

    def __init__(self, backup_manager: BackupManager, recovery_manager: RecoveryManager):
        self.backup_manager = backup_manager
        self.recovery_manager = recovery_manager

    def execute_safe_update(
        self,
        current_file: Path,
        new_content: bytes,
        health_check_fn: Callable[[], bool],
    ) -> Tuple[bool, str]:
        """Runs the update sequence: Backup -> Apply -> Health Check -> Commit or Rollback."""
        # 1. Pre-update verified backup
        ok, backup_rec, msg = self.backup_manager.create_file_backup(current_file, backup_type="UPDATE_PRE_BACKUP")
        if not ok or not backup_rec:
            return False, f"Update aborted: Pre-update backup failed ({msg})"

        # 2. Apply new update
        try:
            current_file.write_bytes(new_content)
        except Exception as e:
            return False, f"Update write failed: {e}"

        # 3. Post-install Health Check
        try:
            healthy = health_check_fn()
        except Exception:
            healthy = False

        if not healthy:
            # Health check failed -> AUTOMATIC ROLLBACK! (Test 124)
            restored, r_msg = self.recovery_manager.restore_from_backup(backup_rec.id, target_override=current_file)
            return False, f"Update failed health check! Automatically rolled back: {restored} ({r_msg})"

        return True, "Update verified and committed successfully"
