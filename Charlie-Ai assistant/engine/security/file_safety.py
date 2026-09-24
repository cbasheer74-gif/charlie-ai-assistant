"""engine/security/file_safety.py — Path Traversal Defense, Protected System Paths, Safe Quarantine, and Mass Deletion Gating."""

from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from engine.security.models import RiskLevel


class FileSafetyEngine:
    """Enforces path normalization, protects critical OS paths, routes deletions to quarantine, and guards mass operations."""

    PROTECTED_PATTERNS = [
        r"(?i)^[a-zA-Z]:\\windows(\\|/|$)",
        r"(?i)(\\|/)windows(\\|/)system32(\\|/|$)",
        r"(?i)(\\|/)system32(\\|/|$)",
        r"(?i)^[a-zA-Z]:\\program files(\\|/|$)",
        r"(?i)^[a-zA-Z]:\\program files \(x86\)(\\|/|$)",
        r"(?i)(\\|/)(\.ssh|id_rsa|id_ed25519)(\\.*)?$",
        r"(?i)(\\|/)(\.gitcredentials|git-credentials)$",
    ]

    def __init__(self, quarantine_dir: Optional[Path] = None):
        if quarantine_dir is None:
            self.quarantine_dir = Path.home() / ".jarvis" / "JARVIS_QUARANTINE"
        else:
            self.quarantine_dir = Path(quarantine_dir)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        self._manifest_file = self.quarantine_dir / "quarantine_manifest.json"

    def normalize_and_validate_path(self, raw_path: str) -> Tuple[bool, Optional[Path], str]:
        """Resolves canonical path and prevents path traversal (e.g. ..\\..\\Windows)."""
        if not raw_path or not raw_path.strip():
            return False, None, "Empty path"

        try:
            p = Path(raw_path).resolve()
        except Exception as e:
            return False, None, f"Path resolution error: {e}"

        path_str = str(p)

        # Check directory traversal attempts in raw string
        if ".." in raw_path and not str(p).startswith(str(Path.cwd())):
            # If path traverses outside working directory into system root
            for pat in self.PROTECTED_PATTERNS:
                if re.search(pat, path_str):
                    return False, p, "Path traversal targeting protected system directory"

        # Check protected paths
        for pat in self.PROTECTED_PATTERNS:
            if re.search(pat, path_str):
                return False, p, f"Target path '{path_str}' is protected by security policy"

        return True, p, "Valid safe path"

    def evaluate_mass_operation(self, directory: Path, pattern: str = "*") -> Tuple[int, RiskLevel, str]:
        """Counts targets before mass operation (Section 36 & Test 114) to prevent accidental wipes."""
        if not directory.exists() or not directory.is_dir():
            return 0, RiskLevel.R0_READ_ONLY, "Directory not found"

        count = sum(1 for _ in directory.glob(pattern))
        if count >= 100:
            return count, RiskLevel.R4_CRITICAL, f"Mass operation: {count} files match pattern. Requires explicit confirmation."
        elif count >= 20:
            return count, RiskLevel.R3_HIGH_IMPACT, f"Substantial operation: {count} files match pattern."

        return count, RiskLevel.R1_SAFE_WRITE, f"Routine operation: {count} files match."

    def safe_delete(self, target_path: Path, reason: str = "User command") -> Tuple[bool, str]:
        """Moves file to JARVIS_QUARANTINE instead of permanently deleting it (Section 34 & 35)."""
        if not target_path.exists():
            return False, "Target does not exist"

        valid, norm_path, msg = self.normalize_and_validate_path(str(target_path))
        if not valid or not norm_path:
            return False, f"Deletion blocked: {msg}"

        quarantine_name = f"{norm_path.name}_{int(time.time()*1000)}"
        quarantine_target = self.quarantine_dir / quarantine_name

        try:
            shutil.move(str(norm_path), str(quarantine_target))
            return True, f"Safely moved to quarantine: {quarantine_target.name}"
        except Exception as e:
            return False, f"Failed to quarantine file: {e}"
