"""
CHARLIE Phase 14: Deployment & Production Control Actions
Assistant tools for querying deployment status, onboarding progression,
update checking, diagnostics export, and safe mode recovery.
"""

from typing import Any, Dict, List, Optional
from engine.deployment.core import DeploymentPlatform
from engine.deployment.models import OnboardingStep, ReleaseChannel, ReleaseManifest


class DeploymentControlActions:
    """Assistant action tools for DeploymentPlatform and Lifecycle Management."""

    def __init__(self, platform: Optional[DeploymentPlatform] = None):
        self.platform = platform or DeploymentPlatform()

    def get_deployment_status(self) -> Dict[str, Any]:
        """Query health state, auto-start, update channel, and onboarding status."""
        return self.platform.get_deployment_status()

    def check_environment(self) -> Dict[str, Any]:
        """Validate target Windows OS, RAM, disk, and runtimes."""
        result = self.platform.env_validator.validate_environment()
        return {
            "os": f"{result.os_name} {result.os_version} ({result.architecture})",
            "ram_gb": result.ram_gb,
            "disk_free_gb": result.disk_free_gb,
            "has_mic": result.has_microphone,
            "is_supported": result.is_supported,
            "blocking_issues": result.blocking_issues,
            "warnings": result.warnings,
        }

    def complete_onboarding_step(self, step_name: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Progress through user onboarding."""
        step = OnboardingStep(step_name)
        self.platform.onboarding_engine.complete_step(step, data)
        next_step = self.platform.onboarding_engine.get_next_pending_step()
        return {
            "completed": step_name,
            "next_pending_step": next_step.value if next_step else None,
            "is_finished": self.platform.onboarding_engine.profile.is_finished,
        }

    def check_updates(self, manifests: List[ReleaseManifest]) -> Dict[str, Any]:
        """Check for updates matching channel."""
        from config.version import APP_VERSION
        update = self.platform.update_mgr.check_updates(APP_VERSION, manifests)
        return {
            "update_available": update is not None,
            "manifest": {
                "version": update.version,
                "channel": update.channel.value,
                "checksum": update.checksum_sha256,
            }
            if update
            else None,
        }

    def export_diagnostics(self) -> Dict[str, Any]:
        """Export privacy-redacted diagnostic bundle."""
        bundle = self.platform.export_diagnostic_bundle()
        return {
            "bundle_id": bundle.bundle_id,
            "created_at": bundle.created_at,
            "health": bundle.health_summary,
            "channel": bundle.active_channel,
        }

    def toggle_safe_mode(self, enable: bool) -> Dict[str, Any]:
        """Enter or exit diagnostic safe mode."""
        if enable:
            self.platform.enter_safe_mode()
        else:
            self.platform.exit_safe_mode()
        return {"health_state": self.platform.crash_mgr.get_app_health_state().value}
