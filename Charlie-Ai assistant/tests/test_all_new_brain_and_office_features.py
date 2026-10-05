# tests/test_all_new_brain_and_office_features.py
"""
Comprehensive Integration Test Suite for Charlie New Brain & Office Enhancements.

Validates all 16 new action, voice, intelligence, and routing modules:
  1. email_dictation
  2. meeting_notes
  3. clipboard_manager
  4. focus_timer
  5. writing_polish
  6. page_summarizer
  7. routine_briefing
  8. file_organizer
  9. workflow_runner
  10. emotion_detector
  11. noise_classifier
  12. episodic_memory
  13. proactive_advisor
  14. offline_knowledge
  15. intent_disambiguator
  16. command_engine (end-to-end voice routing)
"""

import os
import sys
import unittest
import numpy as np

# Ensure parent is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestBrainAndOfficeIntegration(unittest.TestCase):

    def test_01_email_dictation(self):
        import actions.email_dictation as ed
        self.assertEqual(ed.TOOL["name"], "email_dictation")
        res = ed.execute(action="draft", to="test@example.com", subject="Test Subject", body_hint="Quick status update")
        self.assertIn("Draft", res)

    def test_02_meeting_notes(self):
        import actions.meeting_notes as mn
        self.assertEqual(mn.TOOL["name"], "meeting_notes")
        start_res = mn.execute(action="start", title="Weekly Sync")
        self.assertIn("Weekly Sync", start_res)
        stop_res = mn.execute(action="stop")
        self.assertTrue(len(stop_res) > 0)

    def test_03_clipboard_manager(self):
        import actions.clipboard_manager as cm
        self.assertEqual(cm.TOOL["name"], "clipboard_manager")
        copy_res = cm.execute(action="copy", text="Charlie test clipboard content")
        self.assertIn("Copied", copy_res)
        show_res = cm.execute(action="show", count=3)
        self.assertTrue(len(show_res) > 0)

    def test_04_focus_timer(self):
        import actions.focus_timer as ft
        self.assertEqual(ft.TOOL["name"], "focus_timer")
        res = ft.execute(action="start", duration_minutes=25)
        self.assertTrue("Focus" in res or "Pomodoro" in res or "started" in res)
        stop_res = ft.execute(action="stop")
        self.assertIn("stopped", stop_res.lower())

    def test_05_writing_polish(self):
        import actions.writing_polish as wp
        self.assertEqual(wp.TOOL["name"], "writing_polish")
        res = wp.execute(action="polish", text="hey bro can u send that report asap thx", tone="executive")
        self.assertIn("Preview", res)

    def test_06_page_summarizer(self):
        import actions.page_summarizer as ps
        self.assertEqual(ps.TOOL["name"], "page_summarizer")
        sample_doc = "Artificial intelligence is rapidly advancing across various sectors. Assistants improve developer productivity. Voice interaction provides seamless accessibility."
        res = ps.execute(action="summarize", text=sample_doc)
        self.assertIn("Key Takeaways", res)

    def test_07_routine_briefing(self):
        import actions.routine_briefing as rb
        self.assertEqual(rb.TOOL["name"], "routine_briefing")
        res = rb.execute(action="morning")
        self.assertIn("Briefing", res)
        goal_res = rb.execute(action="set_goal", goal_text="Deploy release v1.0")
        self.assertIn("Focus goal recorded", goal_res)

    def test_08_file_organizer(self):
        import actions.file_organizer as fo
        self.assertEqual(fo.TOOL["name"], "file_organizer")
        res = fo.execute(action="preview", target="desktop")
        self.assertTrue(len(res) > 0)

    def test_09_workflow_runner(self):
        import actions.workflow_runner as wr
        self.assertEqual(wr.TOOL["name"], "workflow_runner")
        list_res = wr.execute(preset="list")
        self.assertIn("Available Multi-App Workflows", list_res)

    def test_10_emotion_detector(self):
        from engine.voice.emotion_detector import get_emotion_detector
        ed = get_emotion_detector()
        # Feed synthetic audio chunk
        sample_chunk = (np.sin(2 * np.pi * 200 * np.linspace(0, 1, 1024)) * 5000).astype(np.int16)
        ed.feed(sample_chunk)
        state = ed.get_state()
        self.assertIn("emotion", state)
        self.assertIn("guidance", state)

    def test_11_noise_classifier(self):
        from engine.voice.noise_classifier import NoiseClassifier
        nc = NoiseClassifier()
        quiet_chunk = np.zeros(1024, dtype=np.int16)
        nc.feed(quiet_chunk)
        self.assertEqual(nc.get_last_class(), NoiseClassifier.QUIET)

    def test_12_episodic_memory(self):
        from engine.intelligence.episodic_memory import get_episodic_memory
        em = get_episodic_memory()
        ep = em.record_episode(
            summary="Tested Charlie audio pipeline and voice routing",
            tags=["audio", "test_suite"],
            importance=7,
        )
        self.assertTrue(ep.id.startswith("ep_"))
        hits = em.recall("audio pipeline")
        self.assertTrue(len(hits) > 0)

    def test_13_proactive_advisor(self):
        from engine.intelligence.proactive_advisor import get_proactive_advisor
        pa = get_proactive_advisor()
        nudge = pa.evaluate_all()
        # Nudge can be None or ProactiveNudge depending on time and conditions
        self.assertTrue(nudge is None or hasattr(nudge, "title"))

    def test_14_offline_knowledge(self):
        from engine.intelligence.offline_knowledge import get_offline_knowledge
        ok = get_offline_knowledge()
        results = ok.query("undo git commit")
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]["key"], "git_undo_commit")

    def test_15_intent_disambiguator(self):
        from engine.intelligence.intent_disambiguator import get_intent_disambiguator
        ida = get_intent_disambiguator()
        res = ida.disambiguate("clean up")
        self.assertTrue(res.is_ambiguous)
        self.assertEqual(res.resolved_tool, "file_organizer")

    def test_16_command_engine_routing(self):
        from engine.voice.command_engine import VoiceCommandEngine
        ce = VoiceCommandEngine()

        # 1. Cultural greeting
        res_greet = ce.route_command("as-salamu alaykum wa rahmatullahi wa barakatuh", session_id="test_sess")
        self.assertEqual(res_greet["status"], "CULTURAL_GREETING")
        self.assertIn("Wa alaykum as-salam", res_greet["speech_response"])

        # 2. Morning Briefing
        res_morning = ce.route_command("good morning Charlie", session_id="test_sess")
        self.assertEqual(res_morning["status"], "ROUTINE_BRIEFING")

        # 3. Focus Timer
        res_focus = ce.route_command("start focus mode", session_id="test_sess")
        self.assertEqual(res_focus["status"], "FOCUS_TIMER")

        # 4. Disambiguated Polish
        res_polish = ce.route_command("polish this", session_id="test_sess")
        self.assertIn(res_polish["status"], ("WRITING_POLISHED", "EXECUTED_DISAMBIGUATED_TOOL"))

        # 5. Media Control
        res_media = ce.route_command("play music", session_id="test_sess")
        self.assertEqual(res_media["status"], "MEDIA_CONTROL")

        # 6. Quick Calculator
        res_calc = ce.route_command("calculate 15% of 850", session_id="test_sess")
        self.assertEqual(res_calc["status"], "QUICK_CALC")
        self.assertIn("127.5", res_calc["speech_response"])

        # 7. Voice Speed
        res_speed = ce.route_command("speak faster", session_id="test_sess")
        self.assertEqual(res_speed["status"], "VOICE_SPEED")

    def test_17_media_control(self):
        import actions.media_control as mc
        self.assertEqual(mc.TOOL["name"], "media_control")
        res = mc.execute(action="play_pause")
        self.assertTrue(len(res) > 0)

    def test_18_quick_calc(self):
        import actions.quick_calc as qc
        self.assertEqual(qc.TOOL["name"], "quick_calc")
        res_pct = qc.execute("15% of 850")
        self.assertIn("127.5", res_pct)
        res_fx = qc.execute("100 USD to INR")
        self.assertIn("INR", res_fx)
        res_math = qc.execute("144 / 12")
        self.assertIn("12", res_math)

    def test_19_screen_explainer(self):
        from unittest.mock import patch
        import actions.screen_explainer as se
        self.assertEqual(se.TOOL["name"], "screen_explainer")
        mock_ocr = {"status": "success", "text": "Visual screen captured. Active desktop displayed with code editor.", "width": 1920, "height": 1080}
        with patch("engine.vision_ocr.extract_screen_text", return_value=mock_ocr):
            res = se.execute(mode="explain")
            self.assertTrue(len(res) > 0)

    def test_20_voice_speed(self):
        import actions.voice_speed as vs
        self.assertEqual(vs.TOOL["name"], "voice_speed")
        res_faster = vs.execute(action="faster")
        self.assertIn("Voice speed", res_faster)
        res_reset = vs.execute(action="reset")
        self.assertIn("normal", res_reset)


if __name__ == "__main__":
    unittest.main()

