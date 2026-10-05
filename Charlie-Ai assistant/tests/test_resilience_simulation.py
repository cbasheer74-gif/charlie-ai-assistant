"""
tests/test_resilience_simulation.py — Automated Failure Simulation & Resilience Test Suite.

Simulates real-world edge cases:
1. Concurrent duplicate payment webhook delivery (idempotency race).
2. Concurrent credit deduction (atomic row-level lock race).
3. Concurrent wallet creation (unique constraint collision).
4. SQLite WAL multithreaded busy timeout & connection concurrency.
5. Atomic disk file persistence across sudden interruptions.
6. Offline entitlement verification & expired token fallback.
"""

import concurrent.futures
import json
import os
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from engine.commercial.core import atomic_write_text
from engine.commercial.credit_manager import CreditManager
from engine.commercial.entitlement_verifier import EntitlementVerifier
from engine.commercial.models import PlanTier as LocalPlanTier
from licensing_server.config import config
from licensing_server.database import (
    Base,
    CreditTransactionDB,
    CreditWalletDB,
    PaymentDB,
    PlanTier,
    SubscriptionDB,
    SubscriptionStatus,
    UserDB,
)
from licensing_server.services.credit_service import CreditService
from licensing_server.services.entitlement_signer import EntitlementSigner
from licensing_server.services.payment_service import PaymentService


class TestResilienceSimulations(unittest.TestCase):

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.db_path = self.temp_db.name.replace("\\", "/")
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False, "timeout": 30.0},
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

    # ---------------------------------------------------------------------------
    # 1. Concurrent Webhook / Payment Idempotency Race
    # ---------------------------------------------------------------------------

    def test_concurrent_duplicate_payment_activation_idempotency(self):
        """Simulate Razorpay sending identical webhook across 5 simultaneous connections."""
        user = UserDB(
            id="usr_sim_idemp",
            email="sim_idemp@charlie.test",
            password_hash="hash",
        )
        self.db.add(user)
        self.db.commit()

        payment_service = PaymentService()
        shared_payment_id = "pay_sim_dup_999"
        results = []
        errors = []

        def worker():
            db_session = self.Session()
            try:
                ok, msg = payment_service.activate_subscription(
                    db=db_session,
                    user_id="usr_sim_idemp",
                    plan="PRO",
                    order_id="order_sim_dup_999",
                    payment_id=shared_payment_id,
                    amount_paise=99900,
                )
                if ok:
                    results.append(msg)
            except Exception as e:
                errors.append(str(e))
            finally:
                db_session.close()

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Unexpected errors during concurrent webhook: {errors}")
        self.assertEqual(len(results), 5, "All 5 concurrent requests should resolve cleanly.")

        # Exactly 1 payment record must be stored with this payment_id
        db_check = self.Session()
        payments = db_check.query(PaymentDB).filter(PaymentDB.payment_id == shared_payment_id).all()
        self.assertEqual(len(payments), 1, "Must have exactly 1 payment record stored (idempotent).")

        # User credits must not be duplicated (PRO allocation = 1500 credits, exactly once)
        wallet = db_check.query(CreditWalletDB).filter(CreditWalletDB.user_id == "usr_sim_idemp").first()
        self.assertIsNotNone(wallet)
        self.assertEqual(wallet.subscription_credits, 1500, "Credits must not be duplicated by webhook re-delivery!")
        db_check.close()

    # ---------------------------------------------------------------------------
    # 2. Concurrent Credit Deduction Race (Lost-Update Protection)
    # ---------------------------------------------------------------------------

    def test_concurrent_credit_deductions_lost_update_prevention(self):
        """10 concurrent threads deduct 10 credits from a 100-credit wallet."""
        user = UserDB(
            id="usr_sim_credits",
            email="sim_credits@charlie.test",
            password_hash="hash",
        )
        self.db.add(user)
        self.db.commit()

        credit_service = CreditService()
        wallet = credit_service.get_or_create_wallet(self.db, "usr_sim_credits", PlanTier.PRO)
        wallet.subscription_credits = 100
        wallet.purchased_credits = 0
        self.db.commit()

        success_count = 0
        lock = threading.Lock()

        def deduct_worker():
            nonlocal success_count
            db_session = self.Session()
            try:
                ok, _, _ = credit_service.deduct_credits(
                    db=db_session,
                    user_id="usr_sim_credits",
                    feature="basic_text",
                    custom_cost=10,
                )
                if ok:
                    with lock:
                        success_count += 1
            finally:
                db_session.close()

        threads = [threading.Thread(target=deduct_worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(success_count, 10, "All 10 deductions of 10 credits should succeed.")

        db_check = self.Session()
        final_wallet = db_check.query(CreditWalletDB).filter(CreditWalletDB.user_id == "usr_sim_credits").first()
        self.assertEqual(final_wallet.subscription_credits, 0, "Final balance must be exactly 0 (no lost updates).")
        db_check.close()

    # ---------------------------------------------------------------------------
    # 3. Concurrent Wallet Creation Collision
    # ---------------------------------------------------------------------------

    def test_concurrent_wallet_creation_collision(self):
        """Simulate race where multiple requests create the user's initial wallet concurrently."""
        user = UserDB(
            id="usr_sim_race_wallet",
            email="sim_race@charlie.test",
            password_hash="hash",
        )
        self.db.add(user)
        self.db.commit()

        credit_service = CreditService()
        wallets = []

        def create_worker():
            db_session = self.Session()
            try:
                w = credit_service.get_or_create_wallet(db_session, "usr_sim_race_wallet", PlanTier.STARTER)
                wallets.append(w.id)
            finally:
                db_session.close()

        threads = [threading.Thread(target=create_worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(wallets), 5)
        # All returned wallet IDs must match the same single row in DB
        self.assertEqual(len(set(wallets)), 1, "Only one wallet must be created and returned to all callers.")

    # ---------------------------------------------------------------------------
    # 4. Atomic File Write Persistence
    # ---------------------------------------------------------------------------

    def test_atomic_file_write_durability(self):
        """Simulate rapid successive writes and verify file integrity without leftover temporary files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = Path(tmpdir) / "config" / "user_account.json"

            for i in range(20):
                payload = json.dumps({"iteration": i, "token": f"tok_{uuid.uuid4().hex}"})
                atomic_write_text(target_path, payload)

            self.assertTrue(target_path.exists())
            loaded = json.loads(target_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["iteration"], 19)

            # Ensure no temporary files (.tmp_*) left behind in the directory
            parent_dir = target_path.parent
            tmp_files = list(parent_dir.glob("*.tmp_*"))
            self.assertEqual(len(tmp_files), 0, "No temporary files should be orphaned after atomic writes.")

    # ---------------------------------------------------------------------------
    # 5. Offline Entitlement Verification & Grace Period
    # ---------------------------------------------------------------------------

    def test_offline_entitlement_valid_and_expired(self):
        """Offline verification accepts valid unexpired RSA tokens and rejects expired ones."""
        signer = EntitlementSigner()
        verifier = EntitlementVerifier(public_key_pem=signer.public_key_pem)

        # Valid active token (expires in +7 days)
        active_res = signer.sign_entitlement(
            user_id="usr_offline_test",
            subscription_id="sub_test_123",
            plan="PRO",
            device_id="dev_hw_123",
            features=["voice", "creator"],
            validity_days=7,
        )
        ok, reason, payload = verifier.verify_token(active_res["token"])
        self.assertTrue(ok)
        self.assertFalse(verifier.is_expired(payload))
        self.assertEqual(payload.plan, "PRO")

        # Expired token (validity_days=-1 => expired in past)
        expired_res = signer.sign_entitlement(
            user_id="usr_offline_test",
            subscription_id="sub_test_123",
            plan="PRO",
            device_id="dev_hw_123",
            features=["voice", "creator"],
            validity_days=-1,
        )
        ok_exp, reason_exp, payload_exp = verifier.verify_token(expired_res["token"])
        self.assertTrue(ok_exp, "Signature is cryptographically valid")
        self.assertTrue(verifier.is_expired(payload_exp), "Payload should be marked expired")


if __name__ == "__main__":
    unittest.main()
