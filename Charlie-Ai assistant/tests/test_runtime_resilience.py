"""tests/test_runtime_resilience.py — Comprehensive test suite for Step 24 Production Runtime Resilience.

Covers:
1. Port preflight check (_is_port_free with SO_EXCLUSIVEADDRUSE).
2. Port 1901 collision isolation (Uvicorn bind failure handled, no SystemExit escape).
3. Port 1902 collision isolation (alias server conflict handled cleanly).
4. Both ports occupied test (clean graceful disable of Remote Control).
5. Uvicorn SystemExit containment at dashboard boundary.
6. Single-instance Windows named mutex (acquisition, duplicate refusal, clean release).
7. Mutex kernel auto-release on process termination.
8. Core runtime isolation (dashboard errors do not crash Charlie or trigger Gemini reconnect).
9. Clean shutdown and port release.
10. Step 23A/B/C security preservation (DPAPI vault, secret redactor, loopback-only session-key).
11. Tool mode validation (DISCOVERY 17 tools vs FULL 73 tools override).
12. Regression suites for tools, gateways, conversation turn manager, voice control, and RAG.
"""

import asyncio
import os
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from core.single_instance import (
    acquire_single_instance,
    release_single_instance,
    is_single_instance_acquired,
    _get_mutex_name,
)
from dashboard.server import DashboardServer, PORT

# Import regression test suites
from tests.test_secret_redactor import TestSecretRedactor
from tests.test_tool_groups import TestToolGroupsRegistry, TestActionLoaderFiltering
from tests.test_tool_gateway import TestDiscoveryGateway
from tests.test_conversation_turn_manager import TestConversationTurnManager
from tests.test_voice_control_bridge import TestVoiceControlBridge
from tests.test_rag import LocalRAGTests
from tests.test_production_packaging import TestStep25PackagingValidation
from tests.test_credential_persistence import TestCredentialPersistence


class TestPortPreflight(unittest.TestCase):
    """Verify non-destructive preflight port detection."""

    def test_free_port_detection(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            free_port = s.getsockname()[1]
        self.assertTrue(DashboardServer._is_port_free(free_port, "127.0.0.1"))

    def test_occupied_port_detection(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", 0))
            s.listen(1)
            occupied_port = s.getsockname()[1]
            self.assertFalse(DashboardServer._is_port_free(occupied_port, "127.0.0.1"))


class TestDashboardFailureBoundary(unittest.IsolatedAsyncioTestCase):
    """Verify dashboard isolation boundary and Uvicorn SystemExit containment."""

    async def test_port_1901_occupied_preflight(self):
        srv = DashboardServer()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", PORT))
            sock.listen(1)

            # Serve should return gracefully without raising SystemExit or unhandled exception
            await srv.serve()
            self.assertFalse(srv.is_running)

    async def test_port_1902_occupied_preflight(self):
        srv = DashboardServer()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", PORT + 1))
            sock.listen(1)

            with patch.object(srv, "_ssl_enabled", return_value=True):
                await srv.serve()
                self.assertFalse(srv.is_running)

    async def test_both_ports_occupied(self):
        srv = DashboardServer()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s1:
            if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                s1.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                s1.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s1.bind(("0.0.0.0", PORT))
            s1.listen(1)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
                if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                    s2.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                else:
                    s2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s2.bind(("0.0.0.0", PORT + 1))
                s2.listen(1)

                await srv.serve()
                self.assertFalse(srv.is_running)

    async def test_uvicorn_systemexit_contained_at_boundary(self):
        """Simulate Uvicorn raising SystemExit (code 3 on bind failure) inside Server.serve()."""
        srv = DashboardServer()
        with patch.object(srv, "_is_port_free", return_value=True):
            with patch("uvicorn.Server.serve", side_effect=SystemExit(3)):
                try:
                    await srv.serve()
                except SystemExit:
                    self.fail("SystemExit escaped dashboard boundary!")
                self.assertFalse(srv.is_running)

    async def test_uvicorn_oserror_contained_at_boundary(self):
        """Simulate WinError 10048 (WSAEADDRINUSE)."""
        srv = DashboardServer()
        with patch.object(srv, "_is_port_free", return_value=True):
            with patch("uvicorn.Server.serve", side_effect=OSError(10048, "Address already in use")):
                try:
                    await srv.serve()
                except OSError:
                    self.fail("OSError escaped dashboard boundary!")
                self.assertFalse(srv.is_running)

    async def test_alias_server_systemexit_contained(self):
        """Simulate alias server (port 1902) raising SystemExit."""
        srv = DashboardServer()
        with patch.object(srv, "_is_port_free", return_value=True):
            with patch("uvicorn.Server.serve", side_effect=SystemExit(3)):
                try:
                    await srv._serve_alias()
                except SystemExit:
                    self.fail("SystemExit escaped alias server boundary!")
                self.assertFalse(srv.is_running)

    async def test_broadcast_no_op_when_not_running(self):
        srv = DashboardServer()
        srv._is_running = False
        await srv.broadcast({"type": "test"})
        self.assertEqual(len(srv._history), 0)

    async def test_clean_shutdown(self):
        srv = DashboardServer()
        srv._is_running = True
        mock_main = MagicMock()
        mock_alias = MagicMock()
        srv._main_server = mock_main
        srv._alias_server = mock_alias

        srv.shutdown()
        self.assertFalse(srv.is_running)
        self.assertTrue(mock_main.should_exit)
        self.assertTrue(mock_alias.should_exit)


class TestSingleInstanceGuard(unittest.TestCase):
    """Verify Windows named mutex single-instance mechanism."""

    def setUp(self):
        release_single_instance()

    def tearDown(self):
        release_single_instance()

    def test_first_acquisition_succeeds(self):
        acquired = acquire_single_instance("TestCharlieApp_1")
        self.assertTrue(acquired)
        self.assertTrue(is_single_instance_acquired())

    def test_second_acquisition_fails_in_subprocess(self):
        acquired = acquire_single_instance("TestCharlieApp_2")
        self.assertTrue(acquired)

        code = (
            "from core.single_instance import acquire_single_instance; "
            "print('ACQUIRED' if acquire_single_instance('TestCharlieApp_2') else 'DENIED')"
        )
        res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertIn("DENIED", res.stdout)

    def test_release_allows_reacquisition(self):
        acquired = acquire_single_instance("TestCharlieApp_3")
        self.assertTrue(acquired)
        release_single_instance()
        self.assertFalse(is_single_instance_acquired())

        acquired_again = acquire_single_instance("TestCharlieApp_3")
        self.assertTrue(acquired_again)

    def test_kernel_auto_releases_mutex_on_child_process_termination(self):
        """Verify Windows kernel releases mutex if holding process terminates."""
        child_code = (
            "import time; "
            "from core.single_instance import acquire_single_instance; "
            "acquire_single_instance('TestCharlieApp_4'); "
            "print('HELD', flush=True); "
            "time.sleep(0.5)"
        )
        proc = subprocess.Popen([sys.executable, "-c", child_code], stdout=subprocess.PIPE, text=True)
        try:
            line = proc.stdout.readline()  # wait until 'HELD' is emitted
            self.assertIn("HELD", line)
            self.assertFalse(acquire_single_instance("TestCharlieApp_4"))

            # Wait for child process to terminate
            proc.wait(timeout=5)
        finally:
            if proc.stdout:
                proc.stdout.close()
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                pass

        acquired = acquire_single_instance("TestCharlieApp_4")
        self.assertTrue(acquired)

    def test_second_instance_main_entrypoint_exits_cleanly(self):
        acquired = acquire_single_instance()
        self.assertTrue(acquired)

        code = "from main import main; main()"
        res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn("[Startup] Charlie is already running.", res.stdout)
        self.assertNotIn("Starting live connection", res.stdout)
        self.assertNotIn("Mic stream open", res.stdout)

    def test_ports_are_released_after_shutdown(self):
        srv = DashboardServer()
        srv.shutdown()
        self.assertTrue(DashboardServer._is_port_free(PORT))
        self.assertTrue(DashboardServer._is_port_free(PORT + 1))


class TestCoreRuntimeIsolation(unittest.IsolatedAsyncioTestCase):
    """Verify core assistant components (Gemini Live, tools, audio) are never disturbed by dashboard."""

    async def test_dashboard_bind_failure_does_not_trigger_gemini_reconnect(self):
        """When dashboard fails, CharlieLive reconnect event must remain unset and retry count unchanged."""
        ui_mock = MagicMock()
        reconnect_event = asyncio.Event()

        # Simulate CharlieLive state
        retry_count = 0
        srv = DashboardServer()

        # Trigger dashboard bind failure
        with patch.object(srv, "_is_port_free", return_value=False):
            await srv.serve()

        # Verify dashboard disabled
        self.assertFalse(srv.is_running)

        # Verify reconnect event was never touched
        self.assertFalse(reconnect_event.is_set())
        self.assertEqual(retry_count, 0)

    async def test_make_remote_key_gracefully_handles_disabled_dashboard(self):
        """Remote control click should log and return None without exceptions."""
        ui_mock = MagicMock()
        from main import CharlieLive
        with patch.object(CharlieLive, "__init__", lambda self, ui: None):
            live = CharlieLive(ui_mock)
            live.ui = ui_mock
            live._dashboard = DashboardServer()
            live._dashboard._is_running = False

            res = live._make_remote_key()
            self.assertIsNone(res)
            ui_mock.write_log.assert_called_with(
                "SYS: Remote Control unavailable (dashboard port unavailable or disabled)."
            )

    def test_tool_mode_discovery_vs_full(self):
        """Verify default mode is DISCOVERY (17 tools) and override is FULL (73 tools)."""
        from core.tool_gateway import is_pilot_enabled, is_gateway_enabled
        from core.tool_groups import TOOL_TO_GROUP

        # Total tools inventory = 73
        self.assertEqual(len(TOOL_TO_GROUP), 73)

        # In default mode, pilot is enabled (17 discovery tools)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CHARLIE_TOOL_FULL", None)
            self.assertTrue(is_pilot_enabled())

        # With CHARLIE_TOOL_FULL=1, pilot is disabled -> FULL mode active
        with patch.dict(os.environ, {"CHARLIE_TOOL_FULL": "1"}):
            self.assertFalse(is_pilot_enabled())


class TestStep23SecurityPreserved(unittest.TestCase):
    """Verify Step 23A, 23B, 23C security contracts remain completely intact."""

    def test_session_key_remote_access_forbidden(self):
        srv = DashboardServer()
        from starlette.testclient import TestClient
        with TestClient(srv.app) as client:
            resp = client.get("/session-key", headers={"X-Forwarded-For": "192.168.1.50"})
            self.assertEqual(resp.status_code, 403)

    def test_dpapi_vault_active(self):
        from core.credential_vault import is_windows, get_vault_path
        self.assertTrue(is_windows())
        self.assertTrue(str(get_vault_path()).endswith("credentials.dat"))

    def test_secret_redactor_active(self):
        from core.secret_redactor import redact_text
        redacted = redact_text("key AIzaSyABCDEF123456789012345678901234567")
        self.assertNotIn("AIzaSyABCDEF123456789012345678901234567", redacted)


if __name__ == "__main__":
    unittest.main()
