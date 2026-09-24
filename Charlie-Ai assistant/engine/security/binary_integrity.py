"""
engine/security/binary_integrity.py — Binary Integrity Checker.

Verifies SHA256 hashes of critical modules at startup to detect tampering.
If modification detected → logs warning, marks integrity suspicious.

Critical modules protected:
  - engine/commercial/feature_gate.py
  - engine/commercial/entitlement_verifier.py
  - engine/commercial/licensing_client.py
  - engine/commercial/device_identity.py
  - engine/commercial/core.py
  - engine/security/core.py
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.security.binary_integrity")

# Critical module paths relative to app root
CRITICAL_MODULES = [
    "engine/commercial/feature_gate.py",
    "engine/commercial/entitlement_verifier.py",
    "engine/commercial/licensing_client.py",
    "engine/commercial/device_identity.py",
    "engine/commercial/core.py",
    "engine/commercial/license_manager.py",
    "engine/security/core.py",
]


class BinaryIntegrityChecker:
    """Verifies integrity of critical application modules at startup.

    In production (PyInstaller bundle), checks compiled .pyc/.pyd files.
    In development, checks source .py files.

    Hash manifest is generated at build time by build_production.py.
    """

    def __init__(self, app_root: Optional[Path] = None):
        self.app_root = app_root or Path(__file__).resolve().parent.parent.parent
        self.manifest_path = self.app_root / "config" / "integrity_manifest.json"
        self._expected_hashes: Dict[str, str] = {}
        self._violations: List[str] = []
        self._checked = False

    def load_manifest(self) -> bool:
        """Load expected hashes from build-time manifest."""
        if not self.manifest_path.exists():
            logger.warning("Integrity manifest not found at %s. Skipping verification.", self.manifest_path)
            return False

        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            self._expected_hashes = data.get("hashes", {})
            return bool(self._expected_hashes)
        except Exception as e:
            logger.error("Failed to load integrity manifest: %s", e)
            return False

    def verify_all(self) -> Tuple[bool, List[str]]:
        """Verify all critical modules. Returns (all_ok, list_of_violations).

        Each violation is a string describing the failed module and reason.
        """
        if not self._expected_hashes:
            if not self.load_manifest():
                return True, []  # No manifest = dev mode, skip

        self._violations = []

        for rel_path, expected_hash in self._expected_hashes.items():
            full_path = self.app_root / rel_path
            if not full_path.exists():
                self._violations.append(f"MISSING: {rel_path}")
                continue

            actual_hash = self._hash_file(full_path)
            if actual_hash != expected_hash:
                self._violations.append(
                    f"MODIFIED: {rel_path} (expected={expected_hash[:16]}..., actual={actual_hash[:16]}...)"
                )

        self._checked = True

        if self._violations:
            logger.warning(
                "INTEGRITY VIOLATIONS DETECTED (%d modules): %s",
                len(self._violations),
                "; ".join(self._violations),
            )
            return False, self._violations

        logger.info("Binary integrity check passed. %d modules verified.", len(self._expected_hashes))
        return True, []

    def verify_single(self, rel_path: str) -> Tuple[bool, str]:
        """Verify a single module's integrity."""
        if rel_path not in self._expected_hashes:
            return True, "Not in manifest (untracked)."

        full_path = self.app_root / rel_path
        if not full_path.exists():
            return False, f"Module missing: {rel_path}"

        actual = self._hash_file(full_path)
        expected = self._expected_hashes[rel_path]
        if actual != expected:
            return False, f"Hash mismatch for {rel_path}"
        return True, "OK"

    @property
    def is_integrity_ok(self) -> bool:
        if not self._checked:
            self.verify_all()
        return len(self._violations) == 0

    @property
    def violations(self) -> List[str]:
        return list(self._violations)

    @staticmethod
    def _hash_file(path: Path) -> str:
        """SHA256 hash of file contents."""
        sha = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(8192):
                sha.update(chunk)
        return sha.hexdigest()

    @staticmethod
    def generate_manifest(app_root: Path, output_path: Optional[Path] = None) -> Dict[str, str]:
        """Generate integrity manifest for build time. Called by build_production.py.

        Returns dict of {relative_path: sha256_hash}.
        """
        hashes: Dict[str, str] = {}
        for rel in CRITICAL_MODULES:
            full = app_root / rel
            if full.exists():
                sha = hashlib.sha256()
                with open(full, "rb") as f:
                    while chunk := f.read(8192):
                        sha.update(chunk)
                hashes[rel] = sha.hexdigest()

        manifest = {
            "version": "1.0",
            "modules_count": len(hashes),
            "hashes": hashes,
        }

        out = output_path or (app_root / "config" / "integrity_manifest.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        logger.info("Integrity manifest generated: %d modules → %s", len(hashes), out)

        return hashes
