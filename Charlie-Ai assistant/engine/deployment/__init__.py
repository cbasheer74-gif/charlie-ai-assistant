"""
JARVIS Phase 14: Deployment Platform Package
"""

from engine.deployment.models import (
    AppHealthState,
    BuildInfo,
    CrashReport,
    DiagnosticBundle,
    EnvironmentCheckResult,
    EnvironmentType,
    InstallMode,
    OnboardingProfile,
    OnboardingStep,
    ReleaseChannel,
    ReleaseManifest,
    ServiceConfig,
    TelemetryLevel,
    UpdatePolicy,
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
from engine.deployment.core import DeploymentPlatform

__all__ = [
    "AppHealthState",
    "BuildInfo",
    "CrashReport",
    "DiagnosticBundle",
    "EnvironmentCheckResult",
    "EnvironmentType",
    "InstallMode",
    "OnboardingProfile",
    "OnboardingStep",
    "ReleaseChannel",
    "ReleaseManifest",
    "ServiceConfig",
    "TelemetryLevel",
    "UpdatePolicy",
    "DeploymentPathManager",
    "PortManager",
    "CrashManager",
    "JarvisUserAgent",
    "SingleInstanceManager",
    "StartupManager",
    "WindowsServiceManager",
    "FirstRunManager",
    "OnboardingEngine",
    "TelemetryConsentManager",
    "MigrationManager",
    "CodeSigningManager",
    "ReleaseChannelManager",
    "RollbackManager",
    "UpdateManager",
    "BuildManager",
    "EnvironmentValidator",
    "InstallerBuilder",
    "UninstallManager",
    "DeploymentPlatform",
]
