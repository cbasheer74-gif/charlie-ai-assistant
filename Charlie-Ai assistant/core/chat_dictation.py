"""Windows speech dictation used only by the AI Chat composer.

The realtime voice assistant owns normal Voice mode.  This service deliberately
captures a single dictated phrase through Windows SAPI so chat dictation cannot
send microphone audio to the realtime assistant or trigger a spoken response.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class ChatDictationService:
    """Non-blocking, single-owner, one-utterance Windows dictation service."""

    def __init__(self, timeout_seconds: float = 18.0):
        self.timeout_seconds = max(3.0, float(timeout_seconds))
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def active(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive() and not self._stop.is_set())

    def start(
        self,
        on_result: Callable[[str], None],
        on_status: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> bool:
        """Start listening. Returns False when another dictation already owns it."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                return False
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                args=(on_result, on_status, on_error),
                daemon=True,
                name="chat-dictation",
            )
            self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()

    def _run(self, on_result, on_status, on_error) -> None:
        grammar = None
        try:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            if on_status:
                on_status("Listening")

            recognizer = win32com.client.Dispatch("SAPI.SpInprocRecognizer")
            recognizer.AudioInput = recognizer.GetAudioInputs().Item(0)
            context = recognizer.CreateRecoContext()
            grammar = context.CreateGrammar()
            grammar.DictationLoad("", 0)

            state = {"text": ""}

            class RecognitionEvents:
                def OnRecognition(self, _stream_no, _stream_pos, _kind, result):
                    try:
                        state["text"] = str(result.PhraseInfo.GetText()).strip()
                    except Exception:
                        state["text"] = ""

            events = win32com.client.WithEvents(context, RecognitionEvents)
            grammar.DictationSetState(1)
            deadline = time.monotonic() + self.timeout_seconds
            while not self._stop.is_set() and not state["text"] and time.monotonic() < deadline:
                pythoncom.PumpWaitingMessages()
                time.sleep(0.03)

            if state["text"] and not self._stop.is_set():
                on_result(state["text"])
            elif not self._stop.is_set() and on_error:
                on_error("I couldn't hear a complete phrase. Please try again.")
            # Keep the COM event sink referenced until recognition is disabled.
            _ = events
        except Exception as exc:
            if not self._stop.is_set() and on_error:
                on_error(f"Chat dictation is unavailable: {exc}")
        finally:
            if grammar is not None:
                try:
                    grammar.DictationSetState(0)
                except Exception:
                    pass
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass
            self._stop.set()
            if on_status:
                on_status("Idle")
