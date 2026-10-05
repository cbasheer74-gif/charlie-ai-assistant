import unittest
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.speech_booster import SpeechAccelerator, get_optimized_stt_settings
from core.live_vision_stream import LiveVisionStreamer, get_vision_streamer
from core.semantic_rag import SemanticRAGMemory
from actions.desktop_macros import DesktopMacroEngine
from engine.voice.persona_engine import PersonaManager, PERSONAS


class TestAppBoosters(unittest.TestCase):
    def test_01_speech_accelerator(self):
        acc = SpeechAccelerator.get_instance()
        env = acc.optimize_environment()
        self.assertIn("device", env)
        self.assertIn("compute_type", env)
        kwargs = get_optimized_stt_settings()
        self.assertEqual(kwargs["beam_size"], 1)
        self.assertTrue(kwargs["vad_filter"])

    def test_02_live_vision_streamer(self):
        streamer = get_vision_streamer()
        streamer.set_source("screen")
        self.assertEqual(streamer._source, "screen")
        streamer.set_source("camera")
        self.assertEqual(streamer._source, "camera")

    def test_03_semantic_rag(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            test_db = Path(td) / "test_rag.db"
            rag = SemanticRAGMemory(db_path=test_db)
            rag.index_document("doc1", "Python Guide", "Python is an interpreted programming language.", "tech")
            rag.index_document("doc2", "Meeting Notes", "Discussed roadmap for Charlie AI Assistant.", "work")

            hits = rag.search("Charlie roadmap")
            self.assertTrue(any("Charlie" in h.content for h in hits))

            ctx = rag.build_rag_context("Python language")
            self.assertIn("Python Guide", ctx)

    def test_04_desktop_macro_engine(self):
        res = DesktopMacroEngine.setup_workspace("focus")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["mode"], "focus")

    def test_05_persona_engine(self):
        mgr = PersonaManager()
        self.assertEqual(mgr.active_persona.id, "charlie_core")

        # Switch to Jarvis
        p = mgr.set_persona("jarvis")
        self.assertIsNotNone(p)
        self.assertEqual(p.id, "jarvis")
        self.assertIn("J.A.R.V.I.S.", p.display_name)
        self.assertIn("British", p.accent)

        voice = mgr.get_voice(is_female=False)
        self.assertEqual(voice, "en-GB-RyanNeural")

        prompt = mgr.get_system_prompt_directive()
        self.assertIn("British precision", prompt)


if __name__ == "__main__":
    unittest.main()
