import unittest
import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.voice.user_greeter_clean import (
    build_greeting,
    build_session_greeting,
    build_language_confirm,
    build_unclear_audio_message,
    detect_hindi_speech,
    detect_lang_from_response,
    detect_lang_switch,
    SessionLanguageManager,
    LangPreference,
)


class TestUserGreeterClean(unittest.TestCase):
    def test_build_greeting(self):
        msg = build_greeting(user_name="John", assistant_name="Charlie")
        self.assertIn("Charlie", msg)
        self.assertIn("John", msg)

    def test_build_session_greeting(self):
        msg, mgr = build_session_greeting(user_name="John", assistant_name="Charlie")
        self.assertIsInstance(mgr, SessionLanguageManager)
        self.assertIn("Charlie", msg)

    def test_build_language_confirm(self):
        mr = build_language_confirm("marathi")
        self.assertIn("मराठी", mr)
        es = build_language_confirm("spanish")
        self.assertIn("español", es)

    def test_detect_hindi_speech(self):
        self.assertTrue(detect_hindi_speech("नमस्ते चार्ली क्या हाल है"))
        self.assertTrue(detect_hindi_speech("kya haal hai bhai bolo"))
        self.assertFalse(detect_hindi_speech("hello world open chrome"))


if __name__ == "__main__":
    unittest.main()
