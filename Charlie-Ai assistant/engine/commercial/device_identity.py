"""
engine/commercial/device_identity.py — Privacy-Safe Device Identity Manager.

Generates and manages:
  1. RSA-2048 device keypair (private key stored via DPAPI/keyring)
  2. Privacy-safe device fingerprint (SHA256 of MachineGuid + public key hash + salt)
  3. Friendly device name from Windows computer name

NEVER collects: files, browser data, MAC/IP, location, photos, clipboard, contacts.
ONLY uses: Windows MachineGuid (from registry), app-generated keypair, OS class info.
"""

from __future__ import annotations

import hashlib
import logging
import os
import platform
import uuid
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("jarvis.commercial.device_identity")

# Product salt — not a secret, just prevents cross-product fingerprint reuse
PRODUCT_SALT = "jarvis_mark_liv_2026"


class DeviceIdentityManager:
    """Privacy-respecting device identity for license binding.

    Survives:
      - RAM/GPU/USB/monitor changes (uses MachineGuid, not hardware serial inventory)
      - App reinstall on same OS install (MachineGuid persists)

    Requires reactivation:
      - Clean Windows reinstall (new MachineGuid)
      - Moving to different physical machine
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or (Path.home() / ".jarvis" / "identity")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._device_id_file = self.data_dir / "device_id.txt"
        self._public_key_file = self.data_dir / "device_public.pem"

    # ── Device ID ────────────────────────────────────────────────────────────

    def get_device_id(self) -> str:
        """Returns stable device ID. Generated once per install, persisted."""
        if self._device_id_file.exists():
            return self._device_id_file.read_text(encoding="utf-8").strip()

        device_id = f"dev_{uuid.uuid4().hex}"
        self._device_id_file.write_text(device_id, encoding="utf-8")
        return device_id

    # ── Keypair ──────────────────────────────────────────────────────────────

    def get_or_create_keypair(self) -> Tuple[str, str]:
        """Returns (public_key_pem, private_key_pem). Creates if not exists.

        Private key is stored locally. In production, use DPAPI/keyring.
        """
        private_key_path = self.data_dir / "device_private.pem"

        if self._public_key_file.exists() and private_key_path.exists():
            public_pem = self._public_key_file.read_text(encoding="utf-8")
            private_pem = self._load_private_key_secure(private_key_path)
            if private_pem:
                return public_pem, private_pem

        # Generate new keypair
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import rsa

            private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

            private_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ).decode("utf-8")

            public_pem = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode("utf-8")

        except ImportError:
            # Fallback: generate placeholder keys if cryptography not installed
            logger.warning("cryptography library not available. Using placeholder keys.")
            private_pem = f"PLACEHOLDER_PRIVATE_{uuid.uuid4().hex}"
            public_pem = f"PLACEHOLDER_PUBLIC_{uuid.uuid4().hex}"

        self._public_key_file.write_text(public_pem, encoding="utf-8")
        self._store_private_key_secure(private_key_path, private_pem)

        return public_pem, private_pem

    def get_public_key(self) -> str:
        """Returns public key PEM string."""
        pub, _ = self.get_or_create_keypair()
        return pub

    # ── Fingerprint ──────────────────────────────────────────────────────────

    def get_device_fingerprint(self) -> str:
        """Privacy-safe device fingerprint.

        SHA256(MachineGuid + public_key_hash + product_salt)

        Tolerates hardware upgrades (RAM, GPU, USB, monitor changes).
        """
        machine_guid = self._get_machine_guid()
        public_key = self.get_public_key()
        public_key_hash = hashlib.sha256(public_key.encode("utf-8")).hexdigest()[:32]

        raw = f"{machine_guid}:{public_key_hash}:{PRODUCT_SALT}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    # ── Device Name ──────────────────────────────────────────────────────────

    @staticmethod
    def get_device_name() -> str:
        """Friendly device name from OS."""
        try:
            name = platform.node()
            if name:
                return name
        except Exception:
            pass
        return os.environ.get("COMPUTERNAME", "Unknown PC")

    @staticmethod
    def get_os_type() -> str:
        return platform.system()

    # ── Windows MachineGuid ──────────────────────────────────────────────────

    @staticmethod
    def _get_machine_guid() -> str:
        """Read Windows MachineGuid from registry. Falls back to hostname hash.

        MachineGuid survives hardware upgrades but changes on Windows reinstall.
        This is the desired behavior: reinstall = reactivate via account login.
        """
        if platform.system() == "Windows":
            try:
                import winreg
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Cryptography",
                    0,
                    winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                ) as key:
                    value, _ = winreg.QueryValueEx(key, "MachineGuid")
                    return str(value)
            except Exception as e:
                logger.warning("Cannot read MachineGuid: %s", e)

        # Fallback for non-Windows or registry access failure
        fallback = f"{platform.node()}:{os.getlogin() if hasattr(os, 'getlogin') else 'user'}"
        return hashlib.sha256(fallback.encode("utf-8")).hexdigest()[:36]

    # ── Secure Key Storage ───────────────────────────────────────────────────

    @staticmethod
    def _store_private_key_secure(path: Path, key_pem: str) -> None:
        """Store private key. Production: use DPAPI via ctypes or keyring library."""
        if platform.system() == "Windows":
            try:
                import ctypes
                import ctypes.wintypes

                # Try DPAPI encryption
                class DATA_BLOB(ctypes.Structure):
                    _fields_ = [
                        ("cbData", ctypes.wintypes.DWORD),
                        ("pbData", ctypes.POINTER(ctypes.c_char)),
                    ]

                data_in = key_pem.encode("utf-8")
                blob_in = DATA_BLOB(len(data_in), ctypes.cast(ctypes.create_string_buffer(data_in, len(data_in)), ctypes.POINTER(ctypes.c_char)))
                blob_out = DATA_BLOB()

                if ctypes.windll.crypt32.CryptProtectData(
                    ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
                ):
                    encrypted = ctypes.string_at(blob_out.pbData, blob_out.cbData)
                    path.write_bytes(encrypted)
                    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
                    return
            except Exception as e:
                logger.warning("DPAPI storage failed, using plaintext fallback: %s", e)

        # Fallback: plaintext (acceptable for development)
        path.write_text(key_pem, encoding="utf-8")

    @staticmethod
    def _load_private_key_secure(path: Path) -> Optional[str]:
        """Load private key. Tries DPAPI decryption first."""
        if not path.exists():
            return None

        if platform.system() == "Windows":
            try:
                import ctypes
                import ctypes.wintypes

                class DATA_BLOB(ctypes.Structure):
                    _fields_ = [
                        ("cbData", ctypes.wintypes.DWORD),
                        ("pbData", ctypes.POINTER(ctypes.c_char)),
                    ]

                encrypted = path.read_bytes()
                blob_in = DATA_BLOB(len(encrypted), ctypes.cast(ctypes.create_string_buffer(encrypted, len(encrypted)), ctypes.POINTER(ctypes.c_char)))
                blob_out = DATA_BLOB()

                if ctypes.windll.crypt32.CryptUnprotectData(
                    ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
                ):
                    decrypted = ctypes.string_at(blob_out.pbData, blob_out.cbData)
                    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
                    return decrypted.decode("utf-8")
            except Exception:
                pass

        # Fallback: read as plaintext
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return None

    # ── Challenge Signing ────────────────────────────────────────────────────

    def sign_challenge(self, challenge: bytes) -> Optional[bytes]:
        """Sign a server challenge to prove device ownership."""
        _, private_pem = self.get_or_create_keypair()
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding

            private_key = serialization.load_pem_private_key(private_pem.encode("utf-8"), password=None)
            return private_key.sign(
                challenge,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
        except Exception as e:
            logger.error("Challenge signing failed: %s", e)
            return None
