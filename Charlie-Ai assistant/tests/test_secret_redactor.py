"""Tests for Central Secret Redactor (Step 23C)."""

import unittest
from core.secret_redactor import (
    redact_text,
    redact_mapping,
    safe_exception,
    is_sensitive_key,
)


class TestSecretRedactor(unittest.TestCase):
    def test_redact_api_keys(self):
        gemini_fake = "AIzaSyFakeKeyForTesting1234567890"
        text = f"Error connecting with key {gemini_fake} to Gemini endpoint."
        redacted = redact_text(text)
        self.assertNotIn(gemini_fake, redacted)
        self.assertIn("[REDACTED_API_KEY]", redacted)

        groq_fake = "gsk_FakeGroqKeyForTesting123456789"
        text_groq = f"Groq error: key={groq_fake} is invalid"
        redacted_groq = redact_text(text_groq)
        self.assertNotIn(groq_fake, redacted_groq)
        self.assertIn("[REDACTED", redacted_groq)

    def test_redact_bearer_and_auth(self):
        token_fake = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.doNotLeakThisSignature"
        text = f"Header Authorization: Bearer {token_fake}"
        redacted = redact_text(text)
        self.assertNotIn(token_fake, redacted)
        self.assertIn("[REDACTED", redacted)

    def test_redact_passwords_and_parameters(self):
        text = "Connecting to DB: postgres://user:SuperSecretPassword123@localhost:5432/db"
        redacted = redact_text(text)
        self.assertNotIn("SuperSecretPassword123", redacted)
        self.assertIn("[REDACTED_PASSWORD]", redacted)

        param_text = "Login failed: username=admin password=MySecretPassword123! session_key=sk_live_998877"
        redacted_param = redact_text(param_text)
        self.assertNotIn("MySecretPassword123!", redacted_param)
        self.assertNotIn("sk_live_998877", redacted_param)

    def test_redact_mapping_immutability(self):
        original = {
            "user_name": "CharlieUser",
            "gemini_api_key": "AIzaSyFakeKey1234567890",
            "plugin_config": {
                "spotify": {
                    "client_id": "spot_id_123",
                    "client_secret": "spot_secret_456",
                    "redirect_uri": "http://localhost:8888",
                }
            },
        }
        cleaned = redact_mapping(original)

        # Original is not mutated
        self.assertEqual(original["gemini_api_key"], "AIzaSyFakeKey1234567890")
        self.assertEqual(original["plugin_config"]["spotify"]["client_secret"], "spot_secret_456")

        # Cleaned copy is redacted
        self.assertEqual(cleaned["user_name"], "CharlieUser")
        self.assertEqual(cleaned["gemini_api_key"], "[REDACTED]")
        self.assertEqual(cleaned["plugin_config"]["spotify"]["client_secret"], "[REDACTED]")
        self.assertEqual(cleaned["plugin_config"]["spotify"]["redirect_uri"], "http://localhost:8888")

    def test_safe_exception(self):
        try:
            raise ValueError("Failed auth with secret password=P@ssw0rd123456 and AIzaSyFakeKey9876543210")
        except Exception as e:
            msg = safe_exception(e, include_traceback=True)
            self.assertNotIn("P@ssw0rd123456", msg)
            self.assertNotIn("AIzaSyFakeKey9876543210", msg)
            self.assertIn("[REDACTED", msg)


if __name__ == "__main__":
    unittest.main()
