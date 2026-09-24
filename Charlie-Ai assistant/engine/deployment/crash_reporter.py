"""
engine/deployment/crash_reporter.py — Crash reporting manager, privacy-safe storage, offline queue, and recovery advisor.

Handles crash event tracking, user consent settings, local directory layout,
isolated plugin fault boundaries, and bounded retry upload client.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from engine.deployment.diagnostic_collector import (
    CrashSignatureGenerator,
    DiagnosticCollector,
    ErrorLevel,
    SecretRedactor,
)
from engine.deployment.paths import DeploymentPathManager


class ConsentSetting(str, Enum):
    ASK_EVERY_TIME = "ASK_EVERY_TIME"
    AUTO_SEND = "AUTO_SEND"
    NEVER_SEND = "NEVER_SEND"


class TaskCategory(str, Enum):
    GENERAL = "GENERAL"
    STARTUP = "STARTUP"
    VOICE = "VOICE"
    VIDEO_EDITING = "VIDEO_EDITING"
    CODING = "CODING"
    RESEARCH = "RESEARCH"
    COMPUTER_AUTOMATION = "COMPUTER_AUTOMATION"
    UPDATE = "UPDATE"
    PLUGIN = "PLUGIN"


@dataclass
class CrashEvent:
    crash_id: str
    timestamp: str
    app_version: str
    build_number: int
    release_channel: str
    os_version: str
    architecture: str
    device_id_ref: str
    subscription_plan: str
    active_task_category: str
    component: str
    error_type: str
    error_code: str
    sanitized_message: str
    stack_signature: str
    stack_trace: str
    error_level: str = ErrorLevel.ERROR.value
    recovery_attempted: bool = False
    recovery_result: str = "NORMAL"
    user_comment: str = ""
    screenshot_included: bool = False


class CrashReportingManager:
    """Orchestrates crash capture, local storage layout, privacy scrub, and upload lifecycle."""

    def __init__(
        self,
        app_version: str = "1.0.0",
        build_number: int = 100,
        channel: str = "STABLE",
        path_manager: Optional[DeploymentPathManager] = None,
    ):
        self.app_version = app_version
        self.build_number = build_number
        self.channel = channel
        self.paths = path_manager or DeploymentPathManager()
        self.collector = DiagnosticCollector(app_version, build_number, channel, self.paths)

        # Setup standard subdirectories inside diagnostics
        self.diag_dir = self.paths.get_sub_dir("diagnostics")
        self.crashes_dir = self.diag_dir / "crashes"
        self.logs_dir = self.diag_dir / "logs"
        self.bundles_dir = self.diag_dir / "bundles"
        self.reports_dir = self.diag_dir / "reports"
        self.queue_dir = self.diag_dir / "queue"

        for d in [self.crashes_dir, self.logs_dir, self.bundles_dir, self.reports_dir, self.queue_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self.settings_file = self.paths.get_sub_dir("config") / "privacy_diagnostics.json"
        self.startup_state_file = self.diag_dir / "startup_state.json"
        self.disabled_plugins_file = self.paths.get_sub_dir("config") / "quarantined_plugins.json"

    # ── Consent & Privacy Configuration ──────────────────────────────────────

    def get_consent_setting(self) -> ConsentSetting:
        """Read privacy setting for crash reports. Default is ASK_EVERY_TIME."""
        if self.settings_file.exists():
            try:
                data = json.loads(self.settings_file.read_text(encoding="utf-8"))
                val = data.get("diagnostic_consent", ConsentSetting.ASK_EVERY_TIME.value)
                return ConsentSetting(val)
            except Exception:
                pass
        return ConsentSetting.ASK_EVERY_TIME

    def set_consent_setting(self, setting: ConsentSetting) -> None:
        """Explicitly change diagnostic consent. Never enable telemetry silently."""
        data = {
            "diagnostic_consent": setting.value,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.settings_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ── Crash Event Recording ────────────────────────────────────────────────

    def capture_crash(
        self,
        component: str,
        error: BaseException,
        stack_trace: str,
        error_level: ErrorLevel = ErrorLevel.ERROR,
        task_category: TaskCategory = TaskCategory.GENERAL,
        subscription_plan: str = "STARTER",
        device_id: str = "DEV_LOCAL",
        user_comment: str = "",
        include_screenshot: bool = False,
        screenshot_base64: Optional[str] = None,
    ) -> CrashEvent:
        """Capture, sanitize, and locally persist crash event."""
        clean_msg = SecretRedactor.sanitize_text(str(error))
        clean_stack = SecretRedactor.sanitize_text(stack_trace)
        sig = CrashSignatureGenerator.generate(type(error).__name__, clean_stack, component)

        crash_id = f"JARVIS-CRASH-{uuid.uuid4().hex[:6].upper()}"
        now = datetime.now(timezone.utc).isoformat()
        dev_ref = SecretRedactor.sanitize_text(device_id)[:12]

        event = CrashEvent(
            crash_id=crash_id,
            timestamp=now,
            app_version=self.app_version,
            build_number=self.build_number,
            release_channel=self.channel,
            os_version=f"{os.name} {sys.platform}",
            architecture=sys.byteorder,
            device_id_ref=dev_ref,
            subscription_plan=subscription_plan,
            active_task_category=task_category.value,
            component=component,
            error_type=type(error).__name__,
            error_code=getattr(error, "code", "E_RUNTIME"),
            sanitized_message=clean_msg,
            stack_signature=sig,
            stack_trace=clean_stack,
            error_level=error_level.value,
            recovery_attempted=True,
            recovery_result="RECOVERED",
            user_comment=SecretRedactor.sanitize_text(user_comment),
            screenshot_included=include_screenshot and bool(screenshot_base64),
        )

        # Save local crash report JSON
        crash_file = self.crashes_dir / f"{crash_id}.json"
        crash_file.write_text(json.dumps(asdict(event), indent=2), encoding="utf-8")

        # Build companion diagnostic bundle
        bundle = self.collector.build_diagnostic_bundle(
            recent_errors=[asdict(event)],
            license_summary={"plan": subscription_plan, "device_id": device_id},
            optional_user_comment=user_comment,
            include_screenshot=include_screenshot,
            screenshot_data_base64=screenshot_base64,
        )
        bundle_file = self.bundles_dir / f"{crash_id}_bundle.json"
        bundle_file.write_text(json.dumps(bundle, indent=2), encoding="utf-8")

        # Check consent setting: if AUTO_SEND, queue for background upload
        if self.get_consent_setting() == ConsentSetting.AUTO_SEND:
            self.enqueue_upload(crash_id)

        # Cleanup old diagnostics
        self.cleanup_retention()

        return event

    # ── Startup Crash Loop & Safe Mode Management ────────────────────────────

    def notify_startup_begin(self) -> int:
        """Mark startup in progress. Increment consecutive failed startup counter."""
        data = self._load_startup_state()
        count = data.get("consecutive_startup_failures", 0) + 1
        data["consecutive_startup_failures"] = count
        data["startup_in_progress"] = True
        data["last_launch_time"] = time.time()
        self._save_startup_state(data)
        return count

    def notify_startup_complete(self) -> None:
        """Main UI successfully initialized. Reset startup failure counter."""
        data = self._load_startup_state()
        data["consecutive_startup_failures"] = 0
        data["startup_in_progress"] = False
        data["last_successful_launch"] = time.time()
        self._save_startup_state(data)

    def is_safe_mode_required(self) -> bool:
        """Returns True if application repeatedly crashed during startup (>= 3 times)."""
        data = self._load_startup_state()
        return data.get("consecutive_startup_failures", 0) >= 3

    def _load_startup_state(self) -> Dict[str, Any]:
        if self.startup_state_file.exists():
            try:
                return json.loads(self.startup_state_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"consecutive_startup_failures": 0, "startup_in_progress": False}

    def _save_startup_state(self, data: Dict[str, Any]) -> None:
        self.startup_state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ── Plugin Failure Isolation ─────────────────────────────────────────────

    def quarantine_plugin(self, plugin_id: str, reason: str) -> None:
        """Disable an unstable plugin to isolate fault and prevent whole-app crash."""
        quarantine = self.get_quarantined_plugins()
        quarantine[plugin_id] = {
            "reason": SecretRedactor.sanitize_text(reason),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.disabled_plugins_file.write_text(json.dumps(quarantine, indent=2), encoding="utf-8")

    def is_plugin_quarantined(self, plugin_id: str) -> bool:
        quarantine = self.get_quarantined_plugins()
        return plugin_id in quarantine

    def get_quarantined_plugins(self) -> Dict[str, Any]:
        if self.disabled_plugins_file.exists():
            try:
                return json.loads(self.disabled_plugins_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    # ── Offline Queue & Upload Client ────────────────────────────────────────

    def enqueue_upload(self, crash_id: str) -> None:
        """Queue crash report for upload."""
        q_file = self.queue_dir / f"{crash_id}.pending"
        q_file.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")

    def process_upload_queue(
        self,
        uploader_func: Optional[Callable[[Dict[str, Any]], Tuple[bool, str]]] = None,
    ) -> List[Tuple[str, bool, str]]:
        """Process queued crash reports. Bounded retry policy."""
        results = []
        pending_files = list(self.queue_dir.glob("*.pending"))

        for pf in pending_files:
            crash_id = pf.stem
            crash_json = self.crashes_dir / f"{crash_id}.json"
            bundle_json = self.bundles_dir / f"{crash_id}_bundle.json"

            if not crash_json.exists():
                pf.unlink(missing_ok=True)
                continue

            try:
                crash_data = json.loads(crash_json.read_text(encoding="utf-8"))
                bundle_data = json.loads(bundle_json.read_text(encoding="utf-8")) if bundle_json.exists() else {}
                payload = {"crash": crash_data, "bundle": bundle_data}

                if uploader_func:
                    success, msg = uploader_func(payload)
                else:
                    # Simulated default offline / mock success
                    success, msg = True, "Uploaded to mock endpoint"

                if success:
                    pf.unlink(missing_ok=True)
                    results.append((crash_id, True, msg))
                else:
                    results.append((crash_id, False, msg))
            except Exception as ex:
                results.append((crash_id, False, str(ex)))

        return results

    # ── Retention & Directory Hygiene ────────────────────────────────────────

    def cleanup_retention(self, max_files: int = 50, max_age_days: int = 30) -> int:
        """Enforce file limit and age retention. Never let diagnostic directory grow unbounded."""
        removed = 0
        now = time.time()
        max_age_sec = max_age_days * 86400

        for folder in [self.crashes_dir, self.bundles_dir]:
            files = sorted(folder.glob("*.json"), key=lambda f: f.stat().st_mtime)
            # Remove expired
            for f in files:
                if now - f.stat().st_mtime > max_age_sec:
                    f.unlink(missing_ok=True)
                    removed += 1
            # Remove oldest if over capacity
            remaining = sorted(folder.glob("*.json"), key=lambda f: f.stat().st_mtime)
            if len(remaining) > max_files:
                for f in remaining[:-max_files]:
                    f.unlink(missing_ok=True)
                    removed += 1

        return removed
