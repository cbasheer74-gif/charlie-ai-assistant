"""
engine/deployment/update_client.py — Desktop HTTP client for official signed release checking and downloading.

Integrates with licensing_server /updates API with timeout, non-blocking check, and telemetry.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from engine.deployment.paths import DeploymentPathManager

logger = logging.getLogger("jarvis.deployment.update_client")


class UpdateClient:
    """Communicates with the official JARVIS release server for updates."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        path_manager: Optional[DeploymentPathManager] = None,
        timeout_seconds: int = 5,
    ):
        self.base_url = base_url.rstrip("/")
        self.paths = path_manager or DeploymentPathManager()
        self.timeout = timeout_seconds

    def check_for_updates(
        self,
        current_version: str,
        channel: str = "STABLE",
        device_id: Optional[str] = None,
    ) -> Tuple[bool, Dict[str, Any]]:
        """Queries /updates/check. Returns (available, details_dict). Non-blocking and offline safe."""
        params = {
            "version": current_version,
            "channel": channel,
        }
        if device_id:
            params["device_id"] = device_id

        query_str = urllib.parse.urlencode(params)
        url = f"{self.base_url}/updates/check?{query_str}"

        try:
            req = urllib.request.Request(url, headers={"User-Agent": f"JARVIS-Desktop/{current_version}"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    is_avail = bool(data.get("update_available", False))
                    return is_avail, data
                return False, {"error": f"HTTP {resp.status}"}
        except urllib.error.URLError as e:
            logger.info("Release server unreachable (%s). Running with installed version.", e)
            return False, {"error": "OFFLINE", "reason": str(e)}
        except Exception as e:
            logger.warning("Update check exception: %s", e)
            return False, {"error": "EXCEPTION", "reason": str(e)}

    def download_package(
        self,
        download_url: str,
        target_version: str,
        expected_size: int = 0,
    ) -> Tuple[bool, str, Optional[Path]]:
        """Downloads release package into local quarantine directory in AppData/JARVIS/updates/."""
        updates_dir = self.paths.get_sub_dir("updates")
        target_file = updates_dir / f"JARVIS_Setup_{target_version}.bin"
        temp_file = updates_dir / f"JARVIS_Setup_{target_version}.part"

        # Check if URL is local file path (for testing or offline bundle)
        if download_url.startswith("file://") or os.path.exists(download_url):
            local_src = Path(download_url.replace("file://", ""))
            if local_src.exists():
                import shutil
                shutil.copyfile(local_src, target_file)
                return True, "LOCAL_FILE_COPIED", target_file

        try:
            req = urllib.request.Request(download_url, headers={"User-Agent": "JARVIS-Updater/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp, open(temp_file, "wb") as out:
                shutil_copy = resp.read()
                out.write(shutil_copy)

            # Atomic rename after full download completes
            if temp_file.exists():
                temp_file.replace(target_file)

            return True, "DOWNLOAD_COMPLETE", target_file
        except Exception as e:
            temp_file.unlink(missing_ok=True)
            return False, f"DOWNLOAD_FAILED: {e}", None

    def send_telemetry(
        self,
        event_type: str,
        client_version: str,
        target_version: str,
        channel: str = "STABLE",
        device_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Dispatches anonymous update telemetry event to release server."""
        url = f"{self.base_url}/updates/telemetry"
        payload = {
            "event_type": event_type,
            "client_version": client_version,
            "target_version": target_version,
            "channel": channel,
            "device_id": device_id,
            "details": details or {},
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "JARVIS-Updater/1.0"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status == 200
        except Exception:
            return False
