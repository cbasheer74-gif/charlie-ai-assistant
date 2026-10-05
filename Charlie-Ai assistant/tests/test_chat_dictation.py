import threading
import time
import unittest
from unittest.mock import patch

from core.chat_dictation import ChatDictationService


class ChatDictationServiceTests(unittest.TestCase):
    def test_only_one_dictation_worker_can_run(self):
        service = ChatDictationService()
        entered = threading.Event()
        release = threading.Event()

        def fake_run(*_args):
            entered.set()
            release.wait(2)

        with patch.object(service, "_run", side_effect=fake_run):
            self.assertTrue(service.start(lambda _text: None))
            self.assertTrue(entered.wait(1))
            self.assertFalse(service.start(lambda _text: None))
            release.set()
            deadline = time.monotonic() + 2
            while service._thread and service._thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.01)

    def test_stop_marks_service_inactive(self):
        service = ChatDictationService()
        service._stop.clear()
        service.stop()
        self.assertFalse(service.active)


if __name__ == "__main__":
    unittest.main()
