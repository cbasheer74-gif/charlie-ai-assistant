"""
engine/deployment/self_updater.py — Desktop Background Auto-Update Orchestrator.

Capabilities:
  1. Background asynchronous polling of /updates/check.
  2. SHA-256 package verification & quarantine isolation.
  3. Controlled binary replacement / Inno Setup launch.
  4. Safe shutdown and launch handoff.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from engine.deployment.paths import DeploymentPathManager
from engine.deployment.update_client import UpdateClient
from engine.deployment.update_installer import UpdateInstaller
from engine.deployment.update_rollback import RollbackManager

logger = logging.getLogger("charlie.deployment.self_updater")


class SelfUpdaterService:
    """Manages background polling, cryptographic verification, and update launch."""

    def __init__(
        self,
        current_version: str,
        base_url: str = "http://127.0.0.1:8400",
        channel: str = "STABLE",
        poll_interval_seconds: int = 3600,
        on_update_ready: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_update_error: Optional[Callable[[str], None]] = None,
    ):
        self.current_version = current_version
        self.channel = channel
        self.poll_interval = poll_interval_seconds
        self.paths = DeploymentPathManager()
        self.client = UpdateClient(base_url=base_url, path_manager=self.paths)
        self.installer = UpdateInstaller(path_manager=self.paths)
        self.rollback_mgr = RollbackManager(path_manager=self.paths)
        
        self.on_update_ready = on_update_ready
        self.on_update_error = on_update_error
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._downloaded_installer: Optional[Path] = None
        self._pending_update_info: Optional[Dict[str, Any]] = None

    def start_background_poller(self) -> None:
        """Starts asynchronous thread for periodic update checks."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="CharlieUpdatePoller")
        self._thread.start()
        logger.info("Background update poller started (interval: %ds).", self.poll_interval)

    def stop_background_poller(self) -> None:
        """Stops the update polling loop."""
        self._running = False

    def _poll_loop(self) -> None:
        # Initial sleep before first check to avoid slowing application launch
        time.sleep(15)
        while self._running:
            try:
                self.check_and_stage_update()
            except Exception as e:
                logger.warning("Background update check encountered error: %s", e)
                if self.on_update_error:
                    self.on_update_error(str(e))
            
            # Sleep in intervals for responsive shutdown
            for _ in range(max(1, self.poll_interval // 5)):
                if not self._running:
                    break
                time.sleep(5)

    def check_and_stage_update(self) -> Optional[Dict[str, Any]]:
        """Queries server, validates release requirements, downloads and verifies package."""
        logger.info("Checking for application updates (current: %s, channel: %s)...", self.current_version, self.channel)
        avail, details = self.client.check_for_updates(
            current_version=self.current_version,
            channel=self.channel,
        )

        if not avail or not details:
            logger.info("No new application update available.")
            return None

        target_version = details.get("target_version")
        download_url = details.get("download_url")
        expected_sha256 = details.get("sha256") or details.get("checksum")

        if not download_url or not expected_sha256:
            logger.error("Update payload missing download_url or sha256 checksum.")
            return None

        logger.info("Found update %s. Starting quarantine download...", target_version)
        ok_dl, dl_msg, pkg_path = self.client.download_package(
            download_url=download_url,
            target_version=str(target_version),
        )

        if not ok_dl or not pkg_path:
            logger.error("Download failed: %s", dl_msg)
            return None

        # Verify SHA-256 Checksum
        ok_verify, verify_msg = self.installer.verify_before_install(
            package_path=pkg_path,
            expected_sha256=expected_sha256,
        )

        if not ok_verify:
            logger.error("SHA-256 verification failed: %s. Quarantined file discarded.", verify_msg)
            pkg_path.unlink(missing_ok=True)
            return None

        logger.info("Update %s verified successfully. Staged at: %s", target_version, pkg_path)
        self._downloaded_installer = pkg_path
        self._pending_update_info = details

        # Fire notification callback
        if self.on_update_ready:
            self.on_update_ready(details)

        return details

    def launch_update_and_exit(self, silent: bool = True) -> bool:
        """Launches the verified installer and terminates current application instance."""
        if not self._downloaded_installer or not self._downloaded_installer.exists():
            logger.error("No verified installer package available to execute.")
            return False

        # Create rollback snapshot before executing installer
        current_app_dir = Path(__file__).resolve().parents[2]
        self.rollback_mgr.create_snapshot(current_app_dir, self.current_version)

        ok_spawn, spawn_msg = self.installer.execute_installer(
            self._downloaded_installer,
            silent=silent,
            auto_restart=True,
        )

        if not ok_spawn:
            logger.error("Failed to spawn installer: %s", spawn_msg)
            return False

        logger.info("Installer launched (%s). Safe application exit initiated.", spawn_msg)
        
        # Telemetry
        if self._pending_update_info:
            self.client.send_telemetry(
                event_type="INSTALL_LAUNCHED",
                client_version=self.current_version,
                target_version=str(self._pending_update_info.get("target_version", "")),
                channel=self.channel,
            )

        return True
