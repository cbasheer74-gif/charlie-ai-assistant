import tempfile
import unittest
from pathlib import Path

import numpy as np

from core import task_history
from memory import learning_brain as brain
from memory import profile_manager as profiles


class TestLearningBrain(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.originals = {
            "MEMORY_DIR": profiles.MEMORY_DIR,
            "PROFILES_DIR": profiles.PROFILES_DIR,
            "REGISTRY_PATH": profiles.REGISTRY_PATH,
            "LEGACY_MEMORY_PATH": profiles.LEGACY_MEMORY_PATH,
            "LEGACY_DB_PATH": profiles.LEGACY_DB_PATH,
            "profile_name": profiles._profile_name_from_config,
            "notifier": profiles._change_notifier,
            "history": task_history._STORE,
            "voice": brain._recent_voice,
        }
        profiles.MEMORY_DIR = root / "memory"
        profiles.PROFILES_DIR = profiles.MEMORY_DIR / "profiles"
        profiles.REGISTRY_PATH = profiles.MEMORY_DIR / "profiles.json"
        profiles.LEGACY_MEMORY_PATH = profiles.MEMORY_DIR / "long_term.json"
        profiles.LEGACY_DB_PATH = profiles.MEMORY_DIR / "charlie_memory.db"
        profiles._profile_name_from_config = lambda: "Alice"
        profiles._change_notifier = None
        task_history._STORE = root / "history.json"
        brain._recent_voice = None
        self.root = root

    def tearDown(self):
        profiles.MEMORY_DIR = self.originals["MEMORY_DIR"]
        profiles.PROFILES_DIR = self.originals["PROFILES_DIR"]
        profiles.REGISTRY_PATH = self.originals["REGISTRY_PATH"]
        profiles.LEGACY_MEMORY_PATH = self.originals["LEGACY_MEMORY_PATH"]
        profiles.LEGACY_DB_PATH = self.originals["LEGACY_DB_PATH"]
        profiles._profile_name_from_config = self.originals["profile_name"]
        profiles._change_notifier = self.originals["notifier"]
        task_history._STORE = self.originals["history"]
        brain._recent_voice = self.originals["voice"]
        self.temp.cleanup()

    def test_emotion_relationship_knowledge_and_activity(self):
        mood = brain.observe_user_turn("I feel very stressed and overwhelmed today")
        self.assertEqual(mood["mood"], "stressed")

        person = brain.remember_relationship(
            "Riya", "sister", "Preparing for an interview", "2026-11-04",
            "Ask how the interview went")
        self.assertEqual(person["relation"], "sister")

        note = self.root / "project-notes.txt"
        note.write_text("Project Aurora launches Friday. The owner is Riya.", encoding="utf-8")
        doc = brain.add_knowledge(str(note), "Aurora notes")
        self.assertEqual(doc["title"], "Aurora notes")
        results = brain.search_knowledge("When does Aurora launch?")
        self.assertIn("Friday", results[0]["excerpt"])

        instruction = brain.start_activity("interview", "Python developer")
        self.assertIn("one question at a time", instruction)
        surprise = brain.start_activity("surprise")
        self.assertIn("[SURPRISE MODE]", surprise)
        self.assertIn("one consistent voice", surprise)
        context = brain.prompt_context()
        self.assertIn("stressed", context)
        self.assertIn("Riya", context)
        self.assertIn("Aurora notes", context)

    def test_routine_discovery_requires_repetition_and_approval(self):
        for _ in range(3):
            task_history.record("open_app", {"app": "Excel"}, "opened")
        routines = brain.discover_routines()
        self.assertEqual(len(routines), 1)
        self.assertEqual(routines[0]["repetitions"], 3)
        decision = brain.decide_routine(routines[0]["signature"], "approved", "Open Excel")
        self.assertEqual(decision["decision"], "approved")

    def test_learning_state_is_profile_private(self):
        brain.remember_relationship("Riya", "sister")
        brain.update_settings(vision_copilot="on")
        bob = profiles.create_profile("Bob")
        profiles.switch_profile(bob["id"])
        self.assertEqual(brain.list_relationships(), [])
        self.assertEqual(brain.load_brain()["settings"]["vision_copilot"], "ask")
        profiles.switch_profile("Alice")
        self.assertEqual(brain.list_relationships()[0]["name"], "Riya")

    def test_local_voice_matching_is_opt_in_and_convenience_only(self):
        rate = 16000
        t = np.arange(rate * 3, dtype=np.float32) / rate
        alice = ((0.65 * np.sin(2 * np.pi * 145 * t) +
                  0.25 * np.sin(2 * np.pi * 290 * t) +
                  0.10 * np.sin(2 * np.pi * 580 * t)) * 22000).astype(np.int16).tobytes()
        brain.set_recent_voice_sample(alice, rate)
        with self.assertRaises(ValueError):
            brain.enroll_recent_voice(False)
        enrolled = brain.enroll_recent_voice(True)
        self.assertEqual(enrolled["samples"], 1)

        bob = profiles.create_profile("Bob")
        profiles.switch_profile(bob["id"])
        bob_audio = ((0.7 * np.sin(2 * np.pi * 235 * t) +
                      0.3 * np.sin(2 * np.pi * 470 * t)) * 22000).astype(np.int16).tobytes()
        brain.set_recent_voice_sample(bob_audio, rate)
        brain.enroll_recent_voice(True)

        brain.set_recent_voice_sample(alice, rate)
        match = brain.identify_recent_voice()
        self.assertTrue(match["matched"])
        self.assertEqual(match["profile"], "Alice")
        self.assertEqual(match["security"], "convenience_only")

    def test_daily_intelligence_combines_private_context(self):
        brain.remember_relationship("Sam", "friend", follow_up="Ask about the new job")
        snapshot = brain.daily_intelligence("evening")
        self.assertEqual(snapshot["type"], "evening")
        self.assertEqual(snapshot["relationship_followups"][0]["name"], "Sam")


if __name__ == "__main__":
    unittest.main()
