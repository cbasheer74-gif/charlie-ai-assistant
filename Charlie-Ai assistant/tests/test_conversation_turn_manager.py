"""Unit and regression tests for Phase 3 Step 10: ConversationTurnManager Referent Resolution.

Validates:
A. Direct referent resolution: "Open Chrome" -> "close it" -> target = Chrome
B. Container referent resolution: "open Downloads" -> "open Charlie folder in it" -> parent = Downloads
C. Self-correction target override: "Open Chrome... no Edge" -> target = Edge
D. Self-correction action cancellation: "Delete this file... no rename it" -> action = rename, not delete
E. Ambiguity preservation: "Open Chrome and Edge" -> "close it" -> original text preserved, no invented target
F. Hinglish pronouns & syntax:
   - "Chrome kholo" -> "isko band karo" -> "Chrome band karo"
   - "ye file delete nahi, rename karo" -> "ye file rename karo"
   - "Downloads folder kholo" -> "isme Charlie wala folder" -> "Downloads mein Charlie wala folder"
G. Session isolation: manager.reset_session() / new_chat() clears old referents
H. Normal conversational prompts untouched (e.g. "There is no problem", "Explain physics")
I. ProChatAssistant text-chat integration
J. Security confirmation gate isolation (destructive action protection intact)
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure paths
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.voice.conversation import ConversationTurnManager
from engine.voice.models import Transcript
from engine.pro_chat import ProChatAssistant
from core.confirm import confirm_gate


class TestConversationTurnManager(unittest.TestCase):
    """Test suite for ConversationTurnManager referent resolution & self-correction."""

    def setUp(self):
        self.mgr = ConversationTurnManager()

    # --------------------------------------------------------------------------
    # A. Test A: Direct object referent
    # --------------------------------------------------------------------------
    def test_a_direct_referent_resolution(self):
        """User: 'Open Chrome' -> User: 'close it' -> Expected referent = Chrome."""
        self.mgr.record_turn_text("Open Chrome")
        self.assertEqual(self.mgr.last_target, "Chrome")

        resolved = self.mgr.resolve_referents("close it")
        self.assertEqual(resolved, "close Chrome")

    # --------------------------------------------------------------------------
    # B. Test B: Container referent
    # --------------------------------------------------------------------------
    def test_b_container_referent_resolution(self):
        """User: 'open Downloads' -> User: 'open Charlie folder in it' -> Expected parent = Downloads."""
        self.mgr.record_turn_text("open Downloads")
        self.assertEqual(self.mgr.last_container, "Downloads")

        resolved = self.mgr.resolve_referents("open Charlie folder in it")
        self.assertEqual(resolved, "open Charlie folder in Downloads")

    # --------------------------------------------------------------------------
    # C. Test C: Self-correction target override
    # --------------------------------------------------------------------------
    def test_c_self_correction_target_override(self):
        """User: 'Open Chrome... no Edge' -> Expected final target = Edge."""
        corrected = self.mgr.resolve_in_flight_correction("Open Chrome... no Edge")
        self.assertEqual(corrected, "Open Edge")

        # Also test with pause punctuation and Hindi marker
        corrected_hi = self.mgr.resolve_in_flight_correction("Chrome kholo... nahi Edge kholo")
        self.assertEqual(corrected_hi, "Edge kholo")

    # --------------------------------------------------------------------------
    # D. Test D: Self-correction action cancellation
    # --------------------------------------------------------------------------
    def test_d_self_correction_action_cancellation(self):
        """User: 'Delete this file... no rename it' -> Expected action = rename, not delete."""
        corrected = self.mgr.resolve_in_flight_correction("Delete this file... no rename it")
        self.assertNotIn("Delete", corrected)
        self.assertIn("rename", corrected.lower())

        # Also test with "actually"
        corrected_act = self.mgr.resolve_in_flight_correction("Delete this file... actually rename it")
        self.assertNotIn("Delete", corrected_act)
        self.assertIn("rename", corrected_act.lower())

    # --------------------------------------------------------------------------
    # E. Test E: Ambiguous referents
    # --------------------------------------------------------------------------
    def test_e_ambiguous_referents_preserve_original(self):
        """User mentions Chrome and Edge -> 'close it' -> do NOT invent target."""
        self.mgr.record_turn_text("Open Chrome and Edge")
        self.assertEqual(len(self.mgr.recent_entities), 2)
        self.assertIsNone(self.mgr.last_target)

        # Confidence is low -> must NOT rewrite user intent
        resolved = self.mgr.resolve_referents("close it")
        self.assertEqual(resolved, "close it")

    # --------------------------------------------------------------------------
    # F. Test F: Hindi / Hinglish referents and syntax
    # --------------------------------------------------------------------------
    def test_f_hinglish_referents(self):
        """Test Hinglish pronouns: isko, isme, ye file delete nahi rename karo."""
        # 1. "Chrome kholo" -> "isko band karo"
        self.mgr.record_turn_text("Chrome kholo")
        self.assertEqual(self.mgr.last_target, "Chrome")
        resolved_isko = self.mgr.resolve_referents("isko band karo")
        self.assertEqual(resolved_isko, "Chrome band karo")

        # 2. Hinglish action cancellation: "ye file delete nahi, rename karo"
        corrected_action = self.mgr.resolve_in_flight_correction("ye file delete nahi, rename karo")
        self.assertEqual(corrected_action, "ye file rename karo")
        self.assertNotIn("delete", corrected_action.lower())

        # 3. Hinglish container: "Downloads folder kholo" -> "isme Charlie wala folder"
        self.mgr.record_turn_text("Downloads folder kholo")
        self.assertEqual(self.mgr.last_container, "Downloads")
        resolved_isme = self.mgr.resolve_referents("isme Charlie wala folder")
        self.assertEqual(resolved_isme, "Downloads mein Charlie wala folder")

    # --------------------------------------------------------------------------
    # G. Test G: Session isolation & reset
    # --------------------------------------------------------------------------
    def test_g_session_isolation(self):
        """Old referents should not leak unexpectedly after reset_session."""
        self.mgr.record_turn_text("Open Chrome")
        self.assertEqual(self.mgr.last_target, "Chrome")

        self.mgr.reset_session()
        self.assertIsNone(self.mgr.last_target)
        self.assertEqual(len(self.mgr.recent_entities), 0)

        # After reset, "close it" remains un-resolved because context was cleared
        resolved = self.mgr.resolve_referents("close it")
        self.assertEqual(resolved, "close it")

    # --------------------------------------------------------------------------
    # H. Test H: Normal prompts remain unchanged
    # --------------------------------------------------------------------------
    def test_h_normal_prompts_unchanged(self):
        """Regular prompts, questions, and sentences containing 'no' should not be mutated."""
        self.assertEqual(
            self.mgr.resolve_referents("There is no problem with this script."),
            "There is no problem with this script.",
        )
        self.assertEqual(
            self.mgr.resolve_referents("Explain quantum entanglement in simple terms."),
            "Explain quantum entanglement in simple terms.",
        )
        self.assertEqual(
            self.mgr.resolve_referents("I have no doubt about the results."),
            "I have no doubt about the results.",
        )

    # --------------------------------------------------------------------------
    # I. Test I: ProChatAssistant text-chat integration
    # --------------------------------------------------------------------------
    def test_i_pro_chat_assistant_integration(self):
        """Test multi-turn referent tracking in ProChatAssistant."""
        received_prompts = []

        def mock_generate(system, messages):
            user_msg = messages[-1]["content"]
            received_prompts.append(user_msg)
            return f"Processed: {user_msg}"

        assistant = ProChatAssistant(generate=mock_generate)

        # Turn 1: "Open Chrome"
        assistant.respond("Open Chrome")
        self.assertIn("Open Chrome", received_prompts[0])

        # Turn 2: "close it" -> should be resolved to "close Chrome"
        assistant.respond("close it")
        self.assertIn("close Chrome", received_prompts[1])

        # New chat resets session
        assistant.new_chat()
        assistant.respond("close it")
        # Turn 3 after reset: referent was cleared, stays "close it"
        self.assertIn("close it", received_prompts[2])

    # --------------------------------------------------------------------------
    # J. Test J: Security regression (confirm_gate stays active)
    # --------------------------------------------------------------------------
    def test_j_security_confirmation_gate_isolation(self):
        """Destructive action confirmations remain intact and cannot be bypassed."""
        # Check confirm_gate is functioning normally
        self.assertFalse(confirm_gate.is_pending())

        action_called = False
        def risky_delete():
            nonlocal action_called
            action_called = True
            return "File deleted"

        token = confirm_gate.request(
            title="Delete File",
            detail="Permanently delete project folder",
            spoken="Confirm deletion?",
            run=risky_delete,
        )
        self.assertTrue(confirm_gate.is_pending())
        self.assertFalse(action_called)

        # Cancel confirmation
        confirm_gate.cancel()
        self.assertFalse(confirm_gate.is_pending())
        self.assertFalse(action_called)


if __name__ == "__main__":
    unittest.main()
