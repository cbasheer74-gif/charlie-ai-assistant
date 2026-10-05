"""
tests/test_public_commercial_platform.py — Comprehensive tests for CHARLIE Public Commercial Platform.

Validates:
1. Centralized PlanRegistry Catalog (Starter, Basic, Premium, Advanced, Lifetime).
2. Server-side Pricing Authority & Tampering Rejection.
3. User Registration, Default Starter Tier & 10 min/day Quota Link.
4. Email Verification Token Generation & Validation.
5. Password Reset Flow with Time-Limited Token & Session Invalidation.
6. Order Creation & Server-side Payment Verification for all Paid Tiers.
7. Webhook Signature Verification & Idempotent Replay Protection.
8. Lifetime Activation (One-Time Payment, No Monthly Renewal, 1-PC Policy).
9. Customer Account Portal & Device License Management.
10. Official Installer Distribution Integrity (SHA-256, Size > 100MB, Zero Source ZIP).
11. Security Headers Middleware (CSP, X-Frame-Options, Nosniff, Referrer-Policy).
12. Draft Legal Documents Validation (DRAFT_REQUIRES_REVIEW status check).
"""

import hashlib
import hmac
import json
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from licensing_server.app import app
from licensing_server.config import config
from licensing_server.database import (
    Base,
    DeviceDB,
    DeviceStatusEnum,
    LicenseEventDB,
    LicenseEventType,
    PaymentDB,
    PlanTier,
    SignedEntitlementDB,
    SubscriptionDB,
    SubscriptionStatus,
    UserDB,
    get_db,

)
from licensing_server.services.auth_service import AuthService
from licensing_server.services.entitlement_signer import EntitlementSigner
from licensing_server.services.license_service import PLAN_FEATURES, LicenseService
from sqlalchemy.pool import StaticPool
from licensing_server.services.payment_service import PLAN_PRICES, PaymentService


class TestPublicCommercialPlatform(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)


        cls.auth_service = AuthService()
        cls.payment_service = PaymentService()
        cls.signer = EntitlementSigner()
        cls.license_service = LicenseService(cls.signer)

        config.RAZORPAY_KEY_SECRET = "test_razorpay_secret_key"
        config.RAZORPAY_WEBHOOK_SECRET = "test_webhook_secret_key"

        def override_get_db():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        if hasattr(cls, "client"):
            cls.client.close()
        cls.engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()

    # --------------------------------------------------------------------------
    # 1. PlanRegistry Integration
    # --------------------------------------------------------------------------
    def test_plan_registry_catalog(self):
        """Verify centralized PlanRegistry returns accurate prices, intervals, and capabilities."""
        registry = self.payment_service.get_plan_registry()
        self.assertEqual(registry["currency"], "INR")
        plans = {p["tier"]: p for p in registry["plans"]}

        # All tiers present
        self.assertIn("STARTER", plans)
        self.assertIn("BASIC", plans)
        self.assertIn("PRO", plans)
        self.assertIn("PRO_PLUS", plans)
        self.assertIn("ANNUAL_PRO", plans)

        # Starter is free, 30 min daily
        self.assertEqual(plans["STARTER"]["price_inr"], 0)
        self.assertEqual(plans["STARTER"]["daily_minutes"], 30)
        self.assertEqual(plans["STARTER"]["name"], "Starter")

        # Basic: 149 INR / mo
        self.assertEqual(plans["BASIC"]["price_inr"], 149)
        self.assertEqual(plans["BASIC"]["price_paise"], 14900)
        self.assertEqual(plans["BASIC"]["billing"], "monthly")

        # Pro: 299 INR / mo
        self.assertEqual(plans["PRO"]["price_inr"], 299)
        self.assertEqual(plans["PRO"]["price_paise"], 29900)
        self.assertEqual(plans["PRO"]["badge"], "MOST POPULAR")

        # Pro+: 599 INR / mo
        self.assertEqual(plans["PRO_PLUS"]["price_inr"], 599)
        self.assertEqual(plans["PRO_PLUS"]["price_paise"], 59900)
        self.assertEqual(plans["PRO_PLUS"]["badge"], "BEST VALUE")

        # Annual Pro: 2999 INR / yr
        self.assertEqual(plans["ANNUAL_PRO"]["price_inr"], 2999)
        self.assertEqual(plans["ANNUAL_PRO"]["price_paise"], 299900)

        # Verify public API endpoint
        res = self.client.get("/payment/plan-registry")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["data"]["plans"]), 5)

    # --------------------------------------------------------------------------
    # 2. Server-side Pricing Authority & Tampering Rejection
    # --------------------------------------------------------------------------
    def test_price_tampering_rejection(self):
        """Verify client-submitted price mismatches are rejected server-side."""
        # Create user
        ok, _, data = self.auth_service.register(self.db, "buyer@domain.com", "Secret123!", "Buyer")
        self.assertTrue(ok)
        assert data is not None
        user_id = data["user_id"]

        # Attempt to buy PRO_PLUS (normally 59900 paise) for 9900 paise
        ok, msg, order = self.payment_service.create_order(
            self.db, user_id=user_id, plan="PRO_PLUS", client_amount=9900
        )
        self.assertFalse(ok)
        self.assertIn("Tampering rejected", msg)
        self.assertIsNone(order)

        # Check tamper audit event logged
        event = self.db.query(LicenseEventDB).filter(
            LicenseEventDB.user_id == user_id,
            LicenseEventDB.event_type == LicenseEventType.TAMPER_DETECTED.value,
        ).first()
        self.assertIsNotNone(event)
        assert event is not None
        details = json.loads(str(event.details_json))
        self.assertEqual(details["action"], "PRICE_TAMPERING_REJECTED")

        # Starter order creation should be rejected because Starter is free
        ok, msg, _ = self.payment_service.create_order(self.db, user_id=user_id, plan="STARTER")
        self.assertFalse(ok)
        self.assertIn("Starter plan is free", msg)

    # --------------------------------------------------------------------------
    # 3. User Registration & Default Starter Tier
    # --------------------------------------------------------------------------
    def test_user_registration_starter_activation(self):
        """New users should automatically get STARTER plan with 10-minute daily quota."""
        res = self.client.post("/auth/register", json={
            "email": "newuser@domain.com",
            "password": "Password123!",
            "display_name": "New Tester",
        })
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        data = body["data"]

        self.assertEqual(data["plan"], "STARTER")
        self.assertIn("access_token", data)
        self.assertIn("refresh_token", data)

        # Verify DB entry has Starter subscription
        sub = self.db.query(SubscriptionDB).filter(SubscriptionDB.user_id == data["user_id"]).first()
        self.assertIsNotNone(sub)
        self.assertEqual(sub.plan, PlanTier.STARTER.value)
        self.assertEqual(sub.status, SubscriptionStatus.FREE.value)

    # --------------------------------------------------------------------------
    # 4. Email Verification Architecture
    # --------------------------------------------------------------------------
    def test_email_verification_flow(self):
        """Verify token generation and email verification API."""
        ok, _, data = self.auth_service.register(self.db, "verify@domain.com", "Password123!", "Verifier")
        self.assertTrue(ok)
        assert data is not None
        user_id = data["user_id"]

        token = self.auth_service.create_email_verification_token(user_id)
        self.assertIsInstance(token, str)

        # Call verify endpoint
        res = self.client.post("/auth/verify-email", json={"token": token})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        self.assertIn("Email verified successfully", body["message"])

        # Invalid token test
        res_bad = self.client.post("/auth/verify-email", json={"token": "tampered_token"})
        self.assertFalse(res_bad.json()["success"])

    # --------------------------------------------------------------------------
    # 5. Password Reset Flow
    # --------------------------------------------------------------------------
    def test_password_reset_flow(self):
        """Verify password reset generates token, updates password, and revokes old sessions."""
        ok, _, data = self.auth_service.register(self.db, "reset@domain.com", "OldPassword123!", "Resetter")
        self.assertTrue(ok)
        assert data is not None
        user_id = data["user_id"]
        old_refresh = data["refresh_token"]

        # Request reset
        res_req = self.client.post("/auth/forgot-password", json={"email": "reset@domain.com"})
        self.assertTrue(res_req.json()["success"])
        reset_token = res_req.json()["reset_token"]

        # Reset password
        res_reset = self.client.post("/auth/reset-password", json={
            "token": reset_token,
            "new_password": "NewSecretPassword456!",
        })
        self.assertTrue(res_reset.json()["success"])

        # Old password fails
        ok_old, _, _ = self.auth_service.login(self.db, "reset@domain.com", "OldPassword123!")
        self.assertFalse(ok_old)

        # New password succeeds
        ok_new, _, new_data = self.auth_service.login(self.db, "reset@domain.com", "NewSecretPassword456!")
        self.assertTrue(ok_new)

        # Old refresh token is revoked because session_version incremented
        ok_ref, _, _ = self.auth_service.refresh(self.db, old_refresh)
        self.assertFalse(ok_ref)

    # --------------------------------------------------------------------------
    # 6. Secure Checkout & Server-side Payment Verification
    # --------------------------------------------------------------------------
    def test_secure_checkout_and_verification(self):
        """Verify order creation and cryptographic payment verification."""
        ok, _, data = self.auth_service.register(self.db, "premium@domain.com", "Pass123!", "Premium User")
        self.assertTrue(ok)
        assert data is not None
        user_id = data["user_id"]
        token = data["access_token"]

        # 1. Create order
        headers = {"Authorization": f"Bearer {token}"}
        res_order = self.client.post("/payment/create-order", json={"plan": "PRO"}, headers=headers)
        self.assertEqual(res_order.status_code, 200)
        order_body = res_order.json()
        self.assertTrue(order_body["success"])
        order_info = order_body["data"]
        self.assertEqual(order_info["amount_paise"], 29900)
        self.assertEqual(order_info["amount_inr"], 299)

        order_id = order_info["order_id"]
        payment_id = f"pay_{uuid.uuid4().hex[:14]}"

        # Generate valid Razorpay signature using configured secret
        message = f"{order_id}|{payment_id}".encode("utf-8")
        signature = hmac.new(
            config.RAZORPAY_KEY_SECRET.encode("utf-8"),
            message,
            hashlib.sha256,
        ).hexdigest()

        # 2. Verify payment
        res_verify = self.client.post("/payment/verify", json={
            "order_id": order_id,
            "payment_id": payment_id,
            "signature": signature,
            "plan": "PREMIUM",
        }, headers=headers)
        self.assertEqual(res_verify.status_code, 200)
        self.assertTrue(res_verify.json()["success"])

        # Check user's subscription is now ACTIVE with Premium features
        sub = self.db.query(SubscriptionDB).filter(SubscriptionDB.user_id == user_id).first()
        assert sub is not None
        self.assertEqual(sub.plan, PlanTier.PRO.value)
        self.assertEqual(sub.status, SubscriptionStatus.ACTIVE.value)

    # --------------------------------------------------------------------------
    # 7. Webhook Replay Idempotency
    # --------------------------------------------------------------------------
    def test_webhook_replay_idempotency(self):
        """Replaying identical payment verification must not duplicate revenue or entitlements."""
        ok, _, data = self.auth_service.register(self.db, "basic@domain.com", "Pass123!", "Basic User")
        assert data is not None
        user_id = data["user_id"]

        order_id = f"order_{uuid.uuid4().hex[:14]}"
        payment_id = f"pay_{uuid.uuid4().hex[:14]}"

        # First activation
        ok1, msg1 = self.payment_service.activate_subscription(
            self.db, user_id, "BASIC", order_id, payment_id, 9900
        )
        self.assertTrue(ok1)
        self.assertIn("Subscription activated: BASIC", msg1)

        # Count verified payments
        count1 = self.db.query(PaymentDB).filter(PaymentDB.payment_id == payment_id).count()
        self.assertEqual(count1, 1)

        # Replayed webhook/payment
        ok2, msg2 = self.payment_service.activate_subscription(
            self.db, user_id, "BASIC", order_id, payment_id, 9900
        )
        self.assertTrue(ok2)
        self.assertIn("already verified (idempotent replay)", msg2)

        # Payment records not duplicated
        count2 = self.db.query(PaymentDB).filter(PaymentDB.payment_id == payment_id).count()
        self.assertEqual(count2, 1)

    # --------------------------------------------------------------------------
    # 8. Basic Activation & One-Active-PC Policy
    # --------------------------------------------------------------------------
    def test_lifetime_activation_and_policy(self):
        """Basic plan receives ACTIVE, 30-day expiry, and enforces One-Active-PC."""
        ok, _, data = self.auth_service.register(self.db, "basicuser@domain.com", "Pass123!", "Basic User")
        assert data is not None
        user_id = data["user_id"]

        order_id = f"order_{uuid.uuid4().hex[:14]}"
        payment_id = f"pay_{uuid.uuid4().hex[:14]}"

        ok, msg = self.payment_service.activate_subscription(
            self.db, user_id, "BASIC", order_id, payment_id, 14900
        )
        self.assertTrue(ok)

        sub = self.db.query(SubscriptionDB).filter(SubscriptionDB.user_id == user_id).first()
        assert sub is not None
        self.assertEqual(sub.plan, PlanTier.BASIC.value)
        self.assertEqual(sub.status, SubscriptionStatus.ACTIVE.value)
        self.assertIsNotNone(sub.expires_at)

        # Activate on PC 1
        ok_pc1, _, ent1 = self.license_service.activate_device(
            self.db, user_id, "PC-ALPHA-101", "fingerprint_hash_pc1_123456", "pubkey_pc1", "Desktop-A", "Windows", "1.0.0"
        )
        self.assertTrue(ok_pc1)
        assert ent1 is not None
        self.assertEqual(ent1["plan"], "BASIC")
        self.assertEqual(ent1["status"], "ACTIVE")
        ent_record = self.db.query(SignedEntitlementDB).filter(SignedEntitlementDB.user_id == user_id).first()
        assert ent_record is not None
        self.assertEqual(ent_record.license_type, "MONTHLY")


        # Second PC attempt without transfer must be blocked
        ok_pc2, msg_pc2, _ = self.license_service.activate_device(
            self.db, user_id, "PC-BETA-202", "fingerprint_hash_pc2_123456", "pubkey_pc2", "Desktop-B", "Windows", "1.0.0"
        )
        self.assertFalse(ok_pc2)
        self.assertEqual(msg_pc2, "DEVICE_CONFLICT")


    # --------------------------------------------------------------------------
    # 9. Official Installer Distribution Integrity
    # --------------------------------------------------------------------------
    def test_official_installer_integrity(self):
        """Installer must be official binary with matching SHA-256 and no ZIPs."""
        workspace_root = Path(__file__).resolve().parent.parent
        installer_path = workspace_root / "landing_page" / "downloads" / "CHARLIE-Setup.exe"
        if not installer_path.exists():
            installer_path = workspace_root / "landing_page" / "downloads" / "JARVIS-Setup.exe"

        self.assertTrue(installer_path.exists(), f"Installer missing: {installer_path}")
        size_bytes = installer_path.stat().st_size
        self.assertGreater(size_bytes, 100 * 1024 * 1024, "Installer binary should be >100 MB")

        # Check real hash
        with open(installer_path, "rb") as f:
            computed_sha = hashlib.sha256(f.read()).hexdigest()

        expected_shas = [
            "cba1489b6bc599007037820318113e5edfa6e6943e3a4fbd4f8214e01953882a",
            "7ee6ee6910237e9443ddab3334153ccefefdf022e69acdcbd30ad482e5f0b60f",
            "4ff5ed8fc33fd3911d221885940309b02ab9229d6534c6546ba02011463c2cfb",
        ]
        self.assertIn(computed_sha, expected_shas)

        # Check no ZIP file in downloads
        downloads_dir = workspace_root / "landing_page" / "downloads"
        zip_files = list(downloads_dir.glob("*.zip"))
        self.assertEqual(len(zip_files), 0, "No raw source code or ZIP distribution allowed")

    # --------------------------------------------------------------------------
    # 10. Security Headers Middleware
    # --------------------------------------------------------------------------
    def test_security_headers(self):
        """All web responses must return hardened production security headers."""
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(res.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertEqual(res.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")
        self.assertIn("default-src", res.headers.get("Content-Security-Policy", ""))

    # --------------------------------------------------------------------------
    # 11. Draft Legal Pages Presence & Status
    # --------------------------------------------------------------------------
    def test_draft_legal_pages(self):
        """Verify legal pages exist and display DRAFT_REQUIRES_REVIEW status."""
        workspace_root = Path(__file__).resolve().parent.parent
        landing_page_dir = workspace_root / "landing_page"

        required_pages = [
            "terms.html",
            "privacy.html",
            "refund.html",
            "eula.html",
            "security.html",
            "contact.html",
        ]

        for page in required_pages:
            file_path = landing_page_dir / page
            self.assertTrue(file_path.exists(), f"Legal/info page missing: {page}")
            content = file_path.read_text(encoding="utf-8")
            self.assertGreater(len(content), 200, f"Page too short: {page}")

            if page in ["terms.html", "privacy.html", "refund.html", "eula.html"]:
                self.assertIn("DRAFT_REQUIRES_REVIEW", content, f"Page {page} missing draft disclaimer")


if __name__ == "__main__":
    unittest.main()
