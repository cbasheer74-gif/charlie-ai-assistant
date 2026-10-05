import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ui import CharlieUI, MainWindow


class UiCallbackWiringTests(unittest.TestCase):
    def test_request_say_property_reaches_main_window(self):
        wrapper = object.__new__(CharlieUI)
        wrapper._win = SimpleNamespace(request_say=None)
        callback = lambda instruction: instruction

        wrapper.request_say = callback

        self.assertIs(wrapper._win.request_say, callback)
        self.assertIs(wrapper.request_say, callback)

    def test_chat_callbacks_reach_main_window(self):
        wrapper = object.__new__(CharlieUI)
        wrapper._win = SimpleNamespace(
            on_chat_command=None,
            on_new_chat=None,
            on_chat_dictation=None,
        )
        chat_callback = lambda text: text
        new_callback = lambda: None
        dictation_callback = lambda enabled: enabled
        wrapper.on_chat_command = chat_callback
        wrapper.on_new_chat = new_callback
        wrapper.on_chat_dictation = dictation_callback
        self.assertIs(wrapper.on_chat_command, chat_callback)
        self.assertIs(wrapper.on_new_chat, new_callback)
        self.assertIs(wrapper.on_chat_dictation, dictation_callback)

    def test_chat_mode_mic_button_routes_only_to_dictation(self):
        calls = []
        window = SimpleNamespace(
            _chat_mode=True,
            _muted=True,
            _toggle_chat_dictation=lambda: calls.append("dictation"),
        )

        MainWindow._toggle_mute(window)

        self.assertEqual(calls, ["dictation"])
        self.assertTrue(window._muted)

    def test_dictated_text_is_placed_in_composer_without_auto_send(self):
        class Input:
            def __init__(self):
                self.value = "Plan"

            def text(self):
                return self.value

            def setText(self, value):
                self.value = value

            def setCursorPosition(self, _position):
                pass

            def setFocus(self):
                pass

        messages = []
        window = SimpleNamespace(
            _chat_mode=True,
            _input=Input(),
            _log=SimpleNamespace(append_log=messages.append),
            _set_chat_dictation_state=lambda _active: None,
        )

        MainWindow._apply_chat_dictation_text(window, "a launch campaign")

        self.assertEqual(window._input.value, "Plan a launch campaign")
        self.assertTrue(any("message box" in message for message in messages))

    def test_surprise_button_sends_generated_instruction(self):
        received = []
        window = SimpleNamespace(request_say=received.append)
        with patch("memory.learning_brain.start_surprise", return_value="fresh surprise"):
            MainWindow._start_surprise_mode(window)
        self.assertEqual(received, ["fresh surprise"])

    def test_game_room_button_uses_same_speech_channel(self):
        received = []
        window = SimpleNamespace(request_say=received.append)
        with patch("memory.game_room.menu_instruction", return_value="game menu"):
            MainWindow._open_game_room(window)
        self.assertEqual(received, ["game menu"])


if __name__ == "__main__":
    unittest.main()
