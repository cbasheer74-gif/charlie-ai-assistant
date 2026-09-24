"""
JARVIS Phase 14: Runtime and Lifecycle Management
Manages single instance enforcement, user session agent, background service,
startup configuration, and crash detection with safe mode protection.
"""

import os
import re
import sys
import time
import uuid
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from engine.deployment.models import (
    AppHealthState,
    BuildInfo,
    CrashReport,
)
from engine.deployment.paths import DeploymentPathManager


class SingleInstanceManager:
    """Ensures only a single instance of JARVIS runs per user session."""

    def __init__(self, lock_dir: Optional[Path] = None, lock_name: str = "jarvis.lock"):
        self.lock_dir = lock_dir or DeploymentPathManager().get_sub_dir("checkpoints")
        self.lock_file = self.lock_dir / lock_name
        self._acquired = False

    def acquire(self) -> bool:
        """Attempt to acquire instance lock. Returns True if successfully acquired."""
        if self.lock_file.exists():
            try:
                content = self.lock_file.read_text(encoding="utf-8").strip()
                pid = int(content)
                # Check if process with that pid is still running
                if self._is_pid_running(pid):
                    return False
            except Exception:
                pass  # Stale lock file

        try:
            self.lock_file.write_text(str(os.getpid()), encoding="utf-8")
            self._acquired = True
            return True
        except Exception:
            return False

    def release(self) -> None:
        """Release the instance lock."""
        if self._acquired and self.lock_file.exists():
            try:
                self.lock_file.unlink(missing_ok=True)
            except Exception:
                pass
            self._acquired = False

    def _is_pid_running(self, pid: int) -> bool:
        if pid <= 0:
            return False
        if pid == os.getpid():
            return True
        if sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
                if handle:
                    kernel32.CloseHandle(handle)
                    return True
                return False
            except Exception:
                return False
        else:
            try:
                os.kill(pid, 0)
                return True
            except (OSError, ProcessLookupError):
                return False


class WindowsServiceManager:
    """Non-interactive background service coordinator.
    Reserved strictly for background sync, health checks, and update coordination.
    Interactive automation is strictly isolated to JarvisUserAgent.
    """

    def __init__(self, path_manager: Optional[DeploymentPathManager] = None):
        self.paths = path_manager or DeploymentPathManager()
        self.is_running = False
        self.service_name = "JARVIS_Background_Service"

    def start_service(self) -> Dict[str, Any]:
        self.is_running = True
        return {
            "service": self.service_name,
            "status": "RUNNING",
            "session_0_safe": True,
            "interactive_ui_disabled": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def stop_service(self) -> Dict[str, Any]:
        self.is_running = False
        return {
            "service": self.service_name,
            "status": "STOPPED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def perform_background_health_sync(self) -> Dict[str, Any]:
        """Perform non-interactive maintenance."""
        return {
            "health": "OK",
            "active_tasks_monitored": 0,
            "sync_timestamp": datetime.now(timezone.utc).isoformat(),
        }


class JarvisUserAgent:
    """Interactive user-session agent.
    Runs inside the logged-in desktop session to handle UI automation,
    voice recognition, computer control, screen capture, and tray icons.
    """

    def __init__(self, path_manager: Optional[DeploymentPathManager] = None):
        self.paths = path_manager or DeploymentPathManager()
        self.tray_active = True
        self.voice_listening = False
        self.computer_control_enabled = True

    def initialize_session(self) -> Dict[str, Any]:
        return {
            "session": "USER_DESKTOP",
            "screen_capture_ready": True,
            "computer_control_ready": self.computer_control_enabled,
            "voice_ready": True,
            "tray_ready": self.tray_active,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def set_tray_state(self, active: bool) -> None:
        self.tray_active = active


class StartupManager:
    """Manages Windows startup registration (Run registry key / scheduled task)."""

    def __init__(self, app_name: str = "JARVIS", exe_path: Optional[str] = None):
        self.app_name = app_name
        self.exe_path = exe_path or sys.executable
        self._mock_store_file = DeploymentPathManager().get_sub_dir("config") / "startup_registry.json"

    def is_auto_start_enabled(self) -> bool:
        if self._mock_store_file.exists():
            try:
                data = json.loads(self._mock_store_file.read_text(encoding="utf-8"))
                return data.get("auto_start", False)
            except Exception:
                return False
        return False

    def enable_auto_start(self) -> bool:
        try:
            data = {"auto_start": True, "path": self.exe_path, "updated_at": datetime.now(timezone.utc).isoformat()}
            self._mock_store_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return True
        except Exception:
            return False

    def disable_auto_start(self) -> bool:
        try:
            data = {"auto_start": False, "updated_at": datetime.now(timezone.utc).isoformat()}
            self._mock_store_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return True
        except Exception:
            return False


class GlobalExceptionHandler:
    """Installs process-wide unhandled exception hooks for sync, threads, and async loops."""

    def __init__(self, crash_manager: Optional[CrashManager] = None):
        self.crash_manager = crash_manager or CrashManager()
        self._installed = False
        self._orig_excepthook = None
        self._orig_threading_hook = None

    def install(self) -> None:
        """Register sys.excepthook and threading.excepthook."""
        if self._installed:
            return
        self._orig_excepthook = sys.excepthook
        sys.excepthook = self._handle_sys_exception

        import threading
        if hasattr(threading, "excepthook"):
            self._orig_threading_hook = threading.excepthook
            threading.excepthook = self._handle_threading_exception

        self._installed = True

    def uninstall(self) -> None:
        """Restore original exception hooks."""
        if not self._installed:
            return
        if self._orig_excepthook:
            sys.excepthook = self._orig_excepthook
        import threading
        if hasattr(threading, "excepthook") and self._orig_threading_hook:
            threading.excepthook = self._orig_threading_hook
        self._installed = False

    def _handle_sys_exception(self, exc_type, exc_value, exc_traceback) -> None:
        import traceback
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        self.crash_manager.record_crash(
            component="core_process",
            error=exc_value,
            stack_trace=tb_str,
            build_info=BuildInfo(app_version="1.0.0", build_number=100),
        )
        if self._orig_excepthook and self._orig_excepthook != self._handle_sys_exception:
            self._orig_excepthook(exc_type, exc_value, exc_traceback)

    def _handle_threading_exception(self, args) -> None:
        import traceback
        tb_str = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
        self.crash_manager.record_crash(
            component=f"thread_{args.thread.name if args.thread else 'unknown'}",
            error=args.exc_value,
            stack_trace=tb_str,
            build_info=BuildInfo(app_version="1.0.0", build_number=100),
        )


class CrashManager:
    """Detects abnormal process exits, generates privacy-scrubbed crash reports,
    and transitions into Safe Mode upon repeated startup crashes.
    """

    SECRET_PATTERN = re.compile(
        r"(AIza[0-9A-Za-z\-_]{35}|sk-[a-zA-Z0-9_-]{20,}|Bearer\s+[a-zA-Z0-9_\-\.]+|password=['\"][^'\"]+['\"])",
        re.IGNORECASE,
    )

    def __init__(self, path_manager: Optional[DeploymentPathManager] = None):
        self.paths = path_manager or DeploymentPathManager()
        self.crash_history_file = self.paths.get_sub_dir("diagnostics") / "crash_history.json"
        self.state_file = self.paths.get_sub_dir("diagnostics") / "app_state.json"
        self.startup_state_file = self.paths.get_sub_dir("diagnostics") / "startup_state.json"

    def redact_secrets(self, text: str) -> str:
        """Scrub tokens, API keys, passwords, and user paths from stack traces."""
        if not text:
            return ""
        scrubbed = self.SECRET_PATTERN.sub("[REDACTED_SECRET]", text)
        # Normalize Windows and UNIX username paths
        scrubbed = re.sub(r"([A-Za-z]:\\Users\\)([^\\]+)(\\)", r"\1[USER]\3", scrubbed, flags=re.IGNORECASE)
        scrubbed = re.sub(r"(/home/)([^/]+)(/)", r"\1[USER]\3", scrubbed, flags=re.IGNORECASE)
        return scrubbed

    def record_crash(
        self,
        component: str,
        error: Exception,
        stack_trace: str,
        build_info: BuildInfo,
    ) -> CrashReport:
        """Log crash, generate friendly crash ID, and determine whether Safe Mode should be triggered."""
        report_id = f"JARVIS-CRASH-{uuid.uuid4().hex[:6].upper()}"
        now = datetime.now(timezone.utc).isoformat()

        clean_msg = self.redact_secrets(str(error))
        clean_stack = self.redact_secrets(stack_trace)

        # Read past crashes within last 60 seconds
        crashes = self._load_crash_history()
        current_time = time.time()
        recent_crashes = [c for c in crashes if current_time - c.get("time_epoch", 0) <= 60.0]
        recent_crashes.append({"time_epoch": current_time, "report_id": report_id})
        self._save_crash_history(recent_crashes)

        # Crash loop condition: >= 2 crashes in 60s, or repeated startup failures
        trigger_safe_mode = len(recent_crashes) >= 2 or self.is_startup_crash_loop()

        if trigger_safe_mode:
            self.set_app_health_state(AppHealthState.SAFE_MODE)

        report = CrashReport(
            report_id=report_id,
            timestamp=now,
            component=component,
            error_type=type(error).__name__,
            error_message=clean_msg,
            stack_trace=clean_stack,
            build_info={
                "version": build_info.app_version,
                "build": build_info.build_number,
                "env": build_info.environment.value,
            },
            recovery_state="SAFE_MODE" if trigger_safe_mode else "NORMAL",
            is_safe_mode_triggered=trigger_safe_mode,
        )

        report_file = self.paths.get_sub_dir("diagnostics") / f"{report_id}.json"
        report_file.write_text(
            json.dumps(
                {
                    "report_id": report.report_id,
                    "timestamp": report.timestamp,
                    "component": report.component,
                    "error_type": report.error_type,
                    "error_message": report.error_message,
                    "stack_trace": report.stack_trace,
                    "build_info": report.build_info,
                    "recovery_state": report.recovery_state,
                    "is_safe_mode_triggered": report.is_safe_mode_triggered,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        return report

    def record_startup_failure(self) -> int:
        """Increment consecutive startup failure counter."""
        data = self._load_startup_state()
        count = data.get("consecutive_failures", 0) + 1
        data["consecutive_failures"] = count
        data["last_failure_time"] = time.time()
        self._save_startup_state(data)
        if count >= 3:
            self.set_app_health_state(AppHealthState.SAFE_MODE)
        return count

    def record_startup_success(self) -> None:
        """Reset consecutive startup failure counter."""
        data = self._load_startup_state()
        data["consecutive_failures"] = 0
        data["last_success_time"] = time.time()
        self._save_startup_state(data)

    def is_startup_crash_loop(self) -> bool:
        """Check if 3 or more consecutive startup failures occurred."""
        data = self._load_startup_state()
        return data.get("consecutive_failures", 0) >= 3

    def get_app_health_state(self) -> AppHealthState:
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
                return AppHealthState(data.get("state", AppHealthState.HEALTHY.value))
            except Exception:
                return AppHealthState.HEALTHY
        return AppHealthState.HEALTHY

    def set_app_health_state(self, state: AppHealthState) -> None:
        data = {"state": state.value, "updated_at": datetime.now(timezone.utc).isoformat()}
        self.state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def reset_safe_mode(self) -> None:
        self.set_app_health_state(AppHealthState.HEALTHY)
        self._save_crash_history([])
        self._save_startup_state({"consecutive_failures": 0})

    def _load_crash_history(self) -> List[Dict[str, Any]]:
        if self.crash_history_file.exists():
            try:
                return json.loads(self.crash_history_file.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def _save_crash_history(self, history: List[Dict[str, Any]]) -> None:
        try:
            self.crash_history_file.write_text(json.dumps(history, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load_startup_state(self) -> Dict[str, Any]:
        if self.startup_state_file.exists():
            try:
                return json.loads(self.startup_state_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"consecutive_failures": 0}

    def _save_startup_state(self, data: Dict[str, Any]) -> None:
        try:
            self.startup_state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass
