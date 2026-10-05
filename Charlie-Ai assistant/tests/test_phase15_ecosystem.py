"""tests/test_phase15_ecosystem.py — Verification of Phase 15 Ecosystem Additions:

1. Plugin Marketplace & Dynamic Package Manager
2. Offline LLM Ollama Provider Fallback
3. Audio Hardware Hot-Swapping & Dynamic Router
4. Automated Crash Reporter & Telemetry Hook
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from core.audio_router import AudioDeviceRouter, get_audio_router
from core.plugin_marketplace import PluginMarketplace, PluginSecurityScanner, get_plugin_marketplace
from engine.ai.ollama_provider import OllamaProvider, get_ollama_provider
from engine.deployment.crash_reporter import CrashReporter, ErrorLevel, get_crash_reporter, install_global_crash_hook


class TestPhase15Ecosystem(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="charlie_eco_test_"))
        self.plugins_dir = self.test_dir / "plugins"
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # ── 1. Plugin Marketplace ────────────────────────────────────────────────

    def test_marketplace_catalog_and_install_lifecycle(self):
        marketplace = PluginMarketplace(plugins_dir=self.plugins_dir)

        # Catalog listing
        catalog = marketplace.list_catalog()
        self.assertGreaterEqual(len(catalog), 4)

        # Safe installation of a catalog plugin
        ok, msg = marketplace.install_plugin("pomodoro_timer")
        self.assertTrue(ok)
        self.assertTrue((self.plugins_dir / "pomodoro_timer.py").exists())

        # Security AST Scanner blocks dangerous code
        dangerous_code = 'import os\nos.system("rmdir /s /q c:\\\\")'
        score, warnings = PluginSecurityScanner.scan_code(dangerous_code)
        self.assertLess(score, 0.8)
        self.assertTrue(len(warnings) > 0)

        # Attempt to install dangerous code gets rejected
        bad_ok, bad_msg = marketplace.install_plugin("malicious_plugin", code=dangerous_code)
        self.assertFalse(bad_ok)
        self.assertIn("rejected", bad_msg)

        # Uninstall lifecycle
        un_ok, un_msg = marketplace.uninstall_plugin("pomodoro_timer")
        self.assertTrue(un_ok)
        self.assertFalse((self.plugins_dir / "pomodoro_timer.py").exists())

    # ── 2. Offline LLM Ollama Provider ───────────────────────────────────────

    def test_ollama_provider_defaults_and_selection(self):
        provider = OllamaProvider(host="http://127.0.0.1:11434")

        # Preferred model pick
        best_model = provider.pick_best_model()
        self.assertIsInstance(best_model, str)
        self.assertTrue(len(best_model) > 0)

        # Availability check (gracefully returns False if daemon not active locally)
        available = provider.is_available(timeout=0.2)
        self.assertIsInstance(available, bool)

    # ── 3. Audio Device Hot-Swapping Router ───────────────────────────────────

    def test_audio_device_router_priority_and_events(self):
        router = AudioDeviceRouter(check_interval=0.1)

        # Priority selection: Headset > USB > Realtek
        candidates = ["Realtek Audio", "USB Headset Microphone", "Default Line In"]
        best = router.select_best_device("input", candidates)
        self.assertEqual(best, "USB Headset Microphone")

        candidates_out = ["Generic Speakers", "Bose Wireless Headphones", "Realtek High Definition Audio"]
        best_out = router.select_best_device("output", candidates_out)
        self.assertEqual(best_out, "Bose Wireless Headphones")

        # Event callback verification
        events = []
        router.add_change_callback(lambda d, old, new: events.append((d, old, new)))
        router._handle_device_change("input", added={"USB Headset Microphone"}, removed=set())
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "input")

    # ── 4. Crash Telemetry & Global Exception Hook ───────────────────────────

    def test_crash_reporter_and_global_hook(self):
        reporter = CrashReporter()

        # Record synthetic crash
        try:
            raise ValueError("Test synthetic exception for diagnostic telemetry")
        except Exception as e:
            event = reporter.record_crash(
                component="TestComponent",
                error=e,
                stack_trace="Traceback (most recent call last): test line 42",
                error_level=ErrorLevel.ERROR,
            )

        self.assertIsNotNone(event)
        self.assertTrue(event.crash_id.startswith("CHARLIE-CRASH-"))
        self.assertIn("Test synthetic exception", event.sanitized_message)

        # Install global hook
        install_global_crash_hook()
        self.assertNotEqual(sys.excepthook, sys.__excepthook__)


if __name__ == "__main__":
    unittest.main()
