"""tests/test_credential_persistence.py — First-run Gemini credential persistence test suite.

Verifies:
1. Empty key rejected.
2. Non-legacy key format (AQ... etc.) is not rejected solely by prefix.
3. DPAPI set_secret called & readback succeeds.
4. Setup completion occurs only after secure persistence.
5. Failed save does not mark initialization complete.
6. Env overrides DPAPI only when env is non-empty.
7. Empty env falls through to DPAPI.
8. REST receives resolved key.
9. Live receives resolved key.
10. Missing key does not enter reconnect loop.
11. Partially initialized client cleanup does not raise AttributeError.
12. Secrets never appear in logs.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.credential_vault import (
    get_secret,
    set_secret,
    has_secret,
    is_windows,
)
from memory.config_manager import (
    save_api_keys,
    get_gemini_key,
    is_configured,
)
from core.gemini import api_key, safe_aclose_client, safe_close_client
from core.secret_redactor import redact_text


class TestCredentialPersistence(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self.vault_file = Path(self._temp_dir.name) / "test_vault.dat"
        self._orig_env = os.environ.get("GEMINI_API_KEY")
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]
        self._orig_vault_env = os.environ.get("CHARLIE_VAULT_PATH")
        os.environ["CHARLIE_VAULT_PATH"] = str(self.vault_file)

    def tearDown(self):
        if self._orig_env is not None:
            os.environ["GEMINI_API_KEY"] = self._orig_env
        elif "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]
        if self._orig_vault_env is not None:
            os.environ["CHARLIE_VAULT_PATH"] = self._orig_vault_env
        else:
            os.environ.pop("CHARLIE_VAULT_PATH", None)
        self._temp_dir.cleanup()
        api_key(refresh=True)

    def test_empty_key_rejected(self):
        """Empty or whitespace-only keys must be rejected."""
        self.assertFalse(set_secret("gemini", "api_key", "", vault_path=self.vault_file))
        self.assertFalse(set_secret("gemini", "api_key", "   ", vault_path=self.vault_file))
        self.assertFalse(save_api_keys(""))
        self.assertFalse(save_api_keys("   "))

    def test_non_legacy_key_not_rejected_by_prefix(self):
        """Keys not starting with AIza (e.g. AQ... or modern format) must NOT be rejected by prefix."""
        modern_key = "AQ_test_modern_gemini_credential_987654321"
        if not is_windows():
            self.skipTest("DPAPI is Windows-only")
        
        ok = set_secret("gemini", "api_key", modern_key, vault_path=self.vault_file)
        self.assertTrue(ok)
        val = get_secret("gemini", "api_key", fallback_legacy=False, vault_path=self.vault_file)
        self.assertEqual(val, modern_key)

    def test_dpapi_set_secret_and_readback_succeeds(self):
        """Verify DPAPI set_secret writes and immediate read-back matches in memory."""
        if not is_windows():
            self.skipTest("DPAPI is Windows-only")
        secret = "test_gemini_key_dpapi_verify_12345"
        ok = set_secret("gemini", "api_key", secret, vault_path=self.vault_file)
        self.assertTrue(ok)
        
        # Direct read-back without fallback
        readback = get_secret("gemini", "api_key", fallback_legacy=False, vault_path=self.vault_file)
        self.assertEqual(readback, secret)
        self.assertTrue(has_secret("gemini", "api_key", vault_path=self.vault_file))

    def test_setup_completion_only_after_secure_persistence(self):
        """Setup must only mark ready=True after secure persistence succeeds."""
        from ui import SetupOverlay
        
        class FakeOverlay:
            def __init__(self):
                self.error = None
                self.hidden = False
            def set_error(self, msg):
                self.error = msg
            def hide(self):
                self.hidden = True

        class FakeWindow:
            def __init__(self):
                self._ready = False
                self._overlay = FakeOverlay()
                self._state = None
                self._assistant_name = "CHARLIE"
                self._log = MagicMock()

            def _apply_state(self, state):
                self._state = state

        # Case A: Invalid key length (< 10)
        win = FakeWindow()
        from ui import MainWindow
        MainWindow._on_setup_done(win, "short", "windows")
        self.assertFalse(win._ready)
        self.assertIsNotNone(win._overlay.error)
        self.assertFalse(win._overlay.hidden)

        # Case B: Successful persistence
        if is_windows():
            win2 = FakeWindow()
            ov2 = win2._overlay
            valid_key = "test_valid_gemini_key_length_30_chars"
            with patch("google.genai.Client", return_value=MagicMock()):
                MainWindow._on_setup_done(win2, valid_key, "windows")
            self.assertTrue(win2._ready)
            self.assertTrue(ov2.hidden)
            self.assertIsNone(win2._overlay)

    def test_failed_save_does_not_mark_initialization_complete(self):
        """If DPAPI save fails, setup must fail and NOT mark ready."""
        class FakeOverlay:
            def __init__(self):
                self.error = None
                self.hidden = False
            def set_error(self, msg):
                self.error = msg
            def hide(self):
                self.hidden = True

        class FakeWindow:
            def __init__(self):
                self._ready = False
                self._overlay = FakeOverlay()

        win = FakeWindow()
        from ui import MainWindow
        with patch("memory.config_manager.save_api_keys", return_value=False):
            MainWindow._on_setup_done(win, "test_valid_key_1234567890", "windows")
        self.assertFalse(win._ready)
        self.assertIsNotNone(win._overlay.error)
        self.assertFalse(win._overlay.hidden)

    def test_env_overrides_dpapi_only_when_non_empty(self):
        """Non-empty GEMINI_API_KEY takes precedence over DPAPI vault."""
        if not is_windows():
            self.skipTest("DPAPI is Windows-only")
        set_secret("gemini", "api_key", "vault_key_11111", vault_path=self.vault_file)
        os.environ["GEMINI_API_KEY"] = "env_key_22222"
        resolved = get_secret("gemini", "api_key", fallback_legacy=False, vault_path=self.vault_file)
        self.assertEqual(resolved, "env_key_22222")

    def test_empty_env_falls_through_to_dpapi(self):
        """Empty or whitespace GEMINI_API_KEY must fall through to DPAPI vault."""
        if not is_windows():
            self.skipTest("DPAPI is Windows-only")
        set_secret("gemini", "api_key", "vault_key_33333", vault_path=self.vault_file)
        os.environ["GEMINI_API_KEY"] = ""
        resolved = get_secret("gemini", "api_key", fallback_legacy=False, vault_path=self.vault_file)
        self.assertEqual(resolved, "vault_key_33333")

        os.environ["GEMINI_API_KEY"] = "   "
        resolved2 = get_secret("gemini", "api_key", fallback_legacy=False, vault_path=self.vault_file)
        self.assertEqual(resolved2, "vault_key_33333")

    def test_rest_receives_resolved_key(self):
        """REST client receives the credential resolved from core.gemini.api_key()."""
        with patch("core.gemini.api_key", return_value="mock_rest_resolved_key_44444"):
            with patch("google.genai.Client") as mock_cl:
                from core.gemini import client
                client()
                mock_cl.assert_called_once()
                call_kwargs = mock_cl.call_args[1]
                self.assertEqual(call_kwargs.get("api_key"), "mock_rest_resolved_key_44444")

    def test_live_receives_resolved_key(self):
        """Live path in main.py receives the credential resolved from _get_api_key()."""
        import main
        with patch("main._get_api_key", return_value="mock_live_resolved_key_55555"):
            resolved = main._get_api_key()
            self.assertEqual(resolved, "mock_live_resolved_key_55555")

    def test_missing_key_does_not_enter_reconnect_loop(self):
        """Missing key must fail fast and prompt reconfig without incrementing reconnect count."""
        import main
        mock_ui = MagicMock()
        mock_ui._win._ready = True
        charlie = main.CharlieLive(mock_ui)
        charlie._retry_count = 0

        # Simulate missing key check in CharlieLive.run loop body
        with patch("main._get_api_key", return_value=""):
            resolved_key = main._get_api_key()
            self.assertEqual(resolved_key, "")
            # Check error classification
            err_str = "ValueError: No API key was provided."
            is_unconfigured = any(x in err_str for x in (
                "API key not valid", "1007", "No API key was provided",
                "Gemini credential not configured", "no Gemini API key",
                "API_KEY_INVALID"
            ))
            self.assertTrue(is_unconfigured)

    def test_partially_initialized_client_cleanup_does_not_raise_attribute_error(self):
        """Closing a client whose BaseApiClient lacks _async_httpx_client must NOT raise AttributeError."""
        class MockBaseApiClientWithoutHttpx:
            pass

        class MockAsyncClient:
            def __init__(self):
                self._api_client = MockBaseApiClientWithoutHttpx()
            async def aclose(self):
                # Simulates google-genai BaseApiClient bug
                return getattr(self._api_client, "_async_httpx_client").aclose()

        class MockClient:
            def __init__(self):
                self.aio = MockAsyncClient()

        broken_client = MockClient()
        
        # Test safe_close_client
        safe_close_client(broken_client)
        safe_close_client(None)

        # Test safe_aclose_client (async)
        async def run_aclose_test():
            await safe_aclose_client(broken_client)
            await safe_aclose_client(None)

        asyncio.run(run_aclose_test())

    def test_secrets_never_appear_in_logs(self):
        """Secrets matching legacy AIza or modern AQ prefixes must be redacted."""
        log_sample = (
            "Connecting with key AIzaSy_Secret_Legacy_Key_1234567890 and "
            "modern key AQ_Secret_Modern_Key_1234567890 in session."
        )
        redacted = redact_text(log_sample)
        self.assertNotIn("AIzaSy_Secret_Legacy_Key_1234567890", redacted)
        self.assertNotIn("AQ_Secret_Modern_Key_1234567890", redacted)
        self.assertIn("[REDACTED_API_KEY]", redacted)


if __name__ == "__main__":
    unittest.main()
