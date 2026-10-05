import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.hotkey import DEFAULT_CHORD, GlobalShortcut, PushToTalk
from ui import INTELLIGENCE_FEATURES, MainWindow


class IntelligenceHubTests(unittest.TestCase):
    def test_all_twelve_features_are_registered_once(self):
        self.assertEqual(len(INTELLIGENCE_FEATURES), 12)
        names = [feature[0] for feature in INTELLIGENCE_FEATURES]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("Privacy Dashboard", names)
        self.assertIn("Offline Survival", names)

    def test_push_to_talk_does_not_conflict_with_command_bar(self):
        self.assertEqual(DEFAULT_CHORD, ("f8",))
        self.assertEqual(PushToTalk(lambda _held: None).label, "F8")
        self.assertIsInstance(GlobalShortcut(lambda: None), GlobalShortcut)

    def test_feature_launch_routes_through_assistant(self):
        received = []
        window = SimpleNamespace(
            _intelligence_hub=SimpleNamespace(hide=lambda: None),
            _log=SimpleNamespace(append_log=lambda _text: None),
            request_say=received.append,
            _input=SimpleNamespace(setText=lambda _text: None, setFocus=lambda: None),
        )

        class ImmediateThread:
            def __init__(self, target, args, daemon):
                self.target, self.args = target, args

            def start(self):
                self.target(*self.args)

        with patch("ui.threading.Thread", ImmediateThread):
            MainWindow._launch_intelligence_feature(window, "Open private knowledge vault")
        self.assertEqual(received, ["Open private knowledge vault"])

    def test_command_bar_uses_only_the_active_mode(self):
        voice, chat = [], []
        window = SimpleNamespace(
            _chat_mode=False,
            _log=SimpleNamespace(append_log=lambda _text: None),
            on_text_command=voice.append,
            on_chat_command=chat.append,
            _input=SimpleNamespace(setText=lambda _text: None),
        )

        class ImmediateThread:
            def __init__(self, target, args, daemon):
                self.target, self.args = target, args

            def start(self):
                self.target(*self.args)

        with patch("ui.threading.Thread", ImmediateThread):
            MainWindow._submit_universal_command(window, "open calculator")
            window._chat_mode = True
            MainWindow._submit_universal_command(window, "explain this code")
        self.assertEqual(voice, ["open calculator"])
        self.assertEqual(chat, ["explain this code"])


if __name__ == "__main__":
    unittest.main()
