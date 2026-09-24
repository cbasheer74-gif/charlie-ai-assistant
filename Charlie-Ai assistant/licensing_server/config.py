"""
licensing_server/config.py — Server configuration, RSA key management, environment variables.

RSA keypair is generated once and persisted. The PRIVATE key stays here (server-side).
The PUBLIC key is embedded in the desktop client for entitlement verification.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

SERVER_DIR = Path(__file__).resolve().parent
KEYS_DIR = SERVER_DIR / "keys"
PRIVATE_KEY_PATH = KEYS_DIR / "entitlement_signing.pem"
PUBLIC_KEY_PATH = KEYS_DIR / "entitlement_verify.pub"


class ServerConfig:
    """Central server configuration. All secrets from environment variables."""

    # Database
    DATABASE_URL: str = os.getenv("CHARLIE_DB_URL", os.getenv("JARVIS_DB_URL", f"sqlite:///{SERVER_DIR / 'charlie_licensing.db'}"))

    # JWT
    JWT_SECRET: str = os.getenv("CHARLIE_JWT_SECRET", os.getenv("JARVIS_JWT_SECRET", "charlie_jwt_dev_secret_change_in_production"))
    JWT_ACCESS_EXPIRY_MINUTES: int = int(os.getenv("JARVIS_JWT_ACCESS_EXPIRY", "60"))
    JWT_REFRESH_EXPIRY_DAYS: int = int(os.getenv("JARVIS_JWT_REFRESH_EXPIRY", "30"))
    JWT_ALGORITHM: str = "HS256"

    # Razorpay
    RAZORPAY_KEY_ID: str = os.getenv("RAZORPAY_KEY_ID", "")
    RAZORPAY_KEY_SECRET: str = os.getenv("RAZORPAY_KEY_SECRET", "")
    RAZORPAY_WEBHOOK_SECRET: str = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

    # Rate Limiting
    LOGIN_RATE_LIMIT: int = int(os.getenv("JARVIS_LOGIN_RATE_LIMIT", "10"))  # per minute
    ACTIVATION_RATE_LIMIT: int = int(os.getenv("JARVIS_ACTIVATION_RATE_LIMIT", "5"))  # per minute
    TRANSFER_RATE_LIMIT: int = int(os.getenv("JARVIS_TRANSFER_RATE_LIMIT", "3"))  # per hour

    # Device Transfer
    MAX_TRANSFERS_PER_MONTH: int = int(os.getenv("JARVIS_MAX_TRANSFERS_MONTH", "3"))

    # Offline Grace (days)
    MONTHLY_OFFLINE_GRACE_DAYS: int = int(os.getenv("JARVIS_MONTHLY_OFFLINE_DAYS", "14"))
    LIFETIME_OFFLINE_GRACE_DAYS: int = int(os.getenv("JARVIS_LIFETIME_OFFLINE_DAYS", "90"))

    # Product
    PRODUCT_SALT: str = os.getenv("CHARLIE_PRODUCT_SALT", "charlie_ai_2026")

    # Commercial Admin & Control System
    ENVIRONMENT: str = os.getenv("CHARLIE_ENV", "development").lower()
    ADMIN_API_KEY: str = os.getenv("CHARLIE_ADMIN_KEY", "charlie_admin_secret_key_2026" if ENVIRONMENT != "production" else "")
    LATEST_APP_VERSION: str = os.getenv("CHARLIE_LATEST_VERSION", "1.2.3")
    INSTALLER_DOWNLOAD_URL: str = os.getenv("CHARLIE_INSTALLER_URL", "/downloads/CHARLIE-Setup-1.2.3.exe")

    # Server
    HOST: str = os.getenv("JARVIS_SERVER_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("JARVIS_SERVER_PORT", "8400"))
    DEBUG: bool = os.getenv("JARVIS_DEBUG", "false").lower() == "true"


def ensure_rsa_keypair() -> tuple[str, str]:
    """Generate RSA-2048 keypair if not exists. Returns (private_pem, public_pem)."""
    env_private = os.getenv("ENTITLEMENT_SIGNING_KEY_PEM")
    if env_private:
        priv_key = serialization.load_pem_private_key(env_private.encode("utf-8"), password=None)
        pub_pem = priv_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        return env_private, pub_pem

    KEYS_DIR.mkdir(parents=True, exist_ok=True)

    if PRIVATE_KEY_PATH.exists() and PUBLIC_KEY_PATH.exists():
        private_pem = PRIVATE_KEY_PATH.read_text(encoding="utf-8")
        public_pem = PUBLIC_KEY_PATH.read_text(encoding="utf-8")
        return private_pem, public_pem

    # Generate new RSA-2048 keypair
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

    PRIVATE_KEY_PATH.write_text(private_pem, encoding="utf-8")
    PUBLIC_KEY_PATH.write_text(public_pem, encoding="utf-8")

    print(f"[LICENSING] RSA-2048 keypair generated at {KEYS_DIR}")
    print(f"[LICENSING] PUBLIC KEY (embed in desktop client):\n{public_pem}")

    return private_pem, public_pem


config = ServerConfig()
