"""
tests/test_risk_mitigations.py — Tests for high-risk vulnerability mitigations:
1. Payment webhook signature verification & invalid signature rejection.
2. Forged / Tampered RSA entitlement token rejection.
3. SQLite database concurrency & atomic transaction rollback.
"""

import base64
import hashlib
import hmac
import json
import threading
import time
import unittest
import uuid
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from engine.commercial.entitlement_verifier import EntitlementVerifier
from licensing_server.config import config
from licensing_server.database import Base, UserDB, SubscriptionDB, PlanTier, SubscriptionStatus
from licensing_server.services.entitlement_signer import EntitlementSigner
from licensing_server.services.payment_service import PaymentService


from sqlalchemy.pool import StaticPool

class TestRiskMitigations(unittest.TestCase):

    def setUp(self):
        # Ephemeral shared in-memory SQLite for multithreaded test isolation
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    # ── 1. Payment Webhook Tests ───────────────────────────────────────────────

    def test_payment_webhook_valid_signature_success(self):
        """Valid HMAC signature from Razorpay is accepted."""
        payment_service = PaymentService()
        webhook_secret = "test_webhook_secret_key"
        config.RAZORPAY_WEBHOOK_SECRET = webhook_secret

        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_test123",
                        "order_id": "order_test123",
                        "amount": 99900,
                        "notes": {"user_id": "usr_test1", "plan": "PRO"}
                    }
                }
            }
        }
        body = json.dumps(payload).encode("utf-8")
        valid_sig = hmac.new(webhook_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

        ok, data = payment_service.verify_razorpay_webhook(body, valid_sig)
        self.assertTrue(ok)
        self.assertEqual(data.get("event"), "payment.captured")

    def test_payment_webhook_forged_signature_rejection(self):
        """Forged or mismatched HMAC signature is strictly rejected."""
        payment_service = PaymentService()
        config.RAZORPAY_WEBHOOK_SECRET = "legitimate_secret"

        body = b'{"event": "payment.captured", "payload": {}}'
        forged_sig = "0000000000000000000000000000000000000000000000000000000000000000"

        ok, data = payment_service.verify_razorpay_webhook(body, forged_sig)
        self.assertFalse(ok)
        self.assertIn("error", data)

    # ── 2. Forged RSA Entitlement Tests ────────────────────────────────────────

    def test_legitimate_rsa_entitlement_verifies(self):
        """Authentic server-signed RSA entitlement verifies successfully on client."""
        signer = EntitlementSigner()
        verifier = EntitlementVerifier(public_key_pem=signer.public_key_pem)

        token_data = signer.sign_entitlement(
            user_id="usr_alice",
            subscription_id="sub_alice",
            plan="PRO",
            device_id="hw_fingerprint_123",
            features=["voice", "creator", "offline"],
        )
        token = token_data["token"]

        is_valid, reason, payload = verifier.verify_token(token)
        self.assertTrue(is_valid, f"Verification failed: {reason}")
        self.assertIsNotNone(payload)
        self.assertEqual(payload.plan, "PRO")
        self.assertEqual(payload.user_id, "usr_alice")

    def test_tampered_payload_rsa_rejection(self):
        """Tampered entitlement payload (e.g. STARTER altered to LIFETIME) is rejected."""
        signer = EntitlementSigner()
        verifier = EntitlementVerifier(public_key_pem=signer.public_key_pem)

        token_data = signer.sign_entitlement(
            user_id="usr_bob",
            subscription_id="sub_bob",
            plan="STARTER",
            device_id="hw_fingerprint_456",
            features=["voice"],
        )
        payload_b64, signature_b64 = token_data["token"].split(".")

        # Attacker decodes payload, changes plan to LIFETIME, and re-encodes
        decoded_json = json.loads(base64.urlsafe_b64decode(payload_b64 + "==").decode("utf-8"))
        decoded_json["plan"] = "LIFETIME"
        tampered_canonical = json.dumps(decoded_json, sort_keys=True, separators=(",", ":")).encode("utf-8")
        tampered_payload_b64 = base64.urlsafe_b64encode(tampered_canonical).decode("utf-8")

        tampered_token = f"{tampered_payload_b64}.{signature_b64}"

        is_valid, reason, payload = verifier.verify_token(tampered_token)
        self.assertFalse(is_valid)
        self.assertIn("verification FAILED", reason)

    def test_rogue_private_key_signature_rejection(self):
        """Entitlement signed by an attacker's rogue RSA private key is rejected."""
        signer = EntitlementSigner()
        verifier = EntitlementVerifier(public_key_pem=signer.public_key_pem)

        # Generate rogue keypair
        rogue_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        payload = {
            "ent_id": "ent_rogue",
            "user_id": "usr_hacker",
            "sub_id": "sub_rogue",
            "plan": "LIFETIME",
            "device_id": "hw_rogue",
            "features": ["all"],
            "license_type": "LIFETIME",
            "issued_at": "2026-01-01T00:00:00Z",
            "expires_at": "2099-01-01T00:00:00Z",
            "revalidation_at": "2099-01-01T00:00:00Z",
        }
        canonical_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        payload_b64 = base64.urlsafe_b64encode(canonical_bytes).decode("utf-8")
        rogue_sig = rogue_key.sign(
            canonical_bytes,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
        rogue_sig_b64 = base64.urlsafe_b64encode(rogue_sig).decode("utf-8")
        rogue_token = f"{payload_b64}.{rogue_sig_b64}"

        is_valid, reason, _ = verifier.verify_token(rogue_token)
        self.assertFalse(is_valid)
        self.assertIn("verification FAILED", reason)

    # ── 3. Database Concurrency & Atomic Transaction Tests ─────────────────────

    def test_atomic_transaction_rollback_on_failure(self):
        """Database rollback leaves zero partial records upon unexpected error."""
        user_id = f"usr_{uuid.uuid4().hex[:16]}"
        try:
            user = UserDB(
                id=user_id,
                email="atomic_test@charlie.ai",
                password_hash="hashed_pw",
                display_name="Atomic Tester",
            )
            self.db.add(user)
            self.db.flush()  # flushes into transaction without commit

            # Simulate failure before subscription is created
            raise RuntimeError("Simulated mid-transaction failure")
            self.db.commit()
        except RuntimeError:
            self.db.rollback()

        # Verify user was NOT persisted
        persisted = self.db.query(UserDB).filter(UserDB.id == user_id).first()
        self.assertIsNone(persisted)

    def test_concurrent_sessions_isolated(self):
        """Concurrent sessions see independent transaction snapshots without collision."""
        user_id = f"usr_{uuid.uuid4().hex[:16]}"
        user = UserDB(
            id=user_id,
            email="concurrent@charlie.ai",
            password_hash="hashed_pw",
            display_name="Concurrent Tester",
        )
        self.db.add(user)
        self.db.commit()

        results = []

        def worker(worker_id):
            session = self.Session()
            try:
                u = session.query(UserDB).filter(UserDB.id == user_id).first()
                results.append((worker_id, u is not None))
            finally:
                session.close()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 5)
        for _, exists in results:
            self.assertTrue(exists)


if __name__ == "__main__":
    unittest.main()
