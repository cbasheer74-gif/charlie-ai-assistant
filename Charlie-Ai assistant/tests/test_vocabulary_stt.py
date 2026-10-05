"""Unit and regression tests for Phase 3 Step 11: VocabularyContextManager Fallback STT Integration.

Validates:
A. Vocabulary manager returns bounded and deduplicated terms.
B. Whisper receives effective initial_prompt (including primed terms).
C. Normal speech with no custom vocabulary still transcribes cleanly.
D. Missing or None VocabularyContextManager fails gracefully without exceptions.
E. Very large vocabulary inputs are safely truncated at bounds.
F. No sensitive conversation history or chat turns are persisted in vocabulary.
G. Vosk fallback remains operational and stable.
H. Step 1 async offload (asyncio.to_thread) pattern preserved.
I. TranscriptNormalizer behavior remains unchanged.
J. Specific technical keywords recognized: Antigravity, PyQt6, PostgreSQL, Lekhtra, Groq.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

# Ensure paths
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.voice.stt import (
    VocabularyContextManager,
    TranscriptNormalizer,
    FasterWhisperSTTProvider,
    SpeechRecognitionManager,
    MockSTTProvider,
)
from core.stt import WhisperSTT, VoskSTT


class TestVocabularyContextManager(unittest.TestCase):
    """Test suite for VocabularyContextManager and STT vocabulary priming."""

    # --------------------------------------------------------------------------
    # A. Bounded and deduplicated terms
    # --------------------------------------------------------------------------
    def test_a_bounded_and_deduplicated_terms(self):
        """Verify VocabularyContextManager deduplicates case-insensitively and bounds count."""
        mgr = VocabularyContextManager(custom_terms=["pyqt6", "PyQt6", "GROQ", "groq", "Lekhtra"])
        terms = mgr.get_terms()

        # Check deduplication: pyqt6 and groq should only appear once
        groq_count = sum(1 for t in terms if t.lower() == "groq")
        pyqt_count = sum(1 for t in terms if t.lower() == "pyqt6")
        self.assertEqual(groq_count, 1)
        self.assertEqual(pyqt_count, 1)

        # Check bounds: total count must not exceed MAX_ITEMS (50)
        self.assertLessEqual(len(terms), VocabularyContextManager.MAX_ITEMS)

    # --------------------------------------------------------------------------
    # B. Whisper receives initial_prompt when supported
    # --------------------------------------------------------------------------
    @patch("faster_whisper.WhisperModel")
    def test_b_whisper_receives_initial_prompt(self, mock_whisper_cls):
        """Verify WhisperSTT passes primed vocabulary in initial_prompt to model.transcribe."""
        mock_model = MagicMock()
        mock_whisper_cls.return_value = mock_model
        mock_segment = MagicMock()
        mock_segment.text = "Testing speech"
        mock_model.transcribe.return_value = ([mock_segment], None)

        mgr = VocabularyContextManager(custom_terms=["Antigravity", "Lekhtra"])
        stt = WhisperSTT(model_name="base", vocabulary_manager=mgr)

        # Dummy audio with sufficient energy
        audio = (np.ones(16000, dtype=np.float32) * 0.1)
        res = stt.transcribe(audio, vocabulary_context="DynamicProject")

        self.assertEqual(res, "Testing speech")
        self.assertTrue(mock_model.transcribe.called)
        _, kwargs = mock_model.transcribe.call_args
        initial_prompt = kwargs.get("initial_prompt", "")
        self.assertIn("Antigravity", initial_prompt)
        self.assertIn("Lekhtra", initial_prompt)
        self.assertIn("DynamicProject", initial_prompt)

    # --------------------------------------------------------------------------
    # C. Normal speech with no custom vocabulary still works
    # --------------------------------------------------------------------------
    @patch("faster_whisper.WhisperModel")
    def test_c_normal_speech_no_custom_vocabulary(self, mock_whisper_cls):
        """Verify default vocabulary operates cleanly without custom terms."""
        mock_model = MagicMock()
        mock_whisper_cls.return_value = mock_model
        mock_segment = MagicMock()
        mock_segment.text = "Hello world"
        mock_model.transcribe.return_value = ([mock_segment], None)

        stt = WhisperSTT(model_name="base", vocabulary_manager=None)
        audio = (np.ones(16000, dtype=np.float32) * 0.1)
        res = stt.transcribe(audio)

        self.assertEqual(res, "Hello world")
        self.assertTrue(mock_model.transcribe.called)

    # --------------------------------------------------------------------------
    # D. Missing VocabularyContextManager fails gracefully
    # --------------------------------------------------------------------------
    @patch("faster_whisper.WhisperModel")
    def test_d_missing_vocab_manager_fails_gracefully(self, mock_whisper_cls):
        """Verify WhisperSTT initializes and functions even if vocabulary_manager is None."""
        mock_model = MagicMock()
        mock_whisper_cls.return_value = mock_model
        mock_segment = MagicMock()
        mock_segment.text = "System active"
        mock_model.transcribe.return_value = ([mock_segment], None)

        stt = WhisperSTT(model_name="base", vocabulary_manager=None)
        stt._vocab_mgr = None  # Force None
        stt._initial_prompt = stt._build_initial_prompt("en", None)

        audio = (np.ones(16000, dtype=np.float32) * 0.1)
        res = stt.transcribe(audio)
        self.assertEqual(res, "System active")

    # --------------------------------------------------------------------------
    # E. Very large vocabulary is safely truncated
    # --------------------------------------------------------------------------
    def test_e_large_vocabulary_truncated(self):
        """Verify excessive items or prompt lengths are bounded to max limits."""
        mgr = VocabularyContextManager()
        # Add 200 long unique terms
        huge_terms = [f"UniqueVeryLongTechnicalTermNumber{i}ServiceFramework" for i in range(200)]
        mgr.add_terms(huge_terms)

        terms = mgr.get_terms()
        self.assertLessEqual(len(terms), mgr.MAX_ITEMS)

        prompt_ctx = mgr.get_prompt_context()
        self.assertLessEqual(len(prompt_ctx), mgr.MAX_PROMPT_CHARS)

    # --------------------------------------------------------------------------
    # F. No sensitive conversation history is persisted
    # --------------------------------------------------------------------------
    def test_f_no_sensitive_history_persisted(self):
        """Verify manager only stores project/technical terms, not raw chat text."""
        mgr = VocabularyContextManager()
        mgr.add_project_terms("ProjectAlpha", ["Docker", "Kubernetes"])

        terms = mgr.get_terms()
        self.assertIn("ProjectAlpha", terms)
        self.assertIn("Docker", terms)

        # Confirm manager does not have arbitrary chat storage attributes
        self.assertFalse(hasattr(mgr, "chat_history"))
        self.assertFalse(hasattr(mgr, "conversation_log"))

    # --------------------------------------------------------------------------
    # G. Vosk fallback remains operational
    # --------------------------------------------------------------------------
    @patch("vosk.Model")
    @patch("vosk.KaldiRecognizer")
    def test_g_vosk_fallback_operational(self, mock_rec_cls, mock_model_cls):
        """Verify VoskSTT continues to initialize and process chunks normally."""
        mock_rec = MagicMock()
        mock_rec_cls.return_value = mock_rec
        mock_rec.AcceptWaveform.return_value = True
        mock_rec.Result.return_value = '{"text": "offline command"}'

        vosk = VoskSTT(model_path="fake/path")
        text, is_final = vosk.process_chunk(b"\x00" * 3200)

        self.assertEqual(text, "offline command")
        self.assertTrue(is_final)

    # --------------------------------------------------------------------------
    # H. Step 1 async offload verification
    # --------------------------------------------------------------------------
    def test_h_async_offload_preservation(self):
        """Verify main.py fallback voice transcription preserves asyncio.to_thread offload."""
        import inspect
        import main

        src = inspect.getsource(main.CharlieLive._listen_audio)
        self.assertIn("asyncio.to_thread(stt.transcribe", src)

    # --------------------------------------------------------------------------
    # I. TranscriptNormalizer behavior preserved
    # --------------------------------------------------------------------------
    def test_i_transcript_normalizer_preserved(self):
        """Verify TranscriptNormalizer normalizes terms and preserves Hinglish."""
        self.assertEqual(TranscriptNormalizer.normalize("open vs code"), "open VS Code")
        self.assertEqual(TranscriptNormalizer.normalize("anti gravity"), "Antigravity")
        self.assertEqual(TranscriptNormalizer.normalize("zinpay"), "ZynPay")
        self.assertEqual(TranscriptNormalizer.detect_language("Chrome kholo"), "hinglish")

    # --------------------------------------------------------------------------
    # J. Specific technical terms in default vocabulary
    # --------------------------------------------------------------------------
    def test_j_specific_technical_terms(self):
        """Verify default terms include Charlie, Antigravity, Gemini, Groq, PyQt6, PostgreSQL, Lekhtra."""
        mgr = VocabularyContextManager()
        terms_lower = [t.lower() for t in mgr.get_terms()]

        for term in ["charlie", "antigravity", "gemini", "groq", "pyqt6", "postgresql", "lekhtra", "vs code"]:
            self.assertIn(term, terms_lower)


if __name__ == "__main__":
    unittest.main()
