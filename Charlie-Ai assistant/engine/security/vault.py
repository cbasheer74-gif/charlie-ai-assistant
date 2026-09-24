"""engine/security/vault.py — Credential Vault and Secret Redaction Engine."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from cryptography.fernet import Fernet


class SecretRedactionEngine:
    """Scans and redacts API keys, JWTs, OAuth tokens, private keys, connection strings, and passwords."""

    REDACTION_PATTERNS = [
        # OpenAI keys
        (re.compile(r"sk-[a-zA-Z0-9_-]{20,}", re.I), lambda m: f"sk-****{m.group(0)[-4:]}"),
        # Anthropic keys
        (re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}", re.I), lambda m: f"sk-ant-****{m.group(0)[-4:]}"),
        # Google API keys
        (re.compile(r"AIza[0-9A-Za-z-_]{35}", re.I), lambda m: f"AIza****{m.group(0)[-4:]}"),
        # Generic Bearer Tokens
        (re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{25,}", re.I), lambda m: "Bearer ****[REDACTED]"),
        # Private Keys
        (re.compile(r"-----BEGIN[ A-Z0-9_-]*PRIVATE KEY-----[\s\S]*?-----END[ A-Z0-9_-]*PRIVATE KEY-----"), lambda m: "[REDACTED_PRIVATE_KEY]"),
        # Connection Strings with passwords
        (re.compile(r"(postgres|mysql|mongodb|redis):\/\/([^:]+):([^@]+)@"), lambda m: f"{m.group(1)}://{m.group(2)}:****@"),
        # Password parameters in command strings
        (re.compile(r"(?i)(password|passwd|secret|api_key|token)\s*=\s*['\"]?([^'\"\s]+)['\"]?"), lambda m: f"{m.group(1)}=****"),
    ]

    @classmethod
    def redact(cls, text: str) -> str:
        if not text:
            return ""
        result = text
        for pattern, replacement in cls.REDACTION_PATTERNS:
            result = pattern.sub(replacement, result)
        return result


class CredentialVault:
    """Encrypted storage for sensitive API keys, OAuth tokens, and database credentials."""

    def __init__(self, vault_dir: Optional[Path] = None):
        if vault_dir is None:
            v_dir = Path.home() / ".jarvis" / "vault"
            v_dir.mkdir(parents=True, exist_ok=True)
            self.vault_path = v_dir / "credentials.vault"
        else:
            self.vault_path = Path(vault_dir) / "credentials.vault"
            self.vault_path.parent.mkdir(parents=True, exist_ok=True)

        self._encryption_key = self._derive_machine_key()
        self._cache: Dict[str, str] = {}
        self._load()

    def _derive_machine_key(self) -> bytes:
        # Machine-bound key seed (OS user + machine specific salt)
        user = os.environ.get("USERNAME", "jarvis_user")
        seed = f"jarvis_sec_vault_{user}_{os.name}".encode("utf-8")
        key = hashlib.sha256(seed).digest()
        return base64.urlsafe_b64encode(key)

    def _encrypt(self, data: bytes) -> bytes:
        return Fernet(self._encryption_key).encrypt(data)

    def _decrypt(self, data: bytes) -> bytes:
        try:
            return Fernet(self._encryption_key).decrypt(data)
        except Exception:
            # Fallback for legacy XOR stored secrets
            user = os.environ.get("USERNAME", "jarvis_user")
            legacy_key = hashlib.sha256(f"jarvis_sec_vault_{user}_{os.name}".encode("utf-8")).digest()
            return bytes([b ^ legacy_key[i % len(legacy_key)] for i, b in enumerate(data)])

    def _load(self) -> None:
        if not self.vault_path.exists():
            return
        try:
            raw = self.vault_path.read_bytes()
            if not raw:
                return
            decrypted = self._decrypt(raw)
            self._cache = json.loads(decrypted.decode("utf-8"))
        except Exception:
            self._cache = {}

    def _save(self) -> None:
        raw = json.dumps(self._cache).encode("utf-8")
        encrypted = self._encrypt(raw)
        self.vault_path.write_bytes(encrypted)

    def store_secret(self, secret_id: str, raw_value: str) -> str:
        """Stores secret and returns opaque SECRET_ID token."""
        self._cache[secret_id] = raw_value
        self._save()
        return secret_id

    def resolve_secret(self, secret_id: str) -> Optional[str]:
        """Resolves secret only when required by trusted tool execution."""
        return self._cache.get(secret_id)

    def has_secret(self, secret_id: str) -> bool:
        return secret_id in self._cache

    def remove_secret(self, secret_id: str) -> bool:
        if secret_id in self._cache:
            del self._cache[secret_id]
            self._save()
            return True
        return False
