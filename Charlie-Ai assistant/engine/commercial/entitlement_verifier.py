"""
engine/commercial/entitlement_verifier.py — RSA public key verification of server-signed entitlements.

The PUBLIC verification key is embedded here. The PRIVATE signing key stays server-side.
Desktop NEVER signs entitlements — it only verifies them.
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger("jarvis.commercial.entitlement_verifier")

# ── IMPORTANT ─────────────────────────────────────────────────────────────────
# This key is populated at build time from licensing_server/keys/entitlement_verify.pub
# Run `python build_production.py` to auto-embed it.
# The private signing key NEVER appears in client code.
# ─────────────────────────────────────────────────────────────────────────────

VERIFICATION_PUBLIC_KEY_PEM = """
-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAp2caCxMebHfBXUWedH2I
PIro8fgmvNGyg8nlndws8E71Eqa3cSJpFGnrsf1XKNVQKPhdW64568jxSqg8IftV
z3AYLhmbV1qwjJ0zZNHa+72QGHXr9SbvllP8q204eJefW59LyDr7uqXspYN5U/lO
U5OzRsFNf0zTpw2XG5IKx5OQCOzfzf+XFWBvX0j8Ox0DsnkAYS47c6bRE/4l8s8I
+H03gAubZPZOu7550XizBZVxs9Zt/JhKwqdu14EUonmT077fb/tpnrvyZstaYYiE
02bmxVFu4wR0vfKkeTHEu+GMf94Kyc5DFC1duIT5EIJ9TODBTbhKvG24vwowVbW+
hwIDAQAB
-----END PUBLIC KEY-----
""".strip()


@dataclass
class EntitlementPayload:
    """Decoded entitlement content."""
    ent_id: str = ""
    user_id: str = ""
    sub_id: str = ""
    plan: str = "STARTER"
    device_id: str = ""
    features: List[str] = field(default_factory=list)
    license_type: str = "MONTHLY"
    issued_at: str = ""
    expires_at: str = ""
    revalidation_at: str = ""


class EntitlementVerifier:
    """Verifies RSA-PSS signed entitlement tokens from the licensing server.

    Token format: base64url(canonical_json).base64url(rsa_signature)

    Security properties:
      - Cannot forge: requires server's RSA private key
      - Device-bound: payload includes device_id
      - Time-limited: expires_at / revalidation_at
      - Tamper-evident: any modification invalidates signature
    """

    def __init__(self, public_key_pem: Optional[str] = None, plan_registry: Optional[Any] = None):
        self._public_key_pem = public_key_pem or VERIFICATION_PUBLIC_KEY_PEM
        self.plan_registry = plan_registry
        self._public_key = None

        if "REPLACE_WITH" not in self._public_key_pem:
            try:
                from cryptography.hazmat.primitives import serialization
                self._public_key = serialization.load_pem_public_key(
                    self._public_key_pem.encode("utf-8")
                )
            except Exception as e:
                logger.error("Failed to load verification public key: %s", e)

    def gate_feature(self, account: Any, entitlement: Any) -> Any:
        """Gate feature execution based on account tier and entitlements."""
        from .feature_gate import FeatureGate
        from .entitlement_manager import EntitlementManager
        from .plan_registry import PlanRegistry
        reg = self.plan_registry or PlanRegistry()
        em = EntitlementManager(plan_registry=reg)
        gate = FeatureGate(entitlement_manager=em, plan_registry=reg)
        return gate.can_use(account, entitlement)

    def verify_token(self, token: str) -> Tuple[bool, str, Optional[EntitlementPayload]]:
        """Verify a signed entitlement token.

        Returns (is_valid, reason, payload_or_None).
        """
        if not self._public_key:
            return False, "Verification key not configured. Online verification required.", None

        # Split token
        parts = token.split(".", 1)
        if len(parts) != 2:
            return False, "Malformed entitlement token.", None

        payload_b64, signature_b64 = parts

        try:
            payload_bytes = base64.urlsafe_b64decode(payload_b64 + "==")
            signature = base64.urlsafe_b64decode(signature_b64 + "==")
        except Exception:
            return False, "Failed to decode entitlement token.", None

        # Verify RSA-PSS signature
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding

            self._public_key.verify(
                signature,
                payload_bytes,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
        except Exception:
            return False, "Entitlement signature verification FAILED. Possible tampering.", None

        # Parse payload
        try:
            data = json.loads(payload_bytes.decode("utf-8"))
            payload = EntitlementPayload(
                ent_id=data.get("ent_id", ""),
                user_id=data.get("user_id", ""),
                sub_id=data.get("sub_id", ""),
                plan=data.get("plan", "STARTER"),
                device_id=data.get("device_id", ""),
                features=data.get("features", []),
                license_type=data.get("license_type", "MONTHLY"),
                issued_at=data.get("issued_at", ""),
                expires_at=data.get("expires_at", ""),
                revalidation_at=data.get("revalidation_at", ""),
            )
            return True, "Signature valid.", payload
        except Exception as e:
            return False, f"Failed to parse entitlement payload: {e}", None

    def is_device_match(self, payload: EntitlementPayload, current_device_id: str) -> bool:
        """Check if entitlement is bound to current device."""
        return payload.device_id == current_device_id

    def is_expired(self, payload: EntitlementPayload) -> bool:
        """Check if entitlement has passed its expiry time."""
        try:
            exp = datetime.fromisoformat(payload.expires_at)
            return datetime.now(timezone.utc) > exp
        except Exception:
            return True  # If we can't parse, treat as expired

    def needs_revalidation(self, payload: EntitlementPayload) -> bool:
        """Check if entitlement should be refreshed from server."""
        try:
            reval = datetime.fromisoformat(payload.revalidation_at)
            return datetime.now(timezone.utc) > reval
        except Exception:
            return True

    def full_verify(self, token: str, current_device_id: str) -> Tuple[bool, str, Optional[EntitlementPayload]]:
        """Complete verification: signature + device match + expiry.

        Returns (is_valid, reason, payload_or_None).
        """
        ok, reason, payload = self.verify_token(token)
        if not ok:
            return False, reason, None

        if not self.is_device_match(payload, current_device_id):
            return False, f"Device mismatch: entitlement bound to {payload.device_id}, current is {current_device_id}.", payload

        if self.is_expired(payload):
            return False, "Entitlement expired. Online revalidation required.", payload

        return True, "Valid entitlement.", payload
