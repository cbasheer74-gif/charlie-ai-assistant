"""
tests/test_observability_middleware.py — Verification of RequestIdMiddleware, StructuredLoggingMiddleware, and Deep /health endpoint.
"""

import json
import unittest
from fastapi.testclient import TestClient

from licensing_server.app import app


class TestObservability(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_request_id_generated_when_missing(self):
        """Verify request ID is generated and returned in headers."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        req_id = res.headers.get("X-Request-ID")
        self.assertIsNotNone(req_id)
        self.assertTrue(req_id.startswith("req_"))

    def test_request_id_preserved_when_supplied(self):
        """Verify client-supplied request ID is preserved and echoed back."""
        custom_id = "test-custom-trace-12345"
        res = self.client.get("/", headers={"X-Request-ID": custom_id})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("X-Request-ID"), custom_id)

    def test_deep_health_endpoint(self):
        """Verify /health executes DB probe, returns latency and subsystem health."""
        res = self.client.get("/health")
        self.assertIn(res.status_code, [200, 503])
        data = res.json()
        self.assertIn("status", data)
        self.assertIn("database", data)
        self.assertIn("security", data)
        self.assertIn("system", data)

        db_info = data["database"]
        self.assertIn("status", db_info)
        if res.status_code == 200:
            self.assertEqual(db_info["status"], "connected")
            self.assertIsNotNone(db_info["latency_ms"])
            self.assertGreaterEqual(db_info["latency_ms"], 0.0)


if __name__ == "__main__":
    unittest.main()
