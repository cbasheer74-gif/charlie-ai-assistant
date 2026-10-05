"""tests/test_nextgen_capabilities.py — Comprehensive Verification of Next-Gen Charlie Features:

1. Screen Vision Co-pilot (Passive screen analyzer & error context)
2. GUI Computer-Use (Autonomous desktop clicker & safety bounds)
3. User Memory Graph (Lifelong relational knowledge graph)
4. Mobile Companion Bridge (Remote phone companion & web bridge)
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
import urllib.request
from pathlib import Path

from engine.automation.gui_agent import GUIDesktopAutomator, get_gui_automator
from engine.bridge.mobile_companion import MobileCompanionBridge, get_mobile_bridge
from engine.memory.knowledge_graph import GraphEdge, GraphNode, UserMemoryGraph, get_memory_graph
from engine.vision.screen_copilot import ScreenInsight, ScreenVisionCopilot, get_screen_copilot


class TestNextGenCapabilities(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="charlie_nextgen_test_"))
        self.db_path = self.test_dir / "test_memory.db"

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # ── 1. Screen Vision Co-pilot ────────────────────────────────────────────

    def test_screen_copilot_window_and_error_patterns(self):
        copilot = ScreenVisionCopilot()

        # Active window title lookup
        title = copilot.get_active_window_title()
        self.assertIsInstance(title, str)

        # Error patterns regex validation
        test_traceback = "Traceback (most recent call last):\n  File 'test.py', line 10\nValueError: Invalid number"
        matches = [pat.search(test_traceback) for pat in ScreenVisionCopilot.ERROR_PATTERNS if pat.search(test_traceback)]
        self.assertTrue(len(matches) > 0)

        # Live context generation
        ctx = copilot.get_live_context_for_prompt()
        self.assertIn("Current Screen Context", ctx)

    # ── 2. GUI Computer-Use Automator ────────────────────────────────────────

    def test_gui_automator_screen_metrics_and_failsafe(self):
        agent = GUIDesktopAutomator(failsafe_enabled=False)

        w, h = agent.get_screen_size()
        self.assertGreater(w, 0)
        self.assertGreater(h, 0)

        # Destructive command safety block
        blocked = agent.type_text("format c: /fs:ntfs")
        self.assertFalse(blocked)
        audit = agent.get_action_audit_log()
        self.assertTrue(any("Security Block" in str(rec.get("error", "")) for rec in audit))

        # Emergency kill switch
        agent.emergency_stop()
        with self.assertRaises(RuntimeError):
            agent.move_mouse(100, 100)

    # ── 3. Lifelong User Memory Graph ────────────────────────────────────────

    def test_memory_graph_node_and_edge_extraction(self):
        graph = UserMemoryGraph(db_path=self.db_path)

        # Node upsert
        node = GraphNode(id="pref:dark_mode", name="Dark Mode", category="preference")
        graph.upsert_node(node)

        # Edge upsert
        edge = GraphEdge(source_id="user:root", target_id="pref:dark_mode", relation="PREFERS", weight=2.0)
        graph.upsert_edge(edge)

        # Relational NLP extraction
        extracted = graph.extract_and_integrate("I prefer Python and my project is Charlie")
        self.assertTrue(len(extracted) >= 1)

        # Retrieve facts and prompt synthesis
        facts = graph.get_user_facts()
        self.assertTrue(len(facts) >= 1)

        prompt_block = graph.format_profile_for_prompt()
        self.assertIn("User", prompt_block)

    # ── 4. Mobile Companion Bridge ───────────────────────────────────────────

    def test_mobile_companion_bridge_lifecycle(self):
        bridge = MobileCompanionBridge(port=9876)
        started = bridge.start()
        self.assertTrue(started)

        # Test local HTTP ping
        try:
            req = urllib.request.Request("http://127.0.0.1:9876/api/status")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(data.get("charlie_status"), "ONLINE")
        finally:
            bridge.stop()


if __name__ == "__main__":
    unittest.main()
