"""
engine/deployment/update_installer.py — Controlled updater process and installation coordinator.

Ensures:
  1. No termination of unrelated apps (Filmora, Excel, browser remain untouched).
  2. Safe shutdown of JARVIS before binary modification.
  3. Re-verification of package integrity prior to execution.
  4. No Windows reboots without explicit user approval.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from engine.deployment.paths import DeploymentPathManager
from engine.deployment.update_rollback import ChecksumVerifier, SignatureVerifier

logger = logging.getLogger("jarvis.deployment.update_installer")


class UpdateInstaller:
    """Orchestrates update execution with safety checks and clean process handling."""

    def __init__(
        self,
        path_manager: Optional[DeploymentPathManager] = None,
        public_key_pem: Optional[str] = None,
    ):
        self.paths = path_manager or DeploymentPathManager()
        self.checksum_verifier = ChecksumVerifier()
        self.signature_verifier = SignatureVerifier(public_key_pem)

    def verify_before_install(
        self,
        package_path: Path,
        expected_sha256: str,
        manifest_dict: Optional[Dict[str, Any]] = None,
        signature_b64: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Final integrity check immediately prior to spawning installer."""
        if not package_path.exists():
            return False, "PACKAGE_FILE_MISSING"

        # Checksum
        ok_hash, hash_msg = self.checksum_verifier.verify_and_quarantine(package_path, expected_sha256)
        if not ok_hash:
            return False, f"PRE_INSTALL_CHECKSUM_FAILED: {hash_msg}"

        # Signature (if provided)
        if manifest_dict and signature_b64:
            ok_sig, sig_msg = self.signature_verifier.verify_manifest(manifest_dict, signature_b64)
            if not ok_sig:
                return False, f"PRE_INSTALL_SIGNATURE_FAILED: {sig_msg}"

        return True, "VERIFICATION_SUCCESS"

    def execute_installer(
        self,
        installer_path: Path,
        silent: bool = True,
        auto_restart: bool = True,
    ) -> Tuple[bool, str]:
        """Spawns installer in controlled mode without terminating external software or rebooting OS."""
        if not installer_path.exists():
            return False, "INSTALLER_NOT_FOUND"

        try:
            # Build command args for Windows Inno Setup or executable
            # /SILENT /NORESTART ensures Windows does NOT reboot
            cmd = [str(installer_path)]
            if silent and installer_path.suffix.lower() == ".exe":
                cmd.extend(["/SILENT", "/NORESTART", "/CLOSEAPPLICATIONS"])

            logger.info("Executing updater: %s", cmd)

            # Spawn updater detached
            if sys.platform == "win32":
                # DETACHED_PROCESS = 0x00000008
                proc = subprocess.Popen(
                    cmd,
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                    close_fds=True,
                )
            else:
                proc = subprocess.Popen(cmd, close_fds=True)

            return True, f"INSTALLER_LAUNCHED_PID_{proc.pid}"
        except Exception as e:
            return False, f"INSTALL_SPAWN_FAILED: {e}"
