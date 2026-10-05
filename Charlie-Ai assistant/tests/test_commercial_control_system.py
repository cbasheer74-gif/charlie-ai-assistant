"""
tests/test_commercial_control_system.py — Comprehensive tests for CHARLIE Commercial Control System.

Verifies:
1. Owner Admin Metrics & Financial Engine (MRR, Revenue, Tier counts, Churn, Conversion).
2. Admin User Management (Search, Detail, Suspend, Reactivate, Device Reset, Entitlement Grant).
3. Zero-backdoor security & Audit Logging.
4. Customer Portal API (Overview, Deactivation, Transfer, Password Change, Logout All).
5. Support Tickets with Secret-Scrubbed Diagnostics.
6. Remote License Revocation / Kill-Switch.
7. Signed Update Distribution & SemVer checking.
"""

import json
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from licensing_server.config import config
from licensing_server.database import (
    AuditLogDB,
    Base,
    DeviceDB,
    DeviceStatusEnum,
    LicenseEventDB,
    PaymentDB,
    PlanTier,
    SubscriptionDB,
    SubscriptionStatus,
    SupportTicketDB,
    TransferEventDB,
    UserDB,
    _utcnow,
)
from licensing_server.services.admin_service import AdminService
from licensing_server.services.auth_service import AuthService
from licensing_server.services.support_service import SupportService
from licensing_server.services.update_service import UpdateService, is_newer_version, parse_semver


class TestCommercialControlSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Use isolated in-memory SQLite database
        cls.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

        cls.admin_service = AdminService()
        cls.auth_service = AuthService()
        cls.support_service = SupportService()
        cls.update_service = UpdateService()

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.rollback()
        self.db.close()
        Base.metadata.drop_all(self.engine)

    def _seed_test_data(self):
        """Seed a realistic set of users, subscriptions, devices, payments, and tickets."""
        # 1. Admin / Owner
        admin = UserDB(
            id="usr_admin_1",
            email="admin@charlie.ai",
            password_hash=self.auth_service.hash_password("admin_pass_123"),
            display_name="Charlie Owner",
            role="OWNER",
            account_status="ACTIVE",
            session_version=1,
        )
        self.db.add(admin)

        # 2. Free Starter User
        starter_user = UserDB(
            id="usr_starter_1",
            email="free@user.com",
            password_hash=self.auth_service.hash_password("pass123"),
            display_name="Free User",
            role="USER",
            account_status="ACTIVE",
            session_version=1,
        )
        sub_starter = SubscriptionDB(
            id="sub_starter_1",
            user_id=starter_user.id,
            plan=PlanTier.STARTER.value,
            status=SubscriptionStatus.FREE.value,
        )
        self.db.add(starter_user)
        self.db.add(sub_starter)

        # 3. Premium Active User (₹199/mo)
        premium_user = UserDB(
            id="usr_premium_1",
            email="pro@user.com",
            password_hash=self.auth_service.hash_password("pass123"),
            display_name="Pro User",
            role="USER",
            account_status="ACTIVE",
            session_version=1,
        )
        dev_premium = DeviceDB(
            id="dev_pc_1",
            user_id=premium_user.id,
            fingerprint_hash="fp_hash_pc_1_12345",
            device_name="Workstation-X1",
            os_type="Windows",
            app_version="1.0.0",
            status=DeviceStatusEnum.ACTIVE.value,
            activated_at=_utcnow(),
        )
        sub_premium = SubscriptionDB(
            id="sub_premium_1",
            user_id=premium_user.id,
            plan=PlanTier.PREMIUM.value,
            status=SubscriptionStatus.ACTIVE.value,
            active_device_id=dev_premium.id,
            expires_at=_utcnow() + timedelta(days=30),
        )
        payment_premium = PaymentDB(
            id="pay_1",
            user_id=premium_user.id,
            provider="razorpay",
            order_id="ord_1",
            payment_id="pay_ref_1",
            amount_paise=19900,  # ₹199.00
            plan=PlanTier.PREMIUM.value,
            status="CAPTURED",
            created_at=_utcnow(),
            verified_at=_utcnow(),
        )
        self.db.add(premium_user)
        self.db.add(dev_premium)
        self.db.add(sub_premium)
        self.db.add(payment_premium)

        # 4. Advanced Active User (₹299/mo)
        advanced_user = UserDB(
            id="usr_advanced_1",
            email="adv@user.com",
            password_hash=self.auth_service.hash_password("pass123"),
            display_name="Advanced User",
            role="USER",
            account_status="ACTIVE",
            session_version=1,
        )
        sub_advanced = SubscriptionDB(
            id="sub_advanced_1",
            user_id=advanced_user.id,
            plan=PlanTier.ADVANCED.value,
            status=SubscriptionStatus.ACTIVE.value,
            expires_at=_utcnow() + timedelta(days=30),
        )
        payment_advanced = PaymentDB(
            id="pay_2",
            user_id=advanced_user.id,
            provider="razorpay",
            order_id="ord_2",
            payment_id="pay_ref_2",
            amount_paise=29900,  # ₹299.00
            plan=PlanTier.ADVANCED.value,
            status="CAPTURED",
            created_at=_utcnow(),
            verified_at=_utcnow(),
        )
        self.db.add(advanced_user)
        self.db.add(sub_advanced)
        self.db.add(payment_advanced)

        # 5. Suspicious User / Tamper event
        suspicious_user = UserDB(
            id="usr_suspicious_1",
            email="pirate@fake.com",
            password_hash=self.auth_service.hash_password("pass123"),
            display_name="Suspicious Actor",
            role="USER",
            account_status="ACTIVE",
        )
        tamper_event = LicenseEventDB(
            id="evt_tamper_1",
            user_id=suspicious_user.id,
            event_type="TAMPER_DETECTED",
            details_json=json.dumps({"reason": "Binary hash mismatch"}),
        )
        self.db.add(suspicious_user)
        self.db.add(tamper_event)

        self.db.commit()

    def test_01_admin_metrics_and_financial_engine(self):
        """Verify calculation of total users, MRR, today's revenue, active devices, and conversion."""
        self._seed_test_data()

        metrics = self.admin_service.get_overview_metrics(self.db)

        # 5 users seeded total (admin + starter + premium + advanced + suspicious)
        self.assertEqual(metrics["total_users"], 5)

        # Tier breakdown: starter: 1, premium: 1, advanced: 1
        tier_counts = metrics["tier_counts"]
        self.assertEqual(tier_counts["STARTER"], 1)
        self.assertEqual(tier_counts["PREMIUM"], 1)
        self.assertEqual(tier_counts["ADVANCED"], 1)

        # Active subscriptions: premium (active) + advanced (active) = 2
        self.assertEqual(metrics["active_subscriptions"], 2)

        # Active devices: 1 (dev_pc_1)
        self.assertEqual(metrics["active_devices"], 1)

        # Suspicious activations logged
        self.assertGreaterEqual(metrics["suspicious_activations"], 1)

        # Financial Revenue Engine:
        # Today / Monthly Revenue: ₹199 + ₹299 = ₹498.00
        rev = metrics["revenue"]
        self.assertEqual(rev["today"], 498.00)
        self.assertEqual(rev["monthly"], 498.00)
        self.assertEqual(rev["lifetime"], 498.00)

        # MRR: ₹199 (Premium) + ₹299 (Advanced) = ₹498
        self.assertEqual(rev["mrr"], 498)

        # Conversion rate: 2 paid out of 5 users = 40.0%
        self.assertEqual(metrics["analytics"]["conversion_rate_pct"], 40.0)

    def test_02_admin_user_search_and_detail(self):
        """Verify admin user search, filtering, and detailed inspection."""
        self._seed_test_data()

        # Search by email substring
        res = self.admin_service.search_users(self.db, query="pro@user")
        self.assertEqual(res["total"], 1)
        self.assertEqual(res["users"][0]["email"], "pro@user.com")
        self.assertEqual(res["users"][0]["plan"], "PREMIUM")

        # Search with plan filter
        res_plan = self.admin_service.search_users(self.db, plan="STARTER")
        self.assertEqual(res_plan["total"], 1)
        self.assertEqual(res_plan["users"][0]["email"], "free@user.com")

        # Detailed view
        detail = self.admin_service.get_user_detail(self.db, "usr_premium_1")
        self.assertIsNotNone(detail)
        self.assertEqual(detail["user"]["email"], "pro@user.com")
        self.assertEqual(detail["subscription"]["plan"], "PREMIUM")
        self.assertEqual(len(detail["devices"]), 1)
        self.assertEqual(detail["devices"][0]["device_name"], "Workstation-X1")
        self.assertEqual(len(detail["payments"]), 1)
        self.assertEqual(detail["payments"][0]["amount_inr"], 199.0)

    def test_03_admin_suspend_reactivate_and_audit_logging(self):
        """Verify user suspension, session revocation, reactivation, and audit log tracking."""
        self._seed_test_data()

        # Suspend
        ok, msg = self.admin_service.suspend_user(
            self.db, admin_id="usr_admin_1", user_id="usr_premium_1", reason="Payment dispute"
        )
        self.assertTrue(ok)

        # Check user status and active device unlinked
        user = self.db.query(UserDB).filter(UserDB.id == "usr_premium_1").first()
        self.assertEqual(user.account_status, "SUSPENDED")
        self.assertEqual(user.session_version, 2)  # session invalidated
        self.assertIsNone(user.subscription.active_device_id)

        # Check Audit Log created
        audit_logs = self.admin_service.get_audit_logs(self.db)
        self.assertGreaterEqual(len(audit_logs), 1)
        latest = audit_logs[0]
        self.assertEqual(latest["action"], "SUSPEND_USER")
        self.assertEqual(latest["target_user_id"], "usr_premium_1")
        self.assertEqual(latest["details"]["reason"], "Payment dispute")

        # Reactivate
        ok2, msg2 = self.admin_service.reactivate_user(self.db, admin_id="usr_admin_1", user_id="usr_premium_1")
        self.assertTrue(ok2)
        user_reactivated = self.db.query(UserDB).filter(UserDB.id == "usr_premium_1").first()
        self.assertEqual(user_reactivated.account_status, "ACTIVE")

    def test_04_admin_reset_device_and_grant_entitlement(self):
        """Verify admin can clear customer device slot and grant temporary entitlement."""
        self._seed_test_data()

        # Reset device activation
        ok, msg = self.admin_service.reset_device_activation(self.db, admin_id="usr_admin_1", user_id="usr_premium_1")
        self.assertTrue(ok)

        sub = self.db.query(SubscriptionDB).filter(SubscriptionDB.user_id == "usr_premium_1").first()
        self.assertIsNone(sub.active_device_id)

        # Grant promo LIFETIME plan
        ok_grant, msg_grant = self.admin_service.grant_entitlement(
            self.db, admin_id="usr_admin_1", user_id="usr_starter_1", plan="LIFETIME"
        )
        self.assertTrue(ok_grant)
        sub_starter = self.db.query(SubscriptionDB).filter(SubscriptionDB.user_id == "usr_starter_1").first()
        self.assertEqual(sub_starter.plan, "LIFETIME")
        self.assertEqual(sub_starter.status, "LIFETIME_ACTIVE")
        self.assertIsNone(sub_starter.expires_at)

    def test_05_support_ticket_secret_redaction(self):
        """Verify automatic sanitization of Gemini keys, Bearer tokens, passwords, and OpenAI keys."""
        self._seed_test_data()

        raw_logs = {
            "error": "Failed to call Gemini with key AIzaSyMockKeyForRedactionTest_9999999",
            "headers": {
                "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-IDcSemACt8x4iTMC6Y5",
            },
            "config": {
                "password": "SuperSecretPassword123",
                "openai_key": "sk-1234567890abcdef1234567890abcdef",
            },
        }

        pro_user = self.db.query(UserDB).filter(UserDB.id == "usr_premium_1").first()

        ok, msg, ticket = self.support_service.create_ticket(
            db=self.db,
            user=pro_user,
            subject="Crash report with Gemini key AIzaSyMockKeyForRedactionTest_9999999",
            message="My bearer header was Bearer secret_access_token_123456789 and password is 'abc'",
            category="CRASH",
            error_id="ERR_AI_500",
            app_version="1.0.0",
            os_version="Windows 11",
            raw_diagnostics=raw_logs,
        )

        self.assertTrue(ok)
        self.assertIsNotNone(ticket)
        self.assertTrue(ticket.ticket_number.startswith("TICK-"))

        # Check subject & message secrets are scrubbed
        self.assertNotIn("AIzaSyMockKeyForRedactionTest_9999999", ticket.subject)
        self.assertIn("[REDACTED_GEMINI_KEY]", ticket.subject)

        self.assertNotIn("secret_access_token_123456789", ticket.message)

        # Check nested diagnostics secrets are scrubbed
        diag = json.loads(ticket.diagnostics_json)
        self.assertNotIn("AIzaSyMockKeyForRedactionTest_9999999", diag["error"])
        self.assertIn("[REDACTED_GEMINI_KEY]", diag["error"])

        self.assertNotIn("SuperSecretPassword123", json.dumps(diag))
        self.assertNotIn("sk-1234567890abcdef1234567890abcdef", json.dumps(diag))

        # Admin replies to ticket
        ok_rep, msg_rep = self.support_service.reply_ticket(
            self.db, ticket_id=ticket.id, reply_text="Diagnostics received and analyzed.", new_status="RESOLVED"
        )
        self.assertTrue(ok_rep)
        self.assertEqual(ticket.status, "RESOLVED")
        self.assertEqual(ticket.admin_reply, "Diagnostics received and analyzed.")

    def test_06_remote_license_revocation_kill_switch(self):
        """Verify remote license revocation marks device REVOKED and unlinks subscription."""
        self._seed_test_data()

        dev = self.db.query(DeviceDB).filter(DeviceDB.id == "dev_pc_1").first()
        self.assertEqual(dev.status, DeviceStatusEnum.ACTIVE.value)

        # Admin executes remote kill-switch
        ok, msg = self.admin_service.revoke_device_license(
            self.db, admin_id="usr_admin_1", device_id="dev_pc_1", reason="Pirated installation"
        )
        self.assertTrue(ok)

        # Device is now REVOKED
        self.assertEqual(dev.status, DeviceStatusEnum.REVOKED.value)

        # Subscription active device is unlinked
        sub = self.db.query(SubscriptionDB).filter(SubscriptionDB.user_id == "usr_premium_1").first()
        self.assertIsNone(sub.active_device_id)

    def test_07_customer_portal_session_invalidation(self):
        """Verify customer password change and 'Logout all devices' bump session_version and invalidate old JWT."""
        self._seed_test_data()

        pro_user = self.db.query(UserDB).filter(UserDB.id == "usr_premium_1").first()
        initial_sv = pro_user.session_version

        # Issue token with initial session_version
        token = self.auth_service.create_access_token(pro_user.id, pro_user.email, session_version=initial_sv)
        validated_user = self.auth_service.get_user_from_token(self.db, token)
        self.assertIsNotNone(validated_user)

        # User clicks "Logout All Devices"
        self.auth_service.invalidate_all_sessions(self.db, pro_user)
        self.assertEqual(pro_user.session_version, initial_sv + 1)

        # Old token must now fail validation
        invalidated_user = self.auth_service.get_user_from_token(self.db, token)
        self.assertIsNone(invalidated_user)

        # Password change also invalidates sessions
        ok_pwd, _ = self.auth_service.change_password(self.db, pro_user, old_pass="pass123", new_pass="brand_new_pass_456")
        self.assertTrue(ok_pwd)
        self.assertEqual(pro_user.session_version, initial_sv + 2)
        self.assertTrue(self.auth_service.verify_password("brand_new_pass_456", pro_user.password_hash))

    def test_08_automatic_update_system(self):
        """Verify SemVer comparison, signed update release registration, and update checking."""
        self.assertTrue(is_newer_version("1.0.1", "1.0.0"))
        self.assertTrue(is_newer_version("2.0.0", "1.9.9"))
        self.assertFalse(is_newer_version("1.0.0", "1.0.0"))
        self.assertFalse(is_newer_version("0.9.9", "1.0.0"))

        # Register signed release v1.0.1
        ok, msg, rel = self.update_service.register_release(
            db=self.db,
            version="1.0.1",
            download_url="https://updates.charlie.ai/v1.0.1/CHARLIE-Setup.exe",
            sha256="a" * 64,
            release_notes="Major commercial update and performance fixes.",
            mandatory=False,
        )
        self.assertTrue(ok)
        self.assertIsNotNone(rel)
        self.assertTrue(len(rel.signature) > 30)

        # Check for updates with older client
        res = self.update_service.check_update(self.db, client_version="1.0.0")
        self.assertTrue(res["update_available"])
        self.assertEqual(res["latest_version"], "1.0.1")
        self.assertEqual(res["download_url"], "https://updates.charlie.ai/v1.0.1/CHARLIE-Setup.exe")
        self.assertEqual(res["sha256"], "a" * 64)

        # Check with current client
        res_current = self.update_service.check_update(self.db, client_version="1.0.1")
        self.assertFalse(res_current["update_available"])

    def test_09_payment_webhook_idempotency(self):
        """Verify replaying payment webhook does not duplicate transactions or inflate revenue."""
        from licensing_server.services.payment_service import PaymentService
        pay_service = PaymentService()

        # Initial payment verification
        ok1, msg1 = pay_service.activate_subscription(
            self.db, user_id="usr_premium_1", plan="PREMIUM",
            order_id="ord_test_idemp_1", payment_id="pay_test_idemp_1", amount_paise=19900
        )
        self.assertTrue(ok1)

        # Count payments
        count1 = self.db.query(PaymentDB).filter(PaymentDB.payment_id == "pay_test_idemp_1").count()
        self.assertEqual(count1, 1)

        # Replay identical webhook
        ok2, msg2 = pay_service.activate_subscription(
            self.db, user_id="usr_premium_1", plan="PREMIUM",
            order_id="ord_test_idemp_1", payment_id="pay_test_idemp_1", amount_paise=19900
        )
        self.assertTrue(ok2)
        self.assertIn("idempotent", msg2)

        # Count must remain 1
        count2 = self.db.query(PaymentDB).filter(PaymentDB.payment_id == "pay_test_idemp_1").count()
        self.assertEqual(count2, 1)

    def test_10_support_staff_internal_notes_isolation(self):
        """Verify staff internal notes are visible to admins but strictly hidden from customer serialization."""
        self._seed_test_data()
        pro_user = self.db.query(UserDB).filter(UserDB.id == "usr_premium_1").first()

        ok, msg, ticket = self.support_service.create_ticket(
            self.db, user=pro_user, subject="Billing query", message="Why was I charged?"
        )
        self.assertTrue(ok)

        # Staff adds internal note
        ok_note, _ = self.support_service.add_internal_note(
            self.db, ticket_id=ticket.id, staff_id="usr_admin_1",
            note_text="User disputed transaction before on Razorpay. Watch account."
        )
        self.assertTrue(ok_note)

        # Customer ticket serialization (must NOT contain internal_notes)
        customer_view = self.support_service.get_user_tickets(self.db, user_id=pro_user.id)
        self.assertNotIn("internal_notes", customer_view[0])

        # Staff ticket serialization (DOES contain internal_notes)
        staff_view = self.support_service.get_all_tickets(self.db)
        target_ticket = next(t for t in staff_view if t["id"] == ticket.id)
        self.assertIn("internal_notes", target_ticket)
        self.assertIn("Watch account", target_ticket["internal_notes"])

    def test_11_csv_export_sanitization(self):
        """Verify administrative CSV exports generate valid data without leaking secrets."""
        self._seed_test_data()

        users_csv = self.admin_service.export_csv(self.db, entity_type="users")
        self.assertIn("User ID,Email,Display Name", users_csv)
        self.assertIn("pro@user.com", users_csv)
        self.assertNotIn("pass123", users_csv)
        self.assertNotIn("$2b$", users_csv)  # No bcrypt hashes leaked

        payments_csv = self.admin_service.export_csv(self.db, entity_type="payments")
        self.assertIn("Payment ID,User ID,Order ID", payments_csv)
        self.assertIn("199.0", payments_csv)

    def test_12_device_security_flags(self):
        """Verify flagging devices for review, suspicious, or blocked states."""
        self._seed_test_data()

        dev = self.db.query(DeviceDB).filter(DeviceDB.id == "dev_pc_1").first()
        self.assertEqual(dev.security_flag, "NORMAL")

        dev.security_flag = "SUSPICIOUS"
        self.db.commit()

        # Appears in security monitoring
        sec = self.admin_service.get_security_monitoring(self.db)
        self.assertEqual(sec["suspicious_device_count"], 1)
        self.assertEqual(sec["suspicious_devices"][0]["name"], "Workstation-X1")

    def test_13_idor_protection_and_token_scoping(self):
        """Verify customer tokens derive strictly identity from JWT and cannot access or manipulate other users."""
        self._seed_test_data()
        starter_token = self.auth_service.create_access_token("usr_starter_1", "free@user.com", role="USER")
        premium_token = self.auth_service.create_access_token("usr_premium_1", "pro@user.com", role="USER")

        # Verify token maps strictly to user identity
        user1 = self.auth_service.get_user_from_token(self.db, starter_token)
        user2 = self.auth_service.get_user_from_token(self.db, premium_token)
        self.assertEqual(user1.id, "usr_starter_1")
        self.assertEqual(user2.id, "usr_premium_1")

        # Verify customer cannot view or mutate another user's support ticket
        t_ok, _, ticket = self.support_service.create_ticket(
            self.db, user=user2, subject="Private inquiry", message="Sensitive billing data"
        )
        self.assertTrue(t_ok)

        # Customer 1 queries their tickets: must NOT see Customer 2's ticket
        user1_tickets = self.support_service.get_user_tickets(self.db, user_id=user1.id)
        self.assertEqual(len(user1_tickets), 0)

        # Customer 2 queries their tickets: only sees their own
        user2_tickets = self.support_service.get_user_tickets(self.db, user_id=user2.id)
        self.assertEqual(len(user2_tickets), 1)
        self.assertEqual(user2_tickets[0]["id"], ticket.id)

    def test_14_rbac_hierarchy_enforcement(self):
        """Verify role-based boundary enforcement (CUSTOMER < SUPPORT < ADMIN < OWNER)."""
        import asyncio
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials
        from starlette.requests import Request
        from licensing_server.middleware.auth_middleware import require_support, require_admin, require_owner

        self._seed_test_data()

        # Add a SUPPORT role user
        support_user = UserDB(
            id="usr_support_1",
            email="support@charlie.ai",
            password_hash=self.auth_service.hash_password("supp_pass"),
            display_name="Support Agent",
            role="SUPPORT",
            account_status="ACTIVE",
            session_version=1,
        )
        # Add an ADMIN role user (not OWNER)
        admin_user = UserDB(
            id="usr_subadmin_1",
            email="subadmin@charlie.ai",
            password_hash=self.auth_service.hash_password("admin_pass"),
            display_name="Admin Staff",
            role="ADMIN",
            account_status="ACTIVE",
            session_version=1,
        )
        self.db.add(support_user)
        self.db.add(admin_user)
        self.db.commit()

        owner_token = self.auth_service.create_access_token("usr_admin_1", "admin@charlie.ai", role="OWNER")
        admin_token = self.auth_service.create_access_token("usr_subadmin_1", "subadmin@charlie.ai", role="ADMIN")
        support_token = self.auth_service.create_access_token("usr_support_1", "support@charlie.ai", role="SUPPORT")
        customer_token = self.auth_service.create_access_token("usr_premium_1", "pro@user.com", role="USER")

        req = Request({"type": "http", "headers": []})

        def _auth(func, token):
            creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
            return asyncio.run(func(request=req, credentials=creds, db=self.db))

        # 1. Customer token: Cannot access support, admin, or owner
        with self.assertRaises(HTTPException) as cm:
            _auth(require_support, customer_token)
        self.assertEqual(cm.exception.status_code, 403)

        with self.assertRaises(HTTPException) as cm:
            _auth(require_admin, customer_token)
        self.assertEqual(cm.exception.status_code, 403)

        with self.assertRaises(HTTPException) as cm:
            _auth(require_owner, customer_token)
        self.assertEqual(cm.exception.status_code, 403)

        # 2. Support token: Can access support, cannot access admin or owner
        u_supp = _auth(require_support, support_token)
        self.assertEqual(u_supp.id, "usr_support_1")
        with self.assertRaises(HTTPException) as cm:
            _auth(require_admin, support_token)
        self.assertEqual(cm.exception.status_code, 403)
        with self.assertRaises(HTTPException) as cm:
            _auth(require_owner, support_token)
        self.assertEqual(cm.exception.status_code, 403)

        # 3. Admin token: Can access support & admin, cannot access owner
        u_adm = _auth(require_support, admin_token)
        self.assertEqual(u_adm.id, "usr_subadmin_1")
        u_adm2 = _auth(require_admin, admin_token)
        self.assertEqual(u_adm2.id, "usr_subadmin_1")
        with self.assertRaises(HTTPException) as cm:
            _auth(require_owner, admin_token)
        self.assertEqual(cm.exception.status_code, 403)

        # 4. Owner token: Can access all
        u_own1 = _auth(require_support, owner_token)
        self.assertEqual(u_own1.id, "usr_admin_1")
        u_own2 = _auth(require_admin, owner_token)
        self.assertEqual(u_own2.id, "usr_admin_1")
        u_own3 = _auth(require_owner, owner_token)
        self.assertEqual(u_own3.id, "usr_admin_1")


if __name__ == "__main__":
    unittest.main()
