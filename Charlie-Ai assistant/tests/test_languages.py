import unittest
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.languages import (
    LANGUAGES,
    resolve_language,
    get_all_language_keys,
    get_language_choices_ui,
    get_language_voice,
    get_whisper_code,
    detect_language_script,
    get_language_prompt_rule,
)
from memory import personal_hub


class TestLanguages(unittest.TestCase):
    def test_regional_languages_registered(self):
        regional = [
            "hindi", "marathi", "bengali", "tamil", "telugu",
            "gujarati", "kannada", "malayalam", "punjabi", "urdu",
            "odia", "assamese", "bhojpuri", "sanskrit", "nepali"
        ]
        for lang in regional:
            info = resolve_language(lang)
            self.assertIsNotNone(info, f"Missing regional language: {lang}")
            self.assertTrue(bool(info.tts_female))
            self.assertTrue(bool(info.tts_male))
            self.assertTrue(bool(info.whisper_code))

    def test_world_languages_registered(self):
        world = [
            "english", "spanish", "french", "german", "italian",
            "portuguese", "russian", "japanese", "chinese", "korean",
            "arabic", "turkish", "dutch", "polish", "vietnamese",
            "thai", "filipino", "persian", "hebrew", "swahili"
        ]
        for lang in world:
            info = resolve_language(lang)
            self.assertIsNotNone(info, f"Missing world language: {lang}")
            self.assertTrue(bool(info.tts_female))
            self.assertTrue(bool(info.tts_male))

    def test_ui_choices_populated(self):
        choices = get_language_choices_ui()
        self.assertGreater(len(choices), 40)
        keys = [val for _, val in choices]
        self.assertIn("auto", keys)
        self.assertIn("english", keys)
        self.assertIn("hindi", keys)
        self.assertIn("marathi", keys)
        self.assertIn("tamil", keys)
        self.assertIn("japanese", keys)
        self.assertIn("spanish", keys)

    def test_whisper_code_mapping(self):
        self.assertEqual(get_whisper_code("marathi"), "mr")
        self.assertEqual(get_whisper_code("hindi"), "hi")
        self.assertEqual(get_whisper_code("japanese"), "ja")
        self.assertEqual(get_whisper_code("spanish"), "es")
        self.assertEqual(get_whisper_code("auto"), None)

    def test_script_detection(self):
        # Japanese Katakana
        ja = detect_language_script("こんにちは、チャーリー")
        self.assertIsNotNone(ja)
        self.assertEqual(ja.code, "ja")

        # Devanagari Marathi
        mr = detect_language_script("नमस्कार, कसे आहात तुम्ही?")
        self.assertIsNotNone(mr)
        self.assertEqual(mr.code, "mr")

        # Tamil
        ta = detect_language_script("வணக்கம்")
        self.assertIsNotNone(ta)
        self.assertEqual(ta.code, "ta")

        # Russian
        ru = detect_language_script("Привет Чарли")
        self.assertIsNotNone(ru)
        self.assertEqual(ru.code, "ru")

    def test_personal_hub_set_speech_preferences_all_languages(self):
        # Set Marathi
        s = personal_hub.set_speech_preferences(language="marathi")
        self.assertEqual(s["language"], "marathi")

        # Set French
        s = personal_hub.set_speech_preferences(language="french")
        self.assertEqual(s["language"], "french")

        # Set Japanese
        s = personal_hub.set_speech_preferences(language="japanese")
        self.assertEqual(s["language"], "japanese")

        # Reset to auto
        s = personal_hub.set_speech_preferences(language="auto")
        self.assertEqual(s["language"], "auto")


if __name__ == "__main__":
    unittest.main()
