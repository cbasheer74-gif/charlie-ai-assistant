"""
tests/test_auth_rbac.py — Authentication, Session Revocation, and RBAC Role Gating Tests.
"""

import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from licensing_server.app import app
from licensing_server.config import config
from licensing_server.database import Base, UserDB, get_db, UserRole
from licensing_server.services.auth_service import AuthService


class TestAuthRBAC(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )
        Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine, expire_on_commit=False)

        def override_get_db():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)
        cls.auth_service = AuthService()

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=cls.engine)

    def test_01_user_registration_and_hash(self):
        """Registering user stores salted bcrypt hash, never plaintext."""
        db = self.Session()
        try:
            res = self.client.post(
                "/auth/register",
                json={"email": "rbac_user@charlie.ai", "password": "SecurePassword123!", "display_name": "RBAC Test"},
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["success"])

            user = db.query(UserDB).filter(UserDB.email == "rbac_user@charlie.ai").first()
            self.assertIsNotNone(user)
            self.assertNotEqual(user.password_hash, "SecurePassword123!")
            self.assertTrue(user.password_hash.startswith("$2b$") or user.password_hash.startswith("$2a$"))
        finally:
            db.close()

    def test_02_login_invalid_password_rejection(self):
        """Login with wrong password fails."""
        res = self.client.post(
            "/auth/login",
            json={"email": "rbac_user@charlie.ai", "password": "WrongPassword999!"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["success"])

    def test_03_login_and_token_generation(self):
        """Login with correct credentials returns valid JWT."""
        res = self.client.post(
            "/auth/login",
            json={"email": "rbac_user@charlie.ai", "password": "SecurePassword123!"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        token = data["data"]["access_token"]

        # Authenticate /me
        me_res = self.client.get("/me/", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me_res.status_code, 200)
        self.assertEqual(me_res.json()["email"], "rbac_user@charlie.ai")

    def test_04_session_revocation_via_version(self):
        """Incrementing session_version in database instantly revokes active JWT."""
        db = self.Session()
        try:
            # Login to get token
            res = self.client.post(
                "/auth/login",
                json={"email": "rbac_user@charlie.ai", "password": "SecurePassword123!"},
            )
            token = res.json()["data"]["access_token"]

            # Verify token works
            me_res = self.client.get("/me/", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(me_res.status_code, 200)

            # Invalidate session in DB
            user = db.query(UserDB).filter(UserDB.email == "rbac_user@charlie.ai").first()
            user.session_version = (user.session_version or 1) + 1
            db.commit()

            # Token should now be rejected as expired/invalid
            revoked_res = self.client.get("/me/", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(revoked_res.status_code, 401)
        finally:
            db.close()

    def test_05_rbac_customer_denied_admin(self):
        """Regular customer token is denied access to admin endpoints."""
        db = self.Session()
        try:
            user = db.query(UserDB).filter(UserDB.email == "rbac_user@charlie.ai").first()
            token = self.auth_service.create_access_token(
                user.id, user.email, role="CUSTOMER", session_version=user.session_version or 1
            )
            admin_res = self.client.get("/admin/api/metrics", headers={"Authorization": f"Bearer {token}"})
            self.assertIn(admin_res.status_code, [401, 403])
        finally:
            db.close()

    def test_06_rbac_admin_permitted(self):
        """Admin token is permitted access to admin endpoints."""
        db = self.Session()
        try:
            admin_user = UserDB(
                id="usr_admin_test",
                email="admin_test@charlie.ai",
                password_hash="hashed_pw",
                role=UserRole.ADMIN.value,
            )
            db.add(admin_user)
            db.commit()

            admin_token = self.auth_service.create_access_token(
                admin_user.id, admin_user.email, role=UserRole.ADMIN.value, session_version=1
            )
            admin_res = self.client.get("/admin/api/metrics", headers={"Authorization": f"Bearer {admin_token}"})
            self.assertEqual(admin_res.status_code, 200)
            self.assertIn("total_users", admin_res.json())
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
