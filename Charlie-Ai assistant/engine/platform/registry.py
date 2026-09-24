"""
JARVIS Phase 12: Plugin Registry & Extension Health Manager
Manages extension lifecycle, versioning, health tracking, and circuit breakers.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from .models import ExtensionManifest, PluginLifecycle, TrustStatus
from .security import ExtensionSandbox, PluginSecurityScanner

logger = logging.getLogger("jarvis.platform.registry")


class ExtensionHealthManager:
    """Monitors plugin crashes, trips circuit breakers, and tracks latencies."""

    def __init__(self, failure_threshold: int = 3):
        self.failure_threshold = failure_threshold
        # plugin_id -> stats
        self._stats: Dict[str, Dict[str, Any]] = {}

    def record_success(self, plugin_id: str, latency: float):
        entry = self._get_or_create(plugin_id)
        entry["consecutive_failures"] = 0
        entry["total_successes"] += 1
        entry["last_latency"] = latency

    def record_failure(self, plugin_id: str, error: str) -> bool:
        """Records failure. Returns True if circuit breaker tripped."""
        entry = self._get_or_create(plugin_id)
        entry["consecutive_failures"] += 1
        entry["total_failures"] += 1
        entry["last_error"] = error
        if entry["consecutive_failures"] >= self.failure_threshold:
            logger.warning(f"Circuit breaker tripped for plugin {plugin_id} (failures: {entry['consecutive_failures']}).")
            return True
        return False

    def is_degraded_or_broken(self, plugin_id: str) -> bool:
        entry = self._get_or_create(plugin_id)
        return entry["consecutive_failures"] >= self.failure_threshold

    def _get_or_create(self, plugin_id: str) -> Dict[str, Any]:
        if plugin_id not in self._stats:
            self._stats[plugin_id] = {
                "consecutive_failures": 0,
                "total_failures": 0,
                "total_successes": 0,
                "last_latency": 0.0,
                "last_error": "",
            }
        return self._stats[plugin_id]


class PluginRegistry:
    """Central store for installed plugins and active extension runtimes."""

    def __init__(self, scanner: Optional[PluginSecurityScanner] = None):
        self.scanner = scanner or PluginSecurityScanner()
        self.health_manager = ExtensionHealthManager()
        # plugin_id -> {manifest, state, trust, sandbox, previous_version}
        self._installed_plugins: Dict[str, Dict[str, Any]] = {}
        # tool_name -> plugin_id
        self._tool_to_plugin: Dict[str, str] = {}

    def install_plugin(self, manifest: ExtensionManifest) -> Tuple[bool, str]:
        """Validates, scans, and installs a new plugin."""
        # 1. Security scan
        is_safe, issues = self.scanner.scan_manifest(manifest)
        if not is_safe:
            return False, f"Installation rejected by Security Scanner: {', '.join(issues)}"

        # 2. Check existing version for upgrade/rollback backup
        prev_manifest = None
        if manifest.id in self._installed_plugins:
            prev_manifest = self._installed_plugins[manifest.id]["manifest"]
            logger.info(f"Upgrading plugin {manifest.id} from {prev_manifest.version} to {manifest.version}")

        # 3. Create sandbox
        sandbox = ExtensionSandbox(manifest)

        self._installed_plugins[manifest.id] = {
            "manifest": manifest,
            "state": PluginLifecycle.INSTALLED,
            "trust": TrustStatus.TRUSTED if manifest.signature else TrustStatus.REVIEWED,
            "sandbox": sandbox,
            "installed_at": time.time(),
            "previous_version": prev_manifest,
        }

        # Index tools
        for t in manifest.tools:
            self._tool_to_plugin[t] = manifest.id

        logger.info(f"Plugin '{manifest.id}' (v{manifest.version}) installed successfully.")
        return True, "Installed successfully."

    def enable_plugin(self, plugin_id: str) -> Tuple[bool, str]:
        entry = self._installed_plugins.get(plugin_id)
        if not entry:
            return False, f"Plugin {plugin_id} not found."
        entry["state"] = PluginLifecycle.ENABLED
        return True, f"Plugin {plugin_id} enabled."

    def disable_plugin(self, plugin_id: str) -> Tuple[bool, str]:
        entry = self._installed_plugins.get(plugin_id)
        if not entry:
            return False, f"Plugin {plugin_id} not found."
        entry["state"] = PluginLifecycle.DISABLED
        return True, f"Plugin {plugin_id} disabled."

    def quarantine_plugin(self, plugin_id: str, reason: str = "Policy violation") -> Tuple[bool, str]:
        entry = self._installed_plugins.get(plugin_id)
        if not entry:
            return False, f"Plugin {plugin_id} not found."
        entry["state"] = PluginLifecycle.QUARANTINED
        logger.error(f"Plugin {plugin_id} quarantined: {reason}")
        return True, f"Plugin {plugin_id} quarantined: {reason}."

    def uninstall_plugin(self, plugin_id: str) -> Tuple[bool, str]:
        entry = self._installed_plugins.pop(plugin_id, None)
        if not entry:
            return False, f"Plugin {plugin_id} not found."

        # Remove tool mappings
        manifest: ExtensionManifest = entry["manifest"]
        for t in manifest.tools:
            self._tool_to_plugin.pop(t, None)

        logger.info(f"Plugin {plugin_id} uninstalled and removed from registry.")
        return True, f"Plugin {plugin_id} uninstalled."

    def rollback_plugin(self, plugin_id: str) -> Tuple[bool, str]:
        """Rolls back to previous version if available."""
        entry = self._installed_plugins.get(plugin_id)
        if not entry or not entry.get("previous_version"):
            return False, f"No previous version available for rollback of {plugin_id}."

        prev: ExtensionManifest = entry["previous_version"]
        entry["manifest"] = prev
        entry["previous_version"] = None
        entry["sandbox"] = ExtensionSandbox(prev)
        entry["state"] = PluginLifecycle.ENABLED
        logger.info(f"Rolled back plugin {plugin_id} to version {prev.version}.")
        return True, f"Rolled back to v{prev.version}."

    def get_plugin(self, plugin_id: str) -> Optional[ExtensionManifest]:
        entry = self._installed_plugins.get(plugin_id)
        return entry["manifest"] if entry else None

    def list_plugins(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": p_id,
                "name": data["manifest"].name,
                "version": data["manifest"].version,
                "type": data["manifest"].type.value,
                "state": data["state"].value,
                "trust": data["trust"].value,
                "tools": data["manifest"].tools,
            }
            for p_id, data in self._installed_plugins.items()
        ]

    def get_sandbox_for_tool(self, tool_name: str) -> Optional[ExtensionSandbox]:
        plugin_id = self._tool_to_plugin.get(tool_name)
        if not plugin_id:
            return None
        entry = self._installed_plugins.get(plugin_id)
        if not entry or entry["state"] != PluginLifecycle.ENABLED:
            return None
        return entry["sandbox"]
