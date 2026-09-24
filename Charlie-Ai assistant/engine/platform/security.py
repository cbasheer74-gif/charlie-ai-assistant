"""
JARVIS Phase 12: Extension Security, Sandbox & Credential Binding
Enforces strict sandboxing, domain allowlists, path isolation, and scoped credential injection.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from .models import ExtensionManifest, PermissionManifest

logger = logging.getLogger("jarvis.platform.security")


class PluginSecurityScanner:
    """Scans extension manifests and metadata before installation or activation."""

    FORBIDDEN_PATTERNS = [
        "rmdir /s",
        "format c:",
        "powershell -encodedcommand",
        "invoke-expression",
        "drop table",
        "truncate table",
        "bypass_security",
    ]

    def scan_manifest(self, manifest: ExtensionManifest) -> Tuple[bool, List[str]]:
        """Scans manifest for security issues or undeclared permissions."""
        issues = []

        if not manifest.id or not manifest.name:
            issues.append("Manifest missing mandatory id or name.")

        if not manifest.permissions:
            issues.append("Manifest missing permission declaration.")

        # Check for empty tools in TOOL/CONNECTOR extension
        if manifest.type.value in ("TOOL", "CONNECTOR") and not manifest.tools:
            issues.append(f"Extension type {manifest.type.value} must declare at least one tool.")

        # Check for wildcard network access on non-system extension
        if "*" in manifest.permissions.network and not manifest.is_dev_mode:
            issues.append("Wildcard network access '*' is prohibited for production plugins.")

        # Check for suspicious command strings
        for desc in [manifest.description, manifest.entrypoint]:
            low = desc.lower()
            if any(p in low for p in self.FORBIDDEN_PATTERNS):
                issues.append(f"Suspicious pattern detected in manifest metadata: '{desc}'")

        is_safe = len(issues) == 0
        if not is_safe:
            logger.warning(f"Plugin {manifest.id} failed security scan: {issues}")
        return is_safe, issues


class ExtensionSandbox:
    """Runtime sandbox enforcing network domain and filesystem isolation."""

    def __init__(self, manifest: ExtensionManifest):
        self.manifest = manifest
        self.permissions = manifest.permissions

    def check_network_access(self, target_domain: str) -> Tuple[bool, str]:
        """Checks if target domain is explicitly declared in permission manifest."""
        if not self.permissions.network:
            return False, f"Network access denied: Plugin '{self.manifest.id}' declared NO network permissions."

        if self.permissions.allows_domain(target_domain):
            return True, "Domain allowed."

        msg = f"Network access blocked: Domain '{target_domain}' is not in plugin allowlist {self.permissions.network}."
        logger.error(msg)
        return False, msg

    def check_file_access(self, file_path: str, mode: str = "read") -> Tuple[bool, str]:
        """Checks if file path complies with plugin filesystem scope."""
        norm = file_path.replace("\\", "/").lower()

        # Always block windows system internals
        if any(sys_dir in norm for sys_dir in ["c:/windows", "system32", "regedit"]):
            return False, f"Filesystem access blocked: Path '{file_path}' is protected system directory."

        # Check declared scopes
        if not self.permissions.filesystem:
            return False, f"Filesystem access denied: Plugin '{self.manifest.id}' declared NO filesystem permissions."

        if not self.permissions.allows_file_path(file_path, mode=mode):
            return False, f"Filesystem access blocked for path '{file_path}'."

        return True, "File path allowed."


class CredentialBindingManager:
    """Maps declared secret references to CredentialVault without leaking unrelated secrets."""

    def __init__(self, credential_vault: Optional[Any] = None):
        self.vault = credential_vault
        # Mock storage for testing when vault not bound
        self._mock_vault: Dict[str, str] = {
            "github_token": "ghp_mock_token_1234567890",
            "slack_token": "xoxb_mock_slack_987654321",
            "crm_api_key": "crm_mock_secret_key_5544",
            "db_password": "super_secret_db_pass_123",
        }

    def get_scoped_credentials(self, manifest: ExtensionManifest) -> Dict[str, str]:
        """Returns only the credentials explicitly declared in manifest.credentials."""
        scoped = {}
        for cred_name in manifest.credentials:
            if cred_name in self.manifest_declared_credentials(manifest):
                val = self._resolve_secret(cred_name)
                if val:
                    scoped[cred_name] = val
        return scoped

    def manifest_declared_credentials(self, manifest: ExtensionManifest) -> List[str]:
        return manifest.permissions.allowed_credentials or manifest.credentials

    def _resolve_secret(self, cred_name: str) -> Optional[str]:
        if self.vault and hasattr(self.vault, "get_secret"):
            return self.vault.get_secret(cred_name)
        return self._mock_vault.get(cred_name)
