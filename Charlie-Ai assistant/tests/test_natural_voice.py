import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from memory import config_manager as config


class TestNaturalVoiceSettings(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_dir = config.CONFIG_DIR
        self.old_file = config.CONFIG_FILE
        config.CONFIG_DIR = Path(self.temp.name) / "config"
        config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        config.CONFIG_FILE = config.CONFIG_DIR / "api_keys.json"
        self._orig_vault_env = os.environ.get("CHARLIE_VAULT_PATH")
        os.environ["CHARLIE_VAULT_PATH"] = str(Path(self.temp.name) / "test_vault.dat")
        # These tests exercise voice persistence, not commercial entitlements.
        # Plan-gating behavior has its own commercial test suite.
        self.commercial_patch = patch(
            "engine.commercial.core.get_commercial_engine",
            return_value=SimpleNamespace(
                verify_voice_access=lambda _persona: (True, "Voice unlocked.")))
        self.commercial_patch.start()

    def tearDown(self):
        self.commercial_patch.stop()
        if self._orig_vault_env is not None:
            os.environ["CHARLIE_VAULT_PATH"] = self._orig_vault_env
        else:
            os.environ.pop("CHARLIE_VAULT_PATH", None)
        config.CONFIG_DIR = self.old_dir
        config.CONFIG_FILE = self.old_file
        self.temp.cleanup()

    def test_all_live_voices_are_available(self):
        self.assertEqual(len(config.AVAILABLE_VOICES), 30)
        self.assertEqual(len(config.voices_for_persona("female")), 14)
        self.assertEqual(len(config.voices_for_persona("male")), 16)
        self.assertEqual(config.VOICE_GENDERS["Enceladus"], "male")
        self.assertEqual(config.VOICE_GENDERS["Achernar"], "female")
        self.assertEqual(config.VOICE_STYLES["Sulafat"], "Warm")
        self.assertEqual(config.VOICE_STYLES["Algieba"], "Smooth")

    def test_male_and_female_voices_are_independent(self):
        config.save_persona_voice("male", "Algieba")
        config.save_persona_voice("female", "Achernar")

        config.save_assistant_persona("female")
        self.assertEqual(config.get_voice(), "Achernar")
        config.save_assistant_persona("male")
        self.assertEqual(config.get_voice(), "Algieba")

    def test_direct_voice_change_updates_only_active_persona(self):
        config.save_persona_voice("male", "Charon")
        config.save_persona_voice("female", "Aoede")
        config.save_assistant_persona("male")
        config.save_voice("Iapetus")
        self.assertEqual(config.get_persona_voice("male"), "Iapetus")
        self.assertEqual(config.get_persona_voice("female"), "Aoede")

    def test_mismatched_gender_voice_is_rejected(self):
        config.save_persona_voice("female", "Enceladus")
        config.save_persona_voice("male", "Achernar")
        self.assertEqual(config.get_persona_voice("female"), "Achernar")
        self.assertEqual(config.get_persona_voice("male"), "Achird")

    def test_sweet_voice_upgrade_runs_once_and_preserves_later_choice(self):
        config.save_api_keys("secret-key-that-is-long-enough")
        config.save_assistant_persona("female")
        self.assertTrue(config.ensure_sweet_voice_profiles())
        self.assertEqual(config.get_voice(), "Achernar")
        self.assertEqual(config.get_persona_voice("male"), "Achird")
        self.assertEqual(config.get_gemini_key(), "secret-key-that-is-long-enough")

        config.save_voice("Aoede")
        self.assertFalse(config.ensure_sweet_voice_profiles())
        self.assertEqual(config.get_voice(), "Aoede")

    def test_persona_grammar_instructions_match_self_reference(self):
        female = config.get_assistant_grammar_instruction("female")
        self.assertIn("female assistant", female)
        self.assertIn("main kar sakti hoon", female)
        self.assertIn("Never use masculine self-forms", female)
        self.assertIn("do not guess the user's gender", female)

        male = config.get_assistant_grammar_instruction("male")
        self.assertIn("male assistant", male)
        self.assertIn("main kar sakta hoon", male)

    def test_slow_speech_mode_uses_patient_endpointing(self):
        config.save_slow_speech_enabled(True)
        slow = config.get_turn_tuning()
        self.assertTrue(config.get_slow_speech_enabled())
        self.assertEqual(slow["silence_ms"], 2200)
        self.assertEqual(slow["prefix_ms"], 500)
        self.assertEqual(slow["end_sensitivity"], "low")
        self.assertEqual(slow["start_sensitivity"], "high")

        config.save_slow_speech_enabled(False)
        normal = config.get_turn_tuning()
        self.assertFalse(config.get_slow_speech_enabled())
        self.assertEqual(normal["silence_ms"], 900)
        self.assertEqual(normal["prefix_ms"], 300)


if __name__ == "__main__":
    unittest.main()
