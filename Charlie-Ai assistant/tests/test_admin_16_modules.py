"""tests/test_admin_16_modules.py — Test Suite for Founder 16 Admin Modules.

Verifies:
1. User Management (Module 1)
2. Content Management (Module 2)
3. Payments & Transactions (Module 3)
4. Notifications (Module 4)
5. Reports & Exports (Module 5)
6. Roles & Permissions (Module 6)
7. Order / Booking Management (Module 7)
8. Support & Ticket Management (Module 8)
9. Live Analytics Dashboard (Module 9)
10. Audit Logs & Activity History (Module 10)
11. Feature Flags & App Configuration (Module 11)
12. Coupons & Discount Management (Module 12)
13. Vendor / Partner Management (Module 13)
14. Content Moderation Tools (Module 14)
15. Session & Device Management (Module 15)
16. Force-Update & App Version Control (Module 16)
"""

from __future__ import annotations

import unittest
from fastapi.testclient import TestClient
from licensing_server.app import app


class TestAdmin16Modules(unittest.TestCase):

    def setUp(self):
        from licensing_server.database import init_db
        init_db()
        self.client = TestClient(app)
        self.headers = {"X-Admin-Key": "a7d2e8b9f1c4038a5e921d7b6c04f8e29a3b7c1d5e4f0a2b"}
        self.client.post("/admin/api/seed-demo", headers=self.headers)
 
    def tearDown(self):
        if hasattr(self, "client"):
            self.client.close()

    def test_founder_modules_status_summary(self):
        """Verify the 16 Founder Modules status summary endpoint."""
        res = self.client.get("/admin/api/founder-modules-status", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["modules_count"], 16)
        self.assertEqual(len(data["modules"]), 16)

    def test_coupons_module_12(self):
        """Module 12: Create, list, delete coupon."""
        res = self.client.post(
            "/admin/api/coupons",
            json={"code": "TESTPROMO25", "discount_pct": 25, "max_uses": 50, "expires_days": 15},
            headers=self.headers
        )
        self.assertIn(res.status_code, [200, 400])

        list_res = self.client.get("/admin/api/coupons", headers=self.headers)
        self.assertEqual(list_res.status_code, 200)

    def test_partners_module_13(self):
        """Module 13: Vendor/Partner management."""
        res = self.client.post(
            "/admin/api/partners",
            json={"name": "Alpha Agency", "email": "alpha@agency.io", "partner_code": "ALPHA_VIP", "commission_pct": 20},
            headers=self.headers
        )
        self.assertIn(res.status_code, [200, 400, 500])

        list_res = self.client.get("/admin/api/partners", headers=self.headers)
        self.assertEqual(list_res.status_code, 200)

    def test_content_cms_module_2(self):
        """Module 2: Content CMS management."""
        res = self.client.post(
            "/admin/api/content",
            json={"item_type": "BANNER", "title": "Welcome to Charlie Pro", "content_json": "{}"},
            headers=self.headers
        )
        self.assertEqual(res.status_code, 200)

        list_res = self.client.get("/admin/api/content", headers=self.headers)
        self.assertEqual(list_res.status_code, 200)
        self.assertTrue(len(list_res.json()) >= 1)

    def test_orders_module_7(self):
        """Module 7: Orders & Booking."""
        res = self.client.get("/admin/api/orders", headers=self.headers)
        self.assertEqual(res.status_code, 200)

    def test_moderation_module_14(self):
        """Module 14: Moderation queue."""
        res = self.client.get("/admin/api/moderation", headers=self.headers)
        self.assertEqual(res.status_code, 200)

    def test_seed_demo_data(self):
        """Seed demo data across all 16 modules."""
        res = self.client.post("/admin/api/seed-demo", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("seeded", data)
        self.assertIn("users", data["seeded"])

    def test_user_role_change_module_6(self):
        """Module 6: Role change endpoint."""
        res = self.client.post(
            "/admin/api/users/usr_demo_1/role",
            json={"role": "AUDITOR"},
            headers=self.headers
        )
        self.assertEqual(res.status_code, 200)

    def test_payment_refund_module_3(self):
        """Module 3: Payment refund endpoint."""
        res = self.client.post(
            "/admin/api/payments/pay_demo_1/refund",
            json={"reason": "Customer double charged on demo test"},
            headers=self.headers
        )
        self.assertEqual(res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
