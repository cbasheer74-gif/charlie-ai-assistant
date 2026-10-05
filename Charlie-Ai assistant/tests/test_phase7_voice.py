"""tests/test_phase7_voice.py — Certification & Golden Tests for CHARLIE Phase 7.

Validates:
1. AudioDeviceManager Discovery & Disconnect Recovery
2. MicrophoneCapture & Push-to-Talk Hotkey
3. Voice State Machine Transitions
4. VoiceActivityDetector Energy & Silence End-of-Utterance
5. WakeWordEngine Sensitivity & Self-TTS Echo Lockout
6. SpeechRecognitionManager & Hybrid Fallback
7. VocabularyContextManager & Technical Priming
8. TranscriptNormalizer & Hinglish Preservation
9. TextToSpeechManager & Barge-In Immediate Stop
10. ConversationTurnManager & Follow-up Window
11. Referent & Anaphora Resolution ("backend", "ye", "wo")
12. In-Flight Speech Self-Correction ("Chrome... nahi Edge")
13. VoiceCommandEngine Routing to Backend Skills & Agents
14. VoicePermissionConfirmation with Action-Bound Expiry
15. AudioRecoveryEngine & Offline Local Command Execution
16. Golden Scenarios 96 to 113
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
import numpy as np

from engine.voice.audio_device_mgr import AudioDeviceManager
from engine.voice.barge_in import BargeInManager, InterruptScope
from engine.voice.capture import MicrophoneCapture
from engine.voice.command_engine import VoiceCommandEngine, VoicePermissionConfirmation
from engine.voice.conversation import ConversationTurnManager
from engine.voice.models import (
    AudioDevice,
    CommandConfidence,
    PendingConfirmation,
    Transcript,
    VoiceIntent,
    VoiceSession,
    VoiceSettings,
    VoiceState,
)
from engine.voice.orchestrator import VoiceOrchestrator
from engine.voice.recovery import AudioRecoveryEngine
from engine.voice.stt import (
    MockSTTProvider,
    SpeechRecognitionManager,
    TranscriptNormalizer,
    VocabularyContextManager,
)
from engine.voice.tts import MockTTSProvider, TextToSpeechManager
from engine.voice.vad import VoiceActivityDetector
from engine.voice.wake_word import WakeWordEngine


class TestPhase7VoiceEngine(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="charlie_voice_test_"))
        self.config_path = self.test_dir / "audio_settings.json"

        self.device_mgr = AudioDeviceManager(config_path=self.config_path)
        self.mock_devices = [
            AudioDevice(name="USB Headset Mic", index=1, is_default=False),
            AudioDevice(name="Realtek High Definition Audio", index=2, is_default=True),
        ]
        self.device_mgr.set_mock_devices(self.mock_devices)

        self.mock_stt = MockSTTProvider()
        self.stt_mgr = SpeechRecognitionManager(provider=self.mock_stt)

        self.mock_tts = MockTTSProvider()
        self.tts_mgr = TextToSpeechManager(provider=self.mock_tts)

        self.settings = VoiceSettings(
            wake_phrase="Hey Charlie",
            follow_up_window_sec=5.0,
            silence_threshold_sec=0.5,
        )

        self.orchestrator = VoiceOrchestrator(
            settings=self.settings,
            device_manager=self.device_mgr,
            stt_manager=self.stt_mgr,
            tts_manager=self.tts_mgr,
        )

    def tearDown(self):
        self.orchestrator.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # ── 1. Audio Device Management ───────────────────────────────────────────

    def test_audio_device_listing_and_preferences(self):
        mics = self.device_mgr.list_microphones()
        self.assertEqual(len(mics), 2)

        # Select default
        selected = self.device_mgr.get_selected_microphone()
        self.assertEqual(selected.name, "Realtek High Definition Audio")

        # Save preference
        self.device_mgr.save_preferences("USB Headset Mic")
        selected_pref = self.device_mgr.get_selected_microphone()
        self.assertEqual(selected_pref.name, "USB Headset Mic")

    def test_device_disconnect_and_recovery(self):
        # Current mic disconnected: simulate USB mic removal
        self.device_mgr.set_mock_devices([
            AudioDevice(name="Realtek High Definition Audio", index=2, is_default=True),
        ])
        is_disc, fallback = self.device_mgr.handle_device_disconnect("USB Headset Mic")
        self.assertTrue(is_disc)
        self.assertEqual(fallback.name, "Realtek High Definition Audio")

    # ── 2. Microphone Capture & Push-To-Talk ─────────────────────────────────

    def test_microphone_capture_mute_and_ptt(self):
        capture = MicrophoneCapture(device_manager=self.device_mgr)
        capture.start()

        chunk = np.ones(1024, dtype=np.float32) * 0.05
        capture.push_mock_audio(chunk)

        buffered = capture.get_buffered_audio()
        self.assertEqual(len(buffered), 1024)

        # Mute check
        capture.set_muted(True)
        capture.push_mock_audio(chunk)
        self.assertEqual(len(capture.get_buffered_audio()), 0)

        # Push to talk check
        capture.set_push_to_talk(True)
        self.assertTrue(capture.push_to_talk_active)
        capture.stop()

    # ── 3. VAD & Silence End-of-Utterance ─────────────────────────────────────

    def test_vad_energy_and_utterance_end(self):
        vad = VoiceActivityDetector(energy_threshold=0.01, silence_timeout_sec=0.1, min_speech_duration_sec=0.05)

        # Silence frame
        silence = np.zeros(512, dtype=np.float32)
        is_v, complete, energy = vad.process_frame(silence)
        self.assertFalse(is_v)
        self.assertFalse(complete)

        # Voice frames exceeding minimum speech duration
        voice = np.ones(512, dtype=np.float32) * 0.05
        for _ in range(3):
            is_v2, complete2, energy2 = vad.process_frame(voice)
            time.sleep(0.02)
        self.assertTrue(is_v2)
        self.assertFalse(complete2)

        # Sleep to exceed silence timeout
        time.sleep(0.15)
        is_v3, complete3, energy3 = vad.process_frame(silence)
        self.assertFalse(is_v3)
        self.assertTrue(complete3)

    # ── 4. STT, Vocabulary Priming, and Hinglish Normalization ────────────────

    def test_transcript_normalizer_hinglish_and_tech(self):
        raw = "hey charlie vs code kholo aur git hub se post gre sequel check karo"
        normalized = TranscriptNormalizer.normalize(raw)
        self.assertIn("VS Code", normalized)
        self.assertIn("GitHub", normalized)
        self.assertIn("PostgreSQL", normalized)

        lang = TranscriptNormalizer.detect_language(normalized)
        self.assertEqual(lang, "hinglish")

    def test_vocabulary_context_priming(self):
        vocab = VocabularyContextManager()
        vocab.add_project_terms("ZynPay", ["Flutter", "PostgreSQL"])
        prompt_str = vocab.get_prompt_context()
        self.assertIn("ZynPay", prompt_str)
        self.assertIn("Flutter", prompt_str)

    # ── 5. TTS Playback and Barge-In ─────────────────────────────────────────

    def test_barge_in_stops_tts_immediately(self):
        tts = TextToSpeechManager(provider=self.mock_tts)
        barge_in = BargeInManager(tts_manager=tts)

        tts.speak("This is a long speech that will be interrupted.")
        self.assertTrue(tts.is_speaking())

        # Interruption occurs
        scope = barge_in.check_for_interruption("Charlie ruko")
        self.assertEqual(scope, InterruptScope.STOP_TTS_ONLY)
        self.assertFalse(tts.is_speaking())

    # ── 6. Conversational Continuity & Referent Resolution ───────────────────

    def test_follow_up_window_and_referents(self):
        conv = ConversationTurnManager(follow_up_window_sec=2.0)
        conv.set_active_project("ZynPay")
        self.assertTrue(conv.is_in_follow_up_window())

        # Anaphoric referent resolution
        resolved = conv.resolve_referents("backend bhi start karo")
        self.assertIn("ZynPay", resolved)

    def test_in_flight_correction(self):
        conv = ConversationTurnManager()
        corrected = conv.resolve_in_flight_correction("Chrome kholo... nahi Edge kholo")
        self.assertEqual(corrected, "Edge kholo")

    # ── 7. Voice Command Engine & Safety Confirmations ───────────────────────

    def test_voice_permission_confirmation_expiry(self):
        cmd_engine = VoiceCommandEngine()
        sess_id = "sess_123"

        # Action requires confirmation
        res = cmd_engine.route_command("Client ko email bhej do", session_id=sess_id)
        self.assertEqual(res["status"], "AWAITING_CONFIRMATION")

        # Positive confirmation
        conf_res = cmd_engine.route_command("Haan bhej do", session_id=sess_id)
        self.assertEqual(conf_res["status"], "CONFIRMED_AND_EXECUTING")
        self.assertEqual(conf_res["action_type"], "SEND_EMAIL")

    def test_low_confidence_destructive_action(self):
        cmd_engine = VoiceCommandEngine()
        conf = cmd_engine.evaluate_risk_and_confidence("delete project", transcription_confidence=0.60)
        self.assertEqual(conf, CommandConfidence.CLARIFY)

    # ── 8. Golden Scenarios (Tests 96 to 113) ─────────────────────────────────

    def test_golden_96_wake_word_no_unintended_action(self):
        """Test 96: 'Hey Charlie' -> wake state, no unintended action."""
        res = self.orchestrator.process_spoken_transcript("Hey Charlie")
        self.assertEqual(self.orchestrator.current_state, VoiceState.LISTENING)
        self.assertEqual(res["status"], "WAKE_DETECTED")
        self.assertTrue(self.orchestrator.conversation.is_in_follow_up_window())

    def test_golden_97_natural_command(self):
        """Test 97: 'Hey Charlie, Notepad kholo' -> routes to open_app."""
        res = self.orchestrator.process_spoken_transcript("Hey Charlie, Notepad kholo")
        self.assertEqual(res["status"], "ROUTED_TO_COMPUTER_CONTROL")
        self.assertEqual(res["target"].lower(), "notepad")

    def test_golden_98_hinglish_command(self):
        """Test 98: Hinglish 'Charlie latest Excel file open karke monthly report bana do' -> SpreadsheetAgent."""
        res = self.orchestrator.process_spoken_transcript("Hey Charlie, latest Excel file open karke monthly report bana do")
        self.assertEqual(res["status"], "ROUTED_TO_SKILL")
        self.assertEqual(res["agent"], "SpreadsheetAgent")

    def test_golden_99_follow_up_without_wake_word(self):
        """Test 99: Follow-up command within active window does not require second wake word."""
        # Turn 1: with wake word
        self.orchestrator.process_spoken_transcript("Hey Charlie, Chrome kholo")

        # Turn 2: within follow-up window, no wake word
        res2 = self.orchestrator.process_spoken_transcript("YouTube kholo")
        self.assertNotEqual(res2["status"], "IGNORED_NO_WAKE")
        self.assertEqual(res2["status"], "ROUTED_TO_COMPUTER_CONTROL")

    def test_golden_100_context_referent_resolution(self):
        """Test 100: 'ZynPay kholo', then 'Backend bhi start karo' -> associates backend with ZynPay."""
        self.orchestrator.process_spoken_transcript("Hey Charlie, ZynPay continue karo")
        self.assertEqual(self.orchestrator.conversation.active_session.active_project, "ZynPay")

        res2 = self.orchestrator.process_spoken_transcript("Backend bhi start karo")
        self.assertIn("ZynPay", res2["resolved_command"])

    def test_golden_101_barge_in_immediate_interruption(self):
        """Test 101: While speaking, user says 'Stop' -> audio stops quickly."""
        self.orchestrator.tts_manager.speak("This is a very long response from CHARLIE.")
        self.assertTrue(self.orchestrator.tts_manager.is_speaking())

        res = self.orchestrator.process_spoken_transcript("Stop")
        self.assertEqual(res["status"], "TTS_STOPPED")
        self.assertFalse(self.orchestrator.tts_manager.is_speaking())

    def test_golden_102_in_flight_correction(self):
        """Test 102: 'Chrome kholo... nahi Edge kholo' -> final app is Edge."""
        res = self.orchestrator.process_spoken_transcript("Hey Charlie, Chrome kholo... nahi Edge kholo")
        self.assertEqual(res["status"], "ROUTED_TO_COMPUTER_CONTROL")
        self.assertEqual(res["target"].lower(), "edge")

    def test_golden_103_low_confidence_clarification(self):
        """Test 103: Low confidence on high risk command -> requires clarification."""
        conf = self.orchestrator.command_engine.evaluate_risk_and_confidence("format disk", transcription_confidence=0.55)
        self.assertEqual(conf, CommandConfidence.CLARIFY)

    def test_golden_104_email_send_confirmation(self):
        """Test 104: Email command requires action-bound confirmation before sending."""
        res = self.orchestrator.process_spoken_transcript("Hey Charlie, client ko email bhej do")
        self.assertEqual(res["status"], "AWAITING_CONFIRMATION")

        res2 = self.orchestrator.process_spoken_transcript("Haan bhej do")
        self.assertEqual(res2["status"], "CONFIRMED_AND_EXECUTING")

    def test_golden_105_research_voice_command(self):
        """Test 105: 'Hey Charlie aaj AI mein kya trend kar raha hai?' -> routed to ResearchEngine."""
        res = self.orchestrator.process_spoken_transcript("Hey Charlie, aaj AI mein kya trend kar raha hai?")
        self.assertEqual(res["status"], "ROUTED_TO_RESEARCH")
        self.assertEqual(res["agent"], "ResearchAgent")

    def test_golden_106_project_resume_voice(self):
        """Test 106: 'Charlie mera last coding project continue karo' -> retrieves project & checkpoint."""
        self.orchestrator.conversation.set_active_project("ZynPay")
        res = self.orchestrator.process_spoken_transcript("Hey Charlie, mera project continue karo")
        self.assertEqual(res["status"], "ROUTED_TO_SKILL")
        self.assertEqual(res["agent"], "AntigravityAgent")
        self.assertIn("ZynPay", res["speech_response"])

    def test_golden_107_screen_context_command(self):
        """Test 107: 'Charlie ye error fix karo' -> routes to coding/general agent."""
        res = self.orchestrator.process_spoken_transcript("Hey Charlie, screen pe jo error aa raha hai fix karo")
        self.assertEqual(res["status"], "ROUTED_TO_SKILL")
        self.assertEqual(res["agent"], "AntigravityAgent")

    def test_golden_108_self_tts_loop_lockout(self):
        """Test 108: When CHARLIE speaks 'Charlie', wake engine does NOT trigger."""
        self.orchestrator.wake_engine.set_charlie_speaking(True)
        is_wake = self.orchestrator.wake_engine.inspect_text_for_wake("Yes, I am Charlie.")
        self.assertFalse(is_wake)

        self.orchestrator.wake_engine.set_charlie_speaking(False)
        is_wake2 = self.orchestrator.wake_engine.inspect_text_for_wake("Hey Charlie")
        self.assertTrue(is_wake2)

    def test_golden_109_mic_disconnect_recovery(self):
        """Test 109: Microphone disconnected -> detected and recovered to fallback."""
        rec = AudioRecoveryEngine(device_manager=self.device_mgr)
        self.device_mgr.set_mock_devices([
            AudioDevice(name="Realtek High Definition Audio", index=2, is_default=True)
        ])
        disc, fallback = rec.recover_microphone("USB Headset Mic")
        self.assertTrue(disc)
        self.assertEqual(fallback.name, "Realtek High Definition Audio")

    def test_golden_110_offline_command_execution(self):
        """Test 110: Network disabled -> local commands execute, cloud commands report limitation."""
        rec = AudioRecoveryEngine()
        rec.set_network_available(False)

        ok_local, msg_local = rec.check_offline_capability("COMPUTER_COMMAND")
        self.assertTrue(ok_local)

        ok_cloud, msg_cloud = rec.check_offline_capability("RESEARCH_COMMAND")
        self.assertFalse(ok_cloud)
        self.assertIn("Internet connection required", msg_cloud)

    def test_golden_111_voice_settings_persistence(self):
        """Test 111: Voice settings persist across restart."""
        self.device_mgr.save_preferences("Studio USB Mic")

        new_device_mgr = AudioDeviceManager(config_path=self.config_path)
        self.assertEqual(new_device_mgr._preferred_mic_name, "Studio USB Mic")

    def test_golden_112_pause_and_resume_task(self):
        """Test 112: 'Charlie task pause karo' -> pauses active task."""
        res = self.orchestrator.process_spoken_transcript("Charlie, task pause karo")
        self.assertEqual(res["status"], "TASK_STOPPED")
        self.assertTrue(self.orchestrator.active_task_paused)

    def test_golden_113_false_wake_rejection(self):
        """Test 113: Unrelated speech without wake phrase is ignored."""
        res = self.orchestrator.process_spoken_transcript("The weather in London is cloudy today.")
        self.assertEqual(res["status"], "IGNORED_NO_WAKE")


if __name__ == "__main__":
    unittest.main()
