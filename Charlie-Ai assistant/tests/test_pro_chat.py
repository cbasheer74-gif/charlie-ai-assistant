import tempfile
import unittest
from pathlib import Path

from engine.pro_chat import ProChatAssistant


class ProChatAssistantTests(unittest.TestCase):
    def test_follow_up_receives_prior_turns(self):
        calls = []

        def generate(system, messages):
            calls.append((system, messages))
            return "First answer" if len(calls) == 1 else "Follow-up answer"

        chat = ProChatAssistant(generate=generate)
        self.assertEqual(chat.respond("Explain recursion"), "First answer")
        self.assertEqual(chat.respond("Show an example"), "Follow-up answer")
        self.assertEqual(
            [m["role"] for m in calls[1][1]],
            ["user", "assistant", "user"],
        )
        self.assertIn("Explain recursion", calls[1][1][0]["content"])

    def test_new_chat_clears_context(self):
        seen = []
        chat = ProChatAssistant(generate=lambda _s, messages: seen.append(messages) or "ok")
        chat.respond("one")
        chat.new_chat()
        chat.respond("two")
        self.assertEqual(len(seen[1]), 1)
        self.assertEqual(seen[1][0]["content"], "two")

    def test_text_attachment_is_supplied_but_not_saved_in_history(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.py"
            path.write_text("print('hello')", encoding="utf-8")
            captured = []
            chat = ProChatAssistant(
                generate=lambda _s, messages: captured.append(messages) or "reviewed"
            )
            chat.respond("Review this file", str(path))
            self.assertIn("print('hello')", captured[0][-1]["content"])
            self.assertNotIn("print('hello')", chat.history[0]["content"])

    def test_empty_prompt_does_not_call_model(self):
        chat = ProChatAssistant(generate=lambda *_: self.fail("model called"))
        self.assertIn("type a question", chat.respond("   ").lower())


if __name__ == "__main__":
    unittest.main()
