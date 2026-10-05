"""
tests/test_admin_api.py — Verification of Admin Panel API Endpoints & Capabilities.
"""

import tempfile
import os
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from licensing_server.app import app
from licensing_server.config import config
from licensing_server.database import Base, UserDB, PaymentDB, get_db, PlanTier


class TestAdminApi(unittest.TestCase):

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.db_path = self.temp_db.name.replace("\\", "/")
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False, "timeout": 30.0},
        )
        with self.engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL;"))
            conn.commit()

        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()

        def override_get_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        self.admin_headers = {"X-Admin-Key": config.ADMIN_API_KEY or "charlie_admin_secret_key_2026"}

    def tearDown(self):
        app.dependency_overrides.clear()
        if hasattr(self, "client"):
            self.client.close()
        self.db.close()
        self.engine.dispose()
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass

    def test_admin_metrics_endpoint(self):
        res = self.client.get("/admin/api/metrics", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("revenue", data)
        self.assertIn("total_users", data)

    def test_admin_payments_endpoint(self):
        # Insert a sample payment
        user = UserDB(id="usr_pay_test", email="pay@test.local", password_hash="hash")
        payment = PaymentDB(
            id="pay_sample_123",
            user_id="usr_pay_test",
            payment_id="rzp_123456",
            order_id="order_123456",
            amount_paise=99900,
            plan="PRO",
            status="VERIFIED",
        )
        self.db.add(user)
        self.db.add(payment)
        self.db.commit()

        res = self.client.get("/admin/api/payments", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["total_count"], 1)
        self.assertEqual(data["items"][0]["payment_id"], "rzp_123456")
        self.assertEqual(data["items"][0]["amount_inr"], 999.0)

    def test_admin_activity_endpoint(self):
        res = self.client.get("/admin/api/activity", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.json(), list)

    def test_admin_profile_get_and_update(self):
        # 1. GET profile
        res = self.client.get("/admin/api/profile", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        profile = res.json()
        self.assertIn("permissions", profile)

        # 2. UPDATE profile
        res_update = self.client.post(
            "/admin/api/profile",
            headers=self.admin_headers,
            json={"display_name": "Chief Security Officer"},
        )
        self.assertEqual(res_update.status_code, 200)

    def test_llm_gateway_flow(self):
        # 1. GET config
        res = self.client.get("/admin/api/llm/config", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("primary_provider", data)
        self.assertIn("providers", data)

        # 2. POST update config
        update_payload = {
            "primary_provider": "groq",
            "active_model": "openai/gpt-oss-120b",
            "temperature": 0.85,
            "max_tokens": 8192,
        }
        res_post = self.client.post(
            "/admin/api/llm/config",
            headers=self.admin_headers,
            json=update_payload,
        )
        self.assertEqual(res_post.status_code, 200)

        # 3. GET telemetry
        res_telem = self.client.get("/admin/api/llm/telemetry", headers=self.admin_headers)
        self.assertEqual(res_telem.status_code, 200)
        t_data = res_telem.json()
        self.assertIn("total_tokens", t_data)
        self.assertIn("cost_inr", t_data)

    def test_remote_config_and_public_sync(self):
        # 1. GET remote config
        res = self.client.get("/admin/api/remote-config", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("feature_flags", data)
        self.assertIn("kill_switches", data)

        # 2. POST update
        res_post = self.client.post(
            "/admin/api/remote-config",
            headers=self.admin_headers,
            json={
                "feature_flags": {"study_cards": False, "voice_mode": True},
                "prompts": {"system_prompt_version": "v3.0.0"},
            },
        )
        self.assertEqual(res_post.status_code, 200)

        # 3. Client public endpoint
        res_pub = self.client.get("/admin/api/public/remote-config")
        self.assertEqual(res_pub.status_code, 200)
        pub_data = res_pub.json()
        self.assertFalse(pub_data["feature_flags"]["study_cards"])

    def test_push_broadcasts_lifecycle(self):
        # 1. Create notice
        res_create = self.client.post(
            "/admin/api/push/broadcasts",
            headers=self.admin_headers,
            json={
                "title": "Scheduled Nightly Patch",
                "message": "Servers updating at 02:00 UTC",
                "level": "MAINTENANCE",
                "target_tier": "ALL",
                "expires_hours": 24,
            },
        )
        self.assertEqual(res_create.status_code, 200)
        notice_id = res_create.json()["notice"]["id"]

        # 2. Admin list
        res_list = self.client.get("/admin/api/push/broadcasts", headers=self.admin_headers)
        self.assertEqual(res_list.status_code, 200)
        self.assertTrue(any(n["id"] == notice_id for n in res_list.json()))

        # 3. Client public list
        res_client = self.client.get("/admin/api/public/broadcasts")
        self.assertEqual(res_client.status_code, 200)
        self.assertTrue(any(n["id"] == notice_id for n in res_client.json()))

        # 4. Delete notice
        res_del = self.client.delete(f"/admin/api/push/broadcasts/{notice_id}", headers=self.admin_headers)
        self.assertEqual(res_del.status_code, 200)

    def test_ai_analytics_endpoint(self):
        res = self.client.get("/admin/api/ai-analytics", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("prompt_categories", data)
        self.assertIn("latency_benchmarks", data)
        self.assertIn("token_throughput", data)


if __name__ == "__main__":
    unittest.main()
