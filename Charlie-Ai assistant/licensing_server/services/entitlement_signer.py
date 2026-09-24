"""
licensing_server/services/entitlement_signer.py — RSA-2048 entitlement signing.

PRIVATE key stays server-side. Desktop client only gets the PUBLIC key.
Signs canonical JSON payload with RSA-PSS. Constant-time, tamper-evident.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed

from licensing_server.config import PRIVATE_KEY_PATH, PUBLIC_KEY_PATH, config, ensure_rsa_keypair


class EntitlementSigner:
    """Signs entitlement payloads with RSA-2048 private key.

    The signed entitlement is a self-contained token:
    {
      "payload": {base64-encoded canonical JSON},
      "signature": {base64-encoded RSA signature}
    }

    Desktop verifies with embedded PUBLIC key only.
    """

    def __init__(self):
        private_pem, public_pem = ensure_rsa_keypair()
        self._private_key = serialization.load_pem_private_key(
            private_pem.encode("utf-8"), password=None
        )
        self._public_pem = public_pem

    @property
    def public_key_pem(self) -> str:
        """Public key to embed in desktop client."""
        return self._public_pem

    def sign_payload(self, data_str: str) -> str:
        """Sign an arbitrary string payload with RSA-PSS private key."""
        signature = self._private_key.sign(
            data_str.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        return base64.urlsafe_b64encode(signature).decode("utf-8")

    def sign_entitlement(
        self,
        user_id: str,
        subscription_id: str,
        plan: str,
        device_id: str,
        features: List[str],
        license_type: str = "MONTHLY",
        validity_days: Optional[int] = None,
    ) -> dict:
        """Create and sign an entitlement token.

        Returns dict with:
          - entitlement_id
          - payload (canonical JSON dict)
          - payload_b64 (base64 encoded canonical JSON)
          - signature_b64 (base64 encoded RSA-PSS signature)
          - token (combined portable token string)
        """
        if validity_days is None:
            validity_days = (
                config.LIFETIME_OFFLINE_GRACE_DAYS
                if license_type == "LIFETIME"
                else config.MONTHLY_OFFLINE_GRACE_DAYS
            )

        now = datetime.now(timezone.utc)
        entitlement_id = f"ent_{uuid.uuid4().hex[:16]}"

        payload = {
            "ent_id": entitlement_id,
            "user_id": user_id,
            "sub_id": subscription_id,
            "plan": plan,
            "device_id": device_id,
            "features": sorted(features),
            "license_type": license_type,
            "issued_at": now.isoformat(),
            "expires_at": (now + timedelta(days=validity_days)).isoformat(),
            "revalidation_at": (now + timedelta(days=min(validity_days, 7))).isoformat(),
        }

        # Canonical JSON — sorted keys, no whitespace
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        canonical_bytes = canonical.encode("utf-8")
        payload_b64 = base64.urlsafe_b64encode(canonical_bytes).decode("utf-8")

        # RSA-PSS signature
        signature = self._private_key.sign(
            canonical_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        signature_b64 = base64.urlsafe_b64encode(signature).decode("utf-8")

        # Combined portable token
        token = f"{payload_b64}.{signature_b64}"

        return {
            "entitlement_id": entitlement_id,
            "payload": payload,
            "payload_b64": payload_b64,
            "signature_b64": signature_b64,
            "token": token,
            "expires_at": payload["expires_at"],
            "revalidation_at": payload["revalidation_at"],
        }
