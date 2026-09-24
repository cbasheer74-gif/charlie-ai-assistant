"""
JARVIS Phase 14: Master Deployment Platform
Unifies runtime, background service, installer building, onboarding,
auto-updates, rollback, and diagnostic bundle generation.
"""

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from engine.deployment.models import (
    AppHealthState,
    BuildInfo,
    DiagnosticBundle,
    EnvironmentType,
    ReleaseChannel,
)
from engine.deployment.paths import DeploymentPathManager, PortManager
from engine.deployment.runtime import (
    CrashManager,
    JarvisUserAgent,
    SingleInstanceManager,
    StartupManager,
    WindowsServiceManager,
)
from engine.deployment.onboarding import (
    FirstRunManager,
    OnboardingEngine,
    TelemetryConsentManager,
)
from engine.deployment.migration import MigrationManager
from engine.deployment.update_rollback import (
    CodeSigningManager,
    ReleaseChannelManager,
    RollbackManager,
    UpdateManager,
)
from engine.deployment.packaging import (
    BuildManager,
    EnvironmentValidator,
    InstallerBuilder,
    UninstallManager,
)


class DeploymentPlatform:
    """Master production deployment and lifecycle coordinator."""

    def __init__(self, data_dir_override: Optional[str] = None):
        self.paths = DeploymentPathManager(data_dir_override)
        self.ports = PortManager()
        self.single_instance = SingleInstanceManager(self.paths.get_sub_dir("checkpoints"))
        self.service_mgr = WindowsServiceManager(self.paths)
        self.user_agent = JarvisUserAgent(self.paths)
        self.startup_mgr = StartupManager()
        self.crash_mgr = CrashManager(self.paths)
        self.first_run_mgr = FirstRunManager(self.paths)
        self.onboarding_engine = OnboardingEngine(self.paths)
        self.telemetry_mgr = TelemetryConsentManager(self.paths)
        self.migration_mgr = MigrationManager(self.paths)
        self.channel_mgr = ReleaseChannelManager(self.paths)
        self.signing_mgr = CodeSigningManager()
        self.rollback_mgr = RollbackManager(self.paths)
        self.update_mgr = UpdateManager(self.paths)
        self.build_mgr = BuildManager()
        self.env_validator = EnvironmentValidator()
        # Generated installer drafts belong to the selected deployment data
        # directory. Using the repository root here let runtime/tests overwrite
        # the production installer.iss file.
        self.installer_builder = InstallerBuilder(self.paths.data_dir)
        self.uninstall_mgr = UninstallManager(self.paths)

    def initialize(self) -> Dict[str, Any]:
        """Bootstrap production runtime."""
        # 1. Check environment
        env_check = self.env_validator.validate_environment()

        # 2. Check migrations
        migration_res = self.migration_mgr.run_pending_migrations()

        # 3. Check health state / safe mode
        health_state = self.crash_mgr.get_app_health_state()

        # 4. Check first run
        is_first_run = self.first_run_mgr.is_first_run()

        return {
            "status": "INITIALIZED",
            "health_state": health_state.value,
            "is_first_run": is_first_run,
            "environment_supported": env_check.is_supported,
            "migrations": migration_res,
            "active_channel": self.channel_mgr.get_channel().value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_deployment_status(self) -> Dict[str, Any]:
        return {
            "health_state": self.crash_mgr.get_app_health_state().value,
            "is_auto_start": self.startup_mgr.is_auto_start_enabled(),
            "channel": self.channel_mgr.get_channel().value,
            "telemetry_level": self.telemetry_mgr.get_consent_level().value,
            "data_dir": str(self.paths.data_dir),
            "onboarding_completed": self.onboarding_engine.profile.is_finished,
        }

    def export_diagnostic_bundle(self, build_info: Optional[BuildInfo] = None) -> DiagnosticBundle:
        """Exports a privacy-safe, redacted diagnostic bundle."""
        bundle_id = f"DIAG_{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc).isoformat()

        # Collect and sanitize logs
        logs = []
        log_file = self.paths.get_log_file()
        if log_file.exists():
            try:
                raw_lines = log_file.read_text(encoding="utf-8").splitlines()[-50:]
                logs = [self.crash_mgr.redact_secrets(line) for line in raw_lines]
            except Exception:
                pass

        bundle = DiagnosticBundle(
            bundle_id=bundle_id,
            created_at=now,
            build_info={
                "version": build_info.app_version if build_info else "1.0.0",
                "build": build_info.build_number if build_info else 100,
                "env": build_info.environment.value if build_info else "PRODUCTION",
            },
            health_summary={
                "state": self.crash_mgr.get_app_health_state().value,
                "applied_migrations": self.migration_mgr.get_applied_migrations(),
            },
            service_status={
                "background_service": self.service_mgr.is_running,
                "tray_active": self.user_agent.tray_active,
                "auto_start": self.startup_mgr.is_auto_start_enabled(),
            },
            redacted_logs=logs,
            active_channel=self.channel_mgr.get_channel().value,
        )

        out_file = self.paths.get_sub_dir("diagnostics") / f"{bundle_id}.json"
        out_file.write_text(
            json.dumps(
                {
                    "bundle_id": bundle.bundle_id,
                    "created_at": bundle.created_at,
                    "build_info": bundle.build_info,
                    "health_summary": bundle.health_summary,
                    "service_status": bundle.service_status,
                    "redacted_logs": bundle.redacted_logs,
                    "active_channel": bundle.active_channel,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return bundle

    def enter_safe_mode(self) -> None:
        self.crash_mgr.set_app_health_state(AppHealthState.SAFE_MODE)

    def exit_safe_mode(self) -> None:
        self.crash_mgr.reset_safe_mode()
