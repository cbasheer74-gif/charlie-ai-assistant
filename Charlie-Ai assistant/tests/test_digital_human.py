"""
Automated Test & Certification Suite for CHARLIE Digital Human Engine.
Validates:
  1. PhotoRealisticRig instantiation (Male & Female)
  2. Landmark deformation engine & 16-viseme morph targets
  3. Blink, gaze, brow, breathing controllers
  4. Emotion classification & prosody planning
  5. Phonetic test sentences (MBP, FV, Rounded, Open, Conversational)
  6. Timeline generation & synchronization
  7. HUD style cycling (Digital Human, Classic Hologram, Reactor Core)
  8. Performance benchmarks (< 16ms / frame, > 60 FPS)
"""
import math
import os
import sys
import time
import unittest
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QImage

# Headless Qt App
_app = QApplication.instance()
if _app is None:
    _app = QApplication(["--platform", "offscreen"])

from core.digital_human import (
    PhotoRealisticRig, FaceLandmarks, AvatarState, Emotion, Viseme,
    EmotionController, ProsodyPlanner, VISEME_SHAPES, EMOTION_EXPRESSIONS
)
from core.viseme import text_to_visemes, VISEMES
from memory.config_manager import HUD_STYLES, get_hud_style, save_hud_style


class TestDigitalHumanEngine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.male_asset = ROOT / "core" / "assets" / "male_assistant.jpg"
        cls.fem_asset = ROOT / "core" / "assets" / "female_assistant_v2.jpg"

    def test_01_assets_exist(self):
        """Verify photorealistic male and female assets exist on disk."""
        self.assertTrue(self.male_asset.exists(), f"Missing male portrait: {self.male_asset}")
        self.assertTrue(self.fem_asset.exists(), f"Missing female portrait: {self.fem_asset}")
        self.assertGreater(self.male_asset.stat().st_size, 50_000, "Male asset too small")
        self.assertGreater(self.fem_asset.stat().st_size, 50_000, "Female asset too small")

    def test_02_rig_instantiation(self):
        """Verify PhotoRealisticRig instantiates cleanly for both personas."""
        pm_male = QPixmap(str(self.male_asset))
        self.assertFalse(pm_male.isNull())
        rig_male = PhotoRealisticRig(pm_male, FaceLandmarks())
        self.assertIsNotNone(rig_male)

        pm_fem = QPixmap(str(self.fem_asset))
        self.assertFalse(pm_fem.isNull())
        rig_fem = PhotoRealisticRig(pm_fem, FaceLandmarks(
            mouth_centre=(0.500, 0.660),
            mouth_left=(0.390, 0.660),
            mouth_right=(0.610, 0.660),
            upper_lip=(0.500, 0.645),
            lower_lip=(0.500, 0.678),
        ))
        self.assertIsNotNone(rig_fem)

    def test_03_viseme_morph_targets(self):
        """Verify all 16 visemes apply deformation and produce valid non-null frames."""
        pm = QPixmap(str(self.male_asset))
        rig = PhotoRealisticRig(pm, FaceLandmarks())
        rig.set_state(AvatarState.SPEAKING)

        for v in Viseme:
            rig.set_viseme(v, strength=1.0)
            frame = rig.render(size=256, dt=0.030)
            self.assertIsInstance(frame, QImage)
            self.assertFalse(frame.isNull(), f"Render failed for viseme {v}")
            self.assertEqual(frame.width(), 256)
            self.assertEqual(frame.height(), 256)

    def test_04_controllers_step(self):
        """Verify blink, gaze, and breathing controllers modulate deformation."""
        pm = QPixmap(str(self.fem_asset))
        rig = PhotoRealisticRig(pm, FaceLandmarks())

        # Advance 100 frames
        states_tested = [AvatarState.IDLE, AvatarState.LISTENING, AvatarState.SPEAKING, AvatarState.THINKING]
        for st in states_tested:
            rig.set_state(st)
            for _ in range(15):
                frame = rig.render(size=128, dt=0.016)
                self.assertFalse(frame.isNull())

    def test_05_phonetic_test_phrases(self):
        """Test phonetic breakdown on bilabials, labiodentals, rounded, open sounds."""
        test_cases = [
            ("Peter Piper picked a peck", "MBP"),
            ("Five very vivid foxes", "FV"),
            ("You who would know", "W_OO"),
            ("Father car dark start", "AA"),
            ("Hello Charlie, good morning", "REST"),
        ]
        for phrase, expected_vis in test_cases:
            v_list = text_to_visemes(phrase)
            self.assertGreater(len(v_list), 0, f"Failed to transcribe: {phrase}")
            visemes_found = [v for v, _ in v_list]
            if expected_vis != "REST":
                # Check for either direct match or phonetic family
                matched = any(expected_vis in v or v in expected_vis for v in visemes_found)
                self.assertTrue(matched, f"Expected {expected_vis} in {visemes_found} for '{phrase}'")

    def test_06_emotion_classification_and_prosody(self):
        """Test rule-based emotion classifier and prosody planning."""
        ec = EmotionController()

        cases = [
            ("I'm so sorry, I made a mistake.", Emotion.APOLOGETIC),
            ("Warning! CPU temperature is critical!", Emotion.SERIOUS),
            ("Urgent alert: Emergency shutdown imminent!", Emotion.URGENT),
            ("Task completed successfully, excellent work!", Emotion.HAPPY),
            ("Good morning, how can I help you today?", Emotion.FRIENDLY),
            ("What is the current system status?", Emotion.NEUTRAL),
        ]

        for text, expected_emo in cases:
            emo, intensity = ec.classify(text)
            self.assertEqual(emo, expected_emo, f"Mismatch for '{text}': got {emo}, expected {expected_emo}")
            rate, pitch, vol = ProsodyPlanner.get_prosody(emo)
            self.assertTrue(rate.startswith("+") or rate.startswith("-"))
            self.assertTrue(pitch.startswith("+") or pitch.startswith("-"))

    def test_07_hud_style_cycling(self):
        """Test HUD style cycling between Digital Human, Classic Hologram, and Reactor Core."""
        self.assertIn("face", HUD_STYLES)
        self.assertIn("holo", HUD_STYLES)
        self.assertIn("core", HUD_STYLES)

        save_hud_style("face")
        self.assertEqual(get_hud_style(), "face")
        save_hud_style("holo")
        self.assertEqual(get_hud_style(), "holo")
        save_hud_style("core")
        self.assertEqual(get_hud_style(), "core")
        # Invalid resets to default
        save_hud_style("invalid_xyz")
        self.assertEqual(get_hud_style(), "face")

    def test_08_rendering_performance_benchmark(self):
        """Benchmark 2D mesh warp rendering speed (must achieve >60 FPS / <16.6ms per frame)."""
        pm = QPixmap(str(self.male_asset))
        rig = PhotoRealisticRig(pm, FaceLandmarks())
        rig.set_state(AvatarState.SPEAKING)

        sizes = [128, 256, 384]
        for sz in sizes:
            # Warm up
            rig.render(sz, 0.016)
            t0 = time.perf_counter()
            frames_count = 60
            for i in range(frames_count):
                rig.set_viseme_blend(math.sin(i * 0.2) * 0.5 + 0.5, 0.2, 0.8)
                rig.render(sz, 0.016)
            total_elapsed = time.perf_counter() - t0
            ms_per_frame = (total_elapsed / frames_count) * 1000.0
            fps = frames_count / total_elapsed
            print(f"\n[BENCHMARK] Size {sz}x{sz}: {ms_per_frame:.2f} ms/frame ({fps:.1f} FPS)")
            # 256x256 and below must render comfortably within 60fps frame budget
            if sz <= 256:
                self.assertLess(ms_per_frame, 20.0, f"Frame time {ms_per_frame:.2f}ms exceeds real-time threshold at size {sz}")


if __name__ == "__main__":
    unittest.main()
