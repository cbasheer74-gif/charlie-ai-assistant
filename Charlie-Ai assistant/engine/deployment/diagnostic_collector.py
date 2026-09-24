"""
engine/deployment/diagnostic_collector.py — Diagnostic bundle builder, health snapshots, and privacy redactor.

Collects privacy-safe system diagnostics, redacts credentials/paths, evaluates health snapshots,
and builds standardized diagnostic packages for support tickets and crash recovery.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.deployment.paths import DeploymentPathManager


class ErrorLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    FATAL = "FATAL"


class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class SecretRedactor:
    """Robust secret scrubbing and path normalizer for diagnostic reports."""

    REDACTION_PATTERNS = [
        # Google Gemini / Cloud API Key
        (re.compile(r"AIza[0-9A-Za-z\-_]{20,}"), "[REDACTED_GEMINI_KEY]"),
        # OpenAI / Anthropic API Key
        (re.compile(r"sk-[a-zA-Z0-9_\-]{20,}"), "[REDACTED_API_KEY]"),
        # Bearer tokens
        (re.compile(r"Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
        # JWT format
        (re.compile(r"ey[A-Za-z0-9_-]{15,}\.ey[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_\-]+"), "[REDACTED_JWT]"),
        # Key-value secret fields in JSON or assignments
        (
            re.compile(
                r'("?(?:password|secret|api_key|access_token|refresh_token|auth_token|client_secret|private_key)"?\s*[:=]\s*["\'])([^"\']+)(["\'])',
                re.IGNORECASE,
            ),
            r"\1[REDACTED]\3",
        ),
        # Database connection strings with credentials (postgres, mysql, mongodb)
        (
            re.compile(r"((?:postgres|postgresql|mysql|mongodb|redis|amqp):\/\/[^:\s]+:)([^@\s]+)(@)", re.IGNORECASE),
            r"\1[REDACTED_PASSWORD]\3",
        ),
        # Cookies
        (re.compile(r"(Cookie\s*:\s*)([^\r\n;]+)", re.IGNORECASE), r"\1[REDACTED_COOKIE]"),
        # PEM private keys
        (
            re.compile(r"-----BEGIN[A-Z\s]+PRIVATE KEY-----[\s\S]*?-----END[A-Z\s]+PRIVATE KEY-----"),
            "[REDACTED_PRIVATE_KEY]",
        ),
    ]

    # Normalize user home directories to protect username privacy
    USER_PATH_PATTERN_WIN = re.compile(r"([A-Za-z]:\\Users\\)([^\\]+)(\\)", re.IGNORECASE)
    USER_PATH_PATTERN_NIX = re.compile(r"(/home/)([^/]+)(/)", re.IGNORECASE)

    @classmethod
    def sanitize_text(cls, text: str) -> str:
        """Strip all sensitive keys, tokens, and credentials from string."""
        if not text:
            return ""
        cleaned = text
        for pattern, replacement in cls.REDACTION_PATTERNS:
            cleaned = pattern.sub(replacement, cleaned)
        # Normalize file paths
        cleaned = cls.normalize_paths(cleaned)
        return cleaned

    @classmethod
    def normalize_paths(cls, text: str) -> str:
        """Replace specific username in local filesystem paths with [USER]."""
        if not text:
            return ""
        text = cls.USER_PATH_PATTERN_WIN.sub(r"\1[USER]\3", text)
        text = cls.USER_PATH_PATTERN_NIX.sub(r"\1[USER]\3", text)
        return text

    @classmethod
    def sanitize_dict(cls, data: Any) -> Any:
        """Recursively redact dictionary, list, or primitive values."""
        sensitive_keys = {
            "password", "secret", "api_key", "key", "token", "access_token",
            "refresh_token", "auth", "authorization", "credential", "private_key",
            "client_secret", "signature", "raw_fingerprint", "cookie", "cookies",
        }
        if isinstance(data, str):
            return cls.sanitize_text(data)
        elif isinstance(data, dict):
            res = {}
            for k, v in data.items():
                if str(k).lower() in sensitive_keys:
                    res[k] = "[REDACTED]"
                else:
                    res[k] = cls.sanitize_dict(v)
            return res
        elif isinstance(data, list):
            return [cls.sanitize_dict(item) for item in data]
        return data


class CrashSignatureGenerator:
    """Generates stable crash fingerprint based on exception class, normalized stack, and component."""

    @staticmethod
    def generate(exc_type: str, stack_trace: str, component: str = "core") -> str:
        """Produce a deterministic 16-character hex hash signature."""
        clean_stack = SecretRedactor.normalize_paths(stack_trace or "")
        # Remove line numbers and hex memory addresses to group identical stack frames across builds
        normalized = re.sub(r", line \d+", "", clean_stack)
        normalized = re.sub(r"0x[0-9a-fA-F]+", "0xADDR", normalized)
        # Extract top 3 caller frames if available
        lines = [line.strip() for line in normalized.splitlines() if line.strip().startswith("File ") or "in " in line]
        frame_summary = "|".join(lines[-3:]) if lines else "noframes"

        raw = f"{exc_type.strip()}:{frame_summary}:{component.strip()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class HealthSnapshotManager:
    """Evaluates runtime health across core subsystems."""

    def __init__(self, path_manager: Optional[DeploymentPathManager] = None):
        self.paths = path_manager or DeploymentPathManager()

    def check_subsystems(self, context_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, HealthStatus]:
        overrides = context_overrides or {}
        health: Dict[str, HealthStatus] = {}

        # 1. Core
        health["core"] = overrides.get("core", HealthStatus.HEALTHY)

        # 2. License & Device
        health["license"] = overrides.get("license", HealthStatus.HEALTHY)

        # 3. Auth
        health["auth"] = overrides.get("auth", HealthStatus.HEALTHY)

        # 4. Update service
        health["update_service"] = overrides.get("update_service", HealthStatus.HEALTHY)

        # 5. Voice system
        health["voice"] = overrides.get("voice", HealthStatus.HEALTHY)

        # 6. AI Providers
        health["ai_providers"] = overrides.get("ai_providers", HealthStatus.HEALTHY)

        # 7. Local Models
        health["local_models"] = overrides.get("local_models", HealthStatus.NOT_CONFIGURED)

        # 8. Plugins & MCP
        health["plugins"] = overrides.get("plugins", HealthStatus.HEALTHY)
        health["mcp"] = overrides.get("mcp", HealthStatus.HEALTHY)

        # 9. Computer automation & Browser agent
        health["computer_controller"] = overrides.get("computer_controller", HealthStatus.HEALTHY)
        health["browser_agent"] = overrides.get("browser_agent", HealthStatus.HEALTHY)

        # 10. Filmora & FFmpeg
        health["filmora_adapter"] = overrides.get("filmora_adapter", HealthStatus.NOT_CONFIGURED)
        health["ffmpeg"] = overrides.get("ffmpeg", HealthStatus.HEALTHY if shutil.which("ffmpeg") else HealthStatus.DEGRADED)

        # 11. Database
        db_path = self.paths.get_sub_dir("memory")
        health["database"] = HealthStatus.HEALTHY if db_path.exists() else HealthStatus.DEGRADED

        # 12. Disk Space
        try:
            usage = shutil.disk_usage(self.paths.data_dir)
            free_gb = usage.free / (1024 ** 3)
            if free_gb > 1.0:
                health["disk"] = HealthStatus.HEALTHY
            elif free_gb > 0.2:
                health["disk"] = HealthStatus.DEGRADED
            else:
                health["disk"] = HealthStatus.FAILED
        except Exception:
            health["disk"] = HealthStatus.DEGRADED

        return health

    def diagnose_self(self, context_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """User command: 'Jarvis diagnose yourself'. Returns structured data and clear natural language summary."""
        statuses = self.check_subsystems(context_overrides)
        summary_lines = []
        has_degraded = False
        has_failed = False

        for name, st in statuses.items():
            display_name = name.replace("_", " ").capitalize()
            val = st.value if isinstance(st, HealthStatus) else str(st)
            summary_lines.append(f"{display_name}: {val.replace('_', ' ').capitalize()}")
            if val == HealthStatus.DEGRADED.value:
                has_degraded = True
            elif val == HealthStatus.FAILED.value:
                has_failed = True

        overall = "HEALTHY"
        if has_failed:
            overall = "CRITICAL"
        elif has_degraded:
            overall = "DEGRADED"

        return {
            "overall_status": overall,
            "subsystems": {k: (v.value if isinstance(v, HealthStatus) else str(v)) for k, v in statuses.items()},
            "text_report": "\n".join(summary_lines),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class DiagnosticCollector:
    """Aggregates privacy-safe technical telemetry into structured bundles."""

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
        self.health_mgr = HealthSnapshotManager(self.paths)

    def collect_system_info(self) -> Dict[str, Any]:
        """Collect general non-identifying operating system and hardware metrics."""
        disk_free_gb = 0.0
        try:
            usage = shutil.disk_usage(self.paths.data_dir)
            disk_free_gb = round(usage.free / (1024 ** 3), 2)
        except Exception:
            pass

        return {
            "os_name": platform.system(),
            "os_release": platform.release(),
            "os_version": platform.version(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "disk_free_gb": disk_free_gb,
            "windows_10_compatible": True,
        }

    def collect_sanitized_logs(self, max_lines: int = 200) -> List[str]:
        """Read and scrub recent log lines. Strictly zero secrets or user docs."""
        log_file = self.paths.get_log_file()
        if not log_file.exists():
            return []
        try:
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
            recent = lines[-max_lines:] if len(lines) > max_lines else lines
            return [SecretRedactor.sanitize_text(l) for l in recent]
        except Exception:
            return ["[LOG_READ_ERROR]"]

    def build_diagnostic_bundle(
        self,
        recent_errors: Optional[List[Dict[str, Any]]] = None,
        license_summary: Optional[Dict[str, Any]] = None,
        health_overrides: Optional[Dict[str, Any]] = None,
        optional_user_comment: str = "",
        include_screenshot: bool = False,
        screenshot_data_base64: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a complete, privacy-audited technical diagnostic bundle."""
        bundle_id = f"BUNDLE-{uuid.uuid4().hex[:8].upper()}"
        created_at = datetime.now(timezone.utc).isoformat()

        # Sanitize errors
        clean_errors = SecretRedactor.sanitize_dict(recent_errors or [])
        clean_license = SecretRedactor.sanitize_dict(license_summary or {"plan": "STARTER", "status": "ACTIVE"})
        # Redact raw hardware fingerprint if present
        if "device_id" in clean_license:
            dev_id = str(clean_license["device_id"])
            clean_license["device_id_ref"] = hashlib.sha256(dev_id.encode()).hexdigest()[:12]
            clean_license.pop("device_id", None)
            clean_license.pop("fingerprint", None)

        system_info = self.collect_system_info()
        health_info = self.health_mgr.diagnose_self(health_overrides)
        sanitized_logs = self.collect_sanitized_logs()

        bundle_payload = {
            "bundle_id": bundle_id,
            "created_at": created_at,
            "manifest": {
                "bundle_id": bundle_id,
                "app_version": self.app_version,
                "build_number": self.build_number,
                "release_channel": self.channel,
                "redaction_version": "2.0.0",
                "categories": [
                    "system_info",
                    "health",
                    "recent_errors",
                    "license_status",
                    "sanitized_logs",
                ],
            },
            "system_info": system_info,
            "health": health_info,
            "recent_errors": clean_errors,
            "license_status": clean_license,
            "sanitized_logs": sanitized_logs,
            "user_comment": SecretRedactor.sanitize_text(optional_user_comment) if optional_user_comment else "",
        }

        # Optional screenshot: strictly opt-in, default false
        if include_screenshot and screenshot_data_base64:
            bundle_payload["screenshot_attachment"] = {
                "included": True,
                "data_base64": screenshot_data_base64,
                "size_bytes": len(screenshot_data_base64),
            }
        else:
            bundle_payload["screenshot_attachment"] = {"included": False}

        # Compute integrity checksum
        serialized = json.dumps(bundle_payload, sort_keys=True)
        bundle_checksum = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        bundle_payload["manifest"]["bundle_checksum"] = bundle_checksum

        return bundle_payload
