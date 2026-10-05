"""tests/test_conversational_intelligence.py — Verification of Voice Intelligence Pillars.

Validates:
1. Prosody Emotion Matching (cadence, speed, volume modulation)
2. Instant Acoustic Barge-In (sub-50ms acoustic VAD cancellation)
3. Conversational Backchanneling (affirmative cues & visual nods during pauses)
4. Adaptive Turn-Taking (dynamic 350ms-1150ms silence thresholds based on syntax)
5. Integrated Voice Pipeline (VAD, TTS, BargeInManager, and Orchestrator)
"""

from __future__ import annotations

import time
import unittest
import numpy as np

from engine.voice.conversational_intelligence import (
    AdaptiveTurnTakingEngine,
    BackchannelManager,
    ConversationalVoiceSuite,
    InstantBargeInController,
    ProsodyEmotionMatcher,
    ProsodyProfile,
    get_voice_suite,
)
from engine.voice.barge_in import BargeInManager
from engine.voice.tts import MockTTSProvider, TextToSpeechManager
from engine.voice.vad import VoiceActivityDetector


class TestConversationalIntelligence(unittest.TestCase):

    def setUp(self):
        self.suite = ConversationalVoiceSuite()

    # ── 1. Prosody Emotion Matching ──────────────────────────────────────────

    def test_prosody_emotion_profiles(self):
        matcher = self.suite.prosody

        calm_prof = matcher.get_prosody_for_emotion("calm")
        self.assertEqual(calm_prof.speed, 1.0)
        self.assertEqual(calm_prof.volume, 1.0)

        stressed_prof = matcher.get_prosody_for_emotion("stressed")
        self.assertGreater(stressed_prof.speed, 1.10)
        self.assertEqual(stressed_prof.style, "crisp")

        tired_prof = matcher.get_prosody_for_emotion("tired")
        self.assertLess(tired_prof.speed, 0.95)
        self.assertLess(tired_prof.volume, 0.90)

        energetic_prof = matcher.get_prosody_for_emotion("energetic")
        self.assertGreater(energetic_prof.speed, 1.05)
        self.assertGreater(energetic_prof.pitch_adjustment_hz, 0.0)

    def test_tts_param_modulation(self):
        matcher = self.suite.prosody
        speed, vol, tone = matcher.modulate_tts_params("stressed", base_speed=1.0, base_volume=1.0)
        self.assertGreater(speed, 1.0)
        self.assertEqual(tone, "efficient_direct")

        speed_tired, vol_tired, _ = matcher.modulate_tts_params("tired", base_speed=1.0, base_volume=1.0)
        self.assertLess(speed_tired, 1.0)
        self.assertLess(vol_tired, 1.0)

    # ── 2. Instant Acoustic Barge-In ─────────────────────────────────────────

    def test_instant_acoustic_barge_in_trigger(self):
        barge_triggered = []

        def on_barge():
            barge_triggered.append(True)

        controller = InstantBargeInController(
            energy_threshold=0.015,
            required_consecutive_frames=3,
            on_barge_in=on_barge,
        )

        # Frame when AI is NOT speaking -> should never trigger
        for _ in range(5):
            res = controller.process_frame(energy=0.030, is_ai_speaking=False)
            self.assertFalse(res)
        self.assertEqual(len(barge_triggered), 0)

        # Frames with low energy when AI IS speaking -> should not trigger
        for _ in range(5):
            res = controller.process_frame(energy=0.005, is_ai_speaking=True)
            self.assertFalse(res)
        self.assertEqual(len(barge_triggered), 0)

        # 2 frames high energy (< 3 required) -> not triggered yet
        self.assertFalse(controller.process_frame(energy=0.025, is_ai_speaking=True))
        self.assertFalse(controller.process_frame(energy=0.025, is_ai_speaking=True))
        self.assertEqual(len(barge_triggered), 0)

        # 3rd consecutive high energy frame -> triggers barge-in!
        res_3 = controller.process_frame(energy=0.025, is_ai_speaking=True)
        self.assertTrue(res_3)
        self.assertEqual(len(barge_triggered), 1)

    def test_barge_in_manager_acoustic_integration(self):
        mock_tts = MockTTSProvider()
        tts_mgr = TextToSpeechManager(provider=mock_tts)
        barge_mgr = BargeInManager(tts_manager=tts_mgr)

        tts_mgr.speak("Speaking an important long answer...")
        self.assertTrue(tts_mgr.is_speaking())

        # Feed 3 high-energy acoustic frames
        barge_mgr.process_acoustic_frame(0.04)
        barge_mgr.process_acoustic_frame(0.04)
        triggered = barge_mgr.process_acoustic_frame(0.04)

        self.assertTrue(triggered)
        self.assertFalse(tts_mgr.is_speaking())
        self.assertTrue(any(e.trigger_word == "[ACOUSTIC_ENERGY_VAD]" for e in barge_mgr._interruption_history))

    # ── 3. Conversational Backchanneling ────────────────────────────────────

    def test_backchanneling_timing(self):
        backchannel = BackchannelManager(
            min_speech_duration=0.5,
            min_silence_window=0.1,
            max_silence_window=0.3,
            cue_cooldown=0.5,
        )

        # User speaking for > 0.5s
        backchannel.on_speech_frame(is_voice=True)
        time.sleep(0.55)

        # User pauses briefly for 0.15s
        backchannel.on_speech_frame(is_voice=False)
        time.sleep(0.15)
        event = backchannel.on_speech_frame(is_voice=False)

        self.assertIsNotNone(event)
        self.assertEqual(event["type"], "backchannel")
        self.assertTrue(event["visual_nod"])
        self.assertIn(event["cue"], BackchannelManager.CUES_ENGLISH)

    # ── 4. Adaptive Turn-Taking ──────────────────────────────────────────────

    def test_adaptive_turn_taking_hesitation_vs_conclusive(self):
        engine = AdaptiveTurnTakingEngine()

        # Hesitant phrase ending in connector -> expanded pause
        timeout_hesitant = engine.evaluate_silence_timeout("I wanted to check the logs because")
        self.assertEqual(timeout_hesitant, AdaptiveTurnTakingEngine.EXPANDED_PAUSE_TIMEOUT)
        self.assertGreaterEqual(timeout_hesitant, 1.10)

        # Crisp question -> fast snappy response
        timeout_question = engine.evaluate_silence_timeout("What is the CPU usage right now?")
        self.assertEqual(timeout_question, AdaptiveTurnTakingEngine.FAST_RESPONSE_TIMEOUT)
        self.assertLessEqual(timeout_question, 0.45)

        # Command with polite / prompt keyword -> fast response
        timeout_command = engine.evaluate_silence_timeout("open project folder please")
        self.assertEqual(timeout_command, AdaptiveTurnTakingEngine.FAST_RESPONSE_TIMEOUT)

        # Neutral sentence -> standard timeout
        timeout_neutral = engine.evaluate_silence_timeout("The build completed with zero warnings")
        self.assertEqual(timeout_neutral, AdaptiveTurnTakingEngine.STANDARD_TIMEOUT)

    # ── 5. VAD and TTS Live Integration ──────────────────────────────────────

    def test_vad_adaptive_timeout(self):
        vad = VoiceActivityDetector(silence_timeout_sec=1.3)
        self.assertEqual(vad.silence_timeout_sec, 1.3)

        # Adapt timeout to a rapid question
        adapted = vad.adapt_timeout("Where are the test results?")
        self.assertEqual(adapted, AdaptiveTurnTakingEngine.FAST_RESPONSE_TIMEOUT)
        self.assertEqual(vad.silence_timeout_sec, AdaptiveTurnTakingEngine.FAST_RESPONSE_TIMEOUT)

        # Adapt timeout to hesitant connector
        adapted_hes = vad.adapt_timeout("Let me check the database and...")
        self.assertEqual(adapted_hes, AdaptiveTurnTakingEngine.EXPANDED_PAUSE_TIMEOUT)
        self.assertEqual(vad.silence_timeout_sec, AdaptiveTurnTakingEngine.EXPANDED_PAUSE_TIMEOUT)

    def test_tts_prosody_dispatch(self):
        mock_tts = MockTTSProvider()
        tts_mgr = TextToSpeechManager(provider=mock_tts)

        # Speak with energetic emotion
        tts_mgr.speak("System initialized successfully!", emotion="energetic")
        time.sleep(0.08)
        self.assertEqual(mock_tts.last_spoken, "System initialized successfully!")


if __name__ == "__main__":
    unittest.main()
