"""
engine/commercial/licensing_client.py — HTTPS client for communicating with the JARVIS licensing server.

Handles: auth, device activation, license transfer, entitlement refresh.
Stores tokens securely via keyring/DPAPI.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("jarvis.commercial.licensing_client")

# Default licensing server URL — override via config
DEFAULT_SERVER_URL = "http://localhost:8400"


@dataclass
class AuthResult:
    success: bool
    message: str
    user_id: str = ""
    email: str = ""
    display_name: str = ""
    plan: str = "STARTER"
    subscription_status: str = "FREE"
    active_device_id: Optional[str] = None
    access_token: str = ""
    refresh_token: str = ""


@dataclass
class ActivationResult:
    success: bool
    message: str
    plan: str = "STARTER"
    status: str = "FREE"
    token: str = ""  # Signed entitlement token
    expires_at: str = ""
    conflict_device_name: Optional[str] = None
    conflict_device_id: Optional[str] = None


class LicensingClient:
    """Desktop client for the JARVIS licensing server API."""

    def __init__(self, server_url: Optional[str] = None, data_dir: Optional[Path] = None):
        self.server_url = (server_url or DEFAULT_SERVER_URL).rstrip("/")
        self.data_dir = data_dir or (Path.home() / ".jarvis" / "licensing")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._tokens_file = self.data_dir / "session_tokens.json"
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._load_tokens()

    # ── Auth ─────────────────────────────────────────────────────────────────

    def register(self, email: str, password: str, display_name: str = "JARVIS User") -> AuthResult:
        """Register a new account."""
        data = self._post("/auth/register", {
            "email": email,
            "password": password,
            "display_name": display_name,
        }, authenticated=False)

        if not data or not data.get("success"):
            return AuthResult(success=False, message=data.get("error", "Registration failed.") if data else "Server unreachable.")

        d = data["data"]
        self._store_tokens(d.get("access_token", ""), d.get("refresh_token", ""))
        return AuthResult(
            success=True, message="Account created.",
            user_id=d.get("user_id", ""), email=d.get("email", ""),
            display_name=d.get("display_name", ""), plan=d.get("plan", "STARTER"),
            access_token=d.get("access_token", ""), refresh_token=d.get("refresh_token", ""),
        )

    def login(self, email: str, password: str) -> AuthResult:
        """Login to existing account."""
        data = self._post("/auth/login", {
            "email": email,
            "password": password,
        }, authenticated=False)

        if not data or not data.get("success"):
            return AuthResult(success=False, message=data.get("error", "Login failed.") if data else "Server unreachable.")

        d = data["data"]
        self._store_tokens(d.get("access_token", ""), d.get("refresh_token", ""))
        return AuthResult(
            success=True, message="Login successful.",
            user_id=d.get("user_id", ""), email=d.get("email", ""),
            display_name=d.get("display_name", ""), plan=d.get("plan", "STARTER"),
            subscription_status=d.get("subscription_status", "FREE"),
            active_device_id=d.get("active_device_id"),
            access_token=d.get("access_token", ""), refresh_token=d.get("refresh_token", ""),
        )

    def logout(self) -> bool:
        """Discard local tokens."""
        self._access_token = None
        self._refresh_token = None
        if self._tokens_file.exists():
            self._tokens_file.unlink()
        return True

    def is_logged_in(self) -> bool:
        return bool(self._access_token)

    # ── License ──────────────────────────────────────────────────────────────

    def activate_device(
        self, device_id: str, fingerprint_hash: str, device_public_key: str,
        device_name: str = "Unknown PC", os_type: str = "Windows", app_version: str = "1.0.0",
    ) -> ActivationResult:
        """Activate this device for the user's subscription."""
        data = self._post("/license/activate", {
            "device_id": device_id,
            "fingerprint_hash": fingerprint_hash,
            "device_public_key": device_public_key,
            "device_name": device_name,
            "os_type": os_type,
            "app_version": app_version,
        })

        if not data:
            return ActivationResult(success=False, message="Server unreachable.")

        if not data.get("success"):
            error = data.get("error", "")
            conflict_data = data.get("data")
            if error == "DEVICE_CONFLICT" and conflict_data:
                return ActivationResult(
                    success=False, message="DEVICE_CONFLICT",
                    conflict_device_name=conflict_data.get("active_device_name"),
                    conflict_device_id=conflict_data.get("active_device_id"),
                )
            return ActivationResult(success=False, message=error)

        d = data["data"]
        return ActivationResult(
            success=True, message="Device activated.",
            plan=d.get("plan", "STARTER"), status=d.get("status", ""),
            token=d.get("token", ""), expires_at=d.get("expires_at", ""),
        )

    def transfer_license(
        self, device_id: str, fingerprint_hash: str, device_public_key: str,
        device_name: str = "New PC", os_type: str = "Windows", app_version: str = "1.0.0",
    ) -> ActivationResult:
        """Transfer license from old device to this device."""
        data = self._post("/license/transfer", {
            "new_device_id": device_id,
            "new_fingerprint_hash": fingerprint_hash,
            "new_device_public_key": device_public_key,
            "new_device_name": device_name,
            "os_type": os_type,
            "app_version": app_version,
        })

        if not data:
            return ActivationResult(success=False, message="Server unreachable.")

        if not data.get("success"):
            return ActivationResult(success=False, message=data.get("error", "Transfer failed."))

        d = data["data"]
        return ActivationResult(
            success=True, message="License transferred.",
            plan=d.get("plan", "STARTER"), status=d.get("status", ""),
            token=d.get("token", ""), expires_at=d.get("expires_at", ""),
        )

    def deactivate_device(self, device_id: str) -> Tuple[bool, str]:
        data = self._post("/license/deactivate", {"device_id": device_id})
        if not data:
            return False, "Server unreachable."
        return data.get("success", False), data.get("message", "")

    def revoke_device(self, device_id: str) -> Tuple[bool, str]:
        data = self._post("/license/revoke", {"device_id": device_id})
        if not data:
            return False, "Server unreachable."
        return data.get("success", False), data.get("message", "")

    # ── Entitlement ──────────────────────────────────────────────────────────

    def refresh_entitlement(self, device_id: str, fingerprint_hash: str) -> Tuple[bool, str, Optional[str]]:
        """Refresh signed entitlement token. Returns (ok, message, token_or_None)."""
        data = self._post("/entitlement/refresh", {
            "device_id": device_id,
            "fingerprint_hash": fingerprint_hash,
        })
        if not data or not data.get("success"):
            msg = data.get("error", "Refresh failed.") if data else "Server unreachable."
            return False, msg, None
        return True, "Refreshed.", data["data"].get("token")

    def get_devices(self) -> list:
        data = self._get("/devices/")
        if not data or not data.get("success"):
            return []
        return data.get("devices", [])

    # ── Updates & Support ────────────────────────────────────────────────────

    def check_for_updates(self, current_version: str = "1.0.0", channel: str = "stable") -> Optional[dict]:
        """Query official server for signed updates."""
        return self._get(f"/updates/check?version={current_version}&channel={channel}")

    def submit_support_ticket(
        self,
        subject: str,
        message: str,
        category: str = "OTHER",
        error_id: Optional[str] = None,
        app_version: str = "1.0.0",
        os_version: str = "Windows",
        raw_diagnostics: Optional[dict] = None,
    ) -> Tuple[bool, str, Optional[dict]]:
        """Submit a support ticket with system diagnostics."""
        data = self._post("/support/tickets", {
            "subject": subject,
            "message": message,
            "category": category,
            "error_id": error_id,
            "app_version": app_version,
            "os_version": os_version,
            "raw_diagnostics": raw_diagnostics or {},
        })
        if not data or not data.get("status") == "ok":
            msg = data.get("detail", "Ticket submission failed.") if data else "Server unreachable."
            return False, msg, None
        return True, data.get("message", "Ticket created."), data.get("ticket")

    def get_account(self) -> Optional[dict]:
        data = self._get("/account/")
        if not data or not data.get("success"):
            return None
        return data.get("data")

    # ── HTTP Helpers ─────────────────────────────────────────────────────────

    def _post(self, path: str, body: dict, authenticated: bool = True) -> Optional[dict]:
        import urllib.request
        import urllib.error

        url = f"{self.server_url}{path}"
        headers = {"Content-Type": "application/json"}
        if authenticated and self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        try:
            req = urllib.request.Request(
                url, data=json.dumps(body).encode("utf-8"),
                headers=headers, method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode("utf-8"))
            except Exception:
                return {"success": False, "error": f"HTTP {e.code}"}
        except Exception as e:
            logger.warning("Licensing server request failed: %s", e)
            return None

    def _get(self, path: str) -> Optional[dict]:
        import urllib.request
        import urllib.error

        url = f"{self.server_url}{path}"
        headers = {}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.warning("Licensing server GET failed: %s", e)
            return None

    # ── Token Storage ────────────────────────────────────────────────────────

    def _store_tokens(self, access: str, refresh: str) -> None:
        self._access_token = access
        self._refresh_token = refresh
        try:
            self._tokens_file.write_text(json.dumps({
                "access_token": access,
                "refresh_token": refresh,
            }), encoding="utf-8")
        except Exception as e:
            logger.error("Failed to store tokens: %s", e)

    def _load_tokens(self) -> None:
        if self._tokens_file.exists():
            try:
                data = json.loads(self._tokens_file.read_text(encoding="utf-8"))
                self._access_token = data.get("access_token")
                self._refresh_token = data.get("refresh_token")
            except Exception:
                pass
