"""tests/test_features_1234.py — Test Suite for Features 1, 2, 3, and 4.

Validates:
1. Token Add-On Packs (Credit Packs purchase, pricing authority, and /me/credits API).
2. Mobile Device Pairing (ephemeral pairing start, code generation, and verification).
3. Mini HUD Floating Overlay (widget attributes, state propagation, and mic toggle).
4. Filmora Preflight Detector (Filmora 14 detection, automated FFmpeg graceful fallback, and action).
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from actions.video_studio import video_studio
from engine.agents.video_agent import VideoAgent
from engine.error_recovery import ErrorRecoveryEngine
from engine.memory_manager import MemoryManager
from engine.permissions import PermissionManager
from engine.rollback import RollbackManager
from engine.task_planner import TaskPlanner
from engine.verification import VerificationEngine
from licensing_server.routes.me import CompletePairRequest, _ephemeral_pairings, start_companion_pairing
from licensing_server.services.payment_service import CREDIT_PACK_AMOUNTS, PLAN_PRICES, PaymentService


class TestFeatures1234(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_feature_1_token_addon_packs(self):
        """Feature 1: AI Credit pack pricing authority and catalog."""
        self.assertIn("STARTER_PACK", CREDIT_PACK_AMOUNTS)
        self.assertIn("POWER_PACK", CREDIT_PACK_AMOUNTS)
        self.assertIn("PRO_PACK", CREDIT_PACK_AMOUNTS)

        self.assertEqual(CREDIT_PACK_AMOUNTS["STARTER_PACK"], 500)
        self.assertEqual(CREDIT_PACK_AMOUNTS["POWER_PACK"], 1200)
        self.assertEqual(CREDIT_PACK_AMOUNTS["PRO_PACK"], 3000)

        # Server-side pricing
        self.assertEqual(PLAN_PRICES["STARTER_PACK"], 9900)    # ₹99
        self.assertEqual(PLAN_PRICES["POWER_PACK"], 19900)    # ₹199
        self.assertEqual(PLAN_PRICES["PRO_PACK"], 39900)      # ₹399

        ps = PaymentService()
        catalog = ps.get_plan_registry()
        self.assertIn("credit_packs", catalog)
        self.assertEqual(len(catalog["credit_packs"]), 3)

    def test_feature_2_device_pairing(self):
        """Feature 2: Ephemeral 6-digit companion pairing protocol."""
        mock_user = MagicMock()
        mock_user.id = "user_test_42"

        res = start_companion_pairing(user=mock_user)
        self.assertEqual(res["status"], "ok")
        self.assertTrue(len(res["pairing_code"]) == 6)
        self.assertTrue(res["pairing_code"].isdigit())
        self.assertIn(res["pairing_code"], _ephemeral_pairings)
        self.assertEqual(_ephemeral_pairings[res["pairing_code"]]["user_id"], "user_test_42")

        # CompletePairRequest model validation
        req = CompletePairRequest(
            pairing_code=res["pairing_code"],
            client_device_id="hw_mobile_12345",
            client_device_name="Pixel 9 Pro",
            client_device_type="MOBILE_ANDROID",
        )
        self.assertEqual(req.client_device_name, "Pixel 9 Pro")

    def test_feature_3_mini_hud_overlay(self):
        """Feature 3: Mini HUD widget attributes and state propagation."""
        from ui import MiniHudWidget
        mock_win = MagicMock()
        mock_win._assistant_name = "CHARLIE"

        # QWidget headless initialization
        widget = MiniHudWidget(mock_win)
        self.assertEqual(widget.width(), 310)
        self.assertEqual(widget.height(), 48)

        # Verify state updates
        widget.set_state("LISTENING", "Listening...", "#22c55e", "rgba(0,0,0,0)", "#22c55e")
        self.assertIn("Listening", widget._label.text())

        widget.set_audio_level(0.5)
        self.assertEqual(widget._pulse_dot.text(), "◉")

        widget.set_muted(True)
        self.assertTrue(widget._is_muted)

    def test_feature_4_filmora_preflight_detector(self):
        """Feature 4: Filmora 14 detector and graceful FFmpeg fallback."""
        mem = MemoryManager()
        plan = TaskPlanner(mem)
        perm = PermissionManager()
        ver = VerificationEngine()
        rec = ErrorRecoveryEngine(mem)
        roll = RollbackManager()
        agent = VideoAgent(mem, plan, perm, ver, rec, roll)

        filmora_info = agent.detect_filmora()
        self.assertIn("installed", filmora_info)
        self.assertIn("executable", filmora_info)
        self.assertIn("version", filmora_info)

        preflight = agent.check_video_prerequisites()
        self.assertIn("active_engine", preflight)
        self.assertIn("fallback_ready", preflight)
        self.assertIn("filmora", preflight)
        self.assertIn("ffmpeg", preflight)

        # Test video_studio action="preflight"
        output = video_studio({"action": "preflight"})
        self.assertIn("Video Production Preflight Diagnostics", output)
        self.assertIn("Wondershare Filmora 14", output)
        self.assertIn("Local FFmpeg", output)
        self.assertIn("Automated Graceful Fallback", output)


if __name__ == "__main__":
    unittest.main()
