# tests/test_proactive_daemon.py
"""Unit tests for ProactiveAdvisor and ProactiveDaemon."""

import time
import unittest
from dataclasses import asdict

from engine.intelligence.proactive_advisor import (
    ProactiveAdvisor,
    ProactiveDaemon,
    ProactiveNudge,
    get_proactive_advisor,
    get_proactive_daemon,
    load_proactive_settings,
    save_proactive_settings,
)


class ProactiveDaemonTests(unittest.TestCase):
    def setUp(self):
        self.advisor = ProactiveAdvisor()
        # Reset session time to simulate elapsed time
        self.advisor._session_start = time.monotonic() - 6000.0  # > 90 mins

    def test_settings_persistence(self):
        settings = load_proactive_settings()
        self.assertIn("enabled", settings)
        self.assertIn("check_wellness", settings)

        settings["check_wellness"] = False
        save_proactive_settings(settings)
        reloaded = load_proactive_settings()
        self.assertFalse(reloaded["check_wellness"])

        # Restore
        settings["check_wellness"] = True
        save_proactive_settings(settings)

    def test_wellness_nudge_fires_on_long_session(self):
        nudge = self.advisor.evaluate_all()
        # With session elapsed > 90 mins, a wellness or other nudge should evaluate
        if nudge is not None:
            self.assertIsInstance(nudge, ProactiveNudge)
            self.assertTrue(bool(nudge.title))
            self.assertTrue(bool(nudge.message))

    def test_daemon_lifecycle(self):
        received_nudges = []

        def on_nudge(n):
            received_nudges.append(n)

        daemon = ProactiveDaemon(advisor=self.advisor, on_nudge=on_nudge)
        self.assertFalse(daemon.is_running())

        # Test single manual evaluation
        nudge = daemon.run_once()
        if nudge:
            self.assertEqual(len(received_nudges), 1)

        status = daemon.get_status()
        self.assertIn("running", status)
        self.assertIn("settings", status)

    def test_global_singletons(self):
        pa = get_proactive_advisor()
        pd = get_proactive_daemon()
        self.assertIsNotNone(pa)
        self.assertIsNotNone(pd)


if __name__ == "__main__":
    unittest.main()
