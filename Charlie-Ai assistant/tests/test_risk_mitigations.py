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

from fastapi import HTTPException
from engine.commercial.entitlement_verifier import EntitlementVerifier
from licensing_server.config import config
from licensing_server.database import Base, UserDB, SubscriptionDB, PaymentDB, PlanTier, SubscriptionStatus
from licensing_server.middleware.rate_limiter import RateLimiter
from licensing_server.services.entitlement_signer import EntitlementSigner
from licensing_server.services.license_service import LicenseService
from licensing_server.services.payment_service import PaymentService


from sqlalchemy.pool import StaticPool

import os
import tempfile

class TestRiskMitigations(unittest.TestCase):

    def setUp(self):
        # Ephemeral file-based SQLite with WAL mode for true multithreaded connection concurrency
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.db_path = self.temp_db.name.replace("\\", "/")
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False, "timeout": 30},
            echo=False,
        )
        with self.engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL;"))
            conn.commit()
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass

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
            email=f"{user_id}@charlie.ai",
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

    # ── 4. Rate-Limiting & Idempotency Tests ────────────────────────────────────

    def test_rate_limiter_blocks_and_logs_429(self):
        """RateLimiter raises 429 when max requests exceeded within window."""
        limiter = RateLimiter()
        key = f"test_client_{uuid.uuid4().hex[:8]}"

        # First 3 requests should pass
        for _ in range(3):
            limiter.check(key, max_requests=3, window_seconds=60)

        # 4th request must raise 429
        with self.assertRaises(HTTPException) as ctx:
            limiter.check(key, max_requests=3, window_seconds=60)

        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("Rate limit exceeded", ctx.exception.detail)

    def test_payment_activation_idempotent_replay(self):
        """Replayed payment webhook does not duplicate PaymentDB records or corrupt state."""
        user_id = f"usr_{uuid.uuid4().hex[:16]}"
        user = UserDB(
            id=user_id,
            email=f"{user_id}@charlie.ai",
            password_hash="hashed_pw",
            display_name="Idempotent Tester",
        )
        self.db.add(user)
        self.db.commit()

        payment_service = PaymentService()
        order_id = f"order_{uuid.uuid4().hex[:14]}"
        payment_id = f"pay_{uuid.uuid4().hex[:14]}"

        # First activation
        ok1, msg1 = payment_service.activate_subscription(
            self.db, user_id=user_id, plan="PRO", order_id=order_id, payment_id=payment_id, amount_paise=19900
        )
        self.assertTrue(ok1)
        self.assertIn("Subscription activated: PRO", msg1)

        # Verify only 1 PaymentDB row
        count1 = self.db.query(PaymentDB).filter(PaymentDB.payment_id == payment_id).count()
        self.assertEqual(count1, 1)

        # Second replayed activation
        ok2, msg2 = payment_service.activate_subscription(
            self.db, user_id=user_id, plan="PRO", order_id=order_id, payment_id=payment_id, amount_paise=19900
        )
        self.assertTrue(ok2)
        self.assertIn("already verified (idempotent replay)", msg2)

        # Verify still exactly 1 PaymentDB row
        count2 = self.db.query(PaymentDB).filter(PaymentDB.payment_id == payment_id).count()
        self.assertEqual(count2, 1)

    def test_device_activation_and_conflict_enforcement(self):
        """Device activation enforces one-active-PC policy and detects clone attempts."""
        user_id = f"usr_{uuid.uuid4().hex[:16]}"
        user = UserDB(
            id=user_id,
            email=f"{user_id}@charlie.ai",
            password_hash="hashed_pw",
            display_name="Device Tester",
        )
        sub = SubscriptionDB(
            id=f"sub_{uuid.uuid4().hex[:16]}",
            user_id=user_id,
            plan=PlanTier.PRO.value,
            status=SubscriptionStatus.ACTIVE.value,
            device_limit=1,
        )
        self.db.add(user)
        self.db.add(sub)
        self.db.commit()

        signer = EntitlementSigner()
        license_service = LicenseService(signer)

        # 1. Activate PC Alpha -> succeeds
        ok_a, msg_a, ent_a = license_service.activate_device(
            self.db,
            user_id=user_id,
            device_id="PC-ALPHA-001",
            fingerprint_hash="fingerprint_hash_pc_alpha_123456",
            device_public_key="pubkey_pc_alpha",
            device_name="Alpha Laptop",
        )
        self.assertTrue(ok_a)
        self.assertIsNotNone(ent_a)
        self.assertEqual(ent_a["plan"], "PRO")

        # 2. Activate PC Beta without transfer -> rejected with DEVICE_CONFLICT
        ok_b, msg_b, data_b = license_service.activate_device(
            self.db,
            user_id=user_id,
            device_id="PC-BETA-002",
            fingerprint_hash="fingerprint_hash_pc_beta_123456",
            device_public_key="pubkey_pc_beta",
            device_name="Beta Desktop",
        )
        self.assertFalse(ok_b)
        self.assertEqual(msg_b, "DEVICE_CONFLICT")
        self.assertEqual(data_b["active_device_id"], "PC-ALPHA-001")

        # 3. Clone attempt: Same device ID with altered fingerprint -> rejected
        ok_clone, msg_clone, _ = license_service.activate_device(
            self.db,
            user_id=user_id,
            device_id="PC-ALPHA-001",
            fingerprint_hash="altered_fake_fingerprint_hash",
            device_public_key="pubkey_pc_alpha",
            device_name="Alpha Clone",
        )
        self.assertFalse(ok_clone)
        self.assertIn("Possible clone detected", msg_clone)


if __name__ == "__main__":
    unittest.main()
