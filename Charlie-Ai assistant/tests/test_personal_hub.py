import tempfile
import unittest
from pathlib import Path

from memory import personal_hub as hub
from memory import profile_manager as profiles
from memory.memory_manager import load_memory, remember, search_memory


class TestPersonalHub(unittest.TestCase):
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
        }
        profiles.MEMORY_DIR = root / "memory"
        profiles.PROFILES_DIR = profiles.MEMORY_DIR / "profiles"
        profiles.REGISTRY_PATH = profiles.MEMORY_DIR / "profiles.json"
        profiles.LEGACY_MEMORY_PATH = profiles.MEMORY_DIR / "long_term.json"
        profiles.LEGACY_DB_PATH = profiles.MEMORY_DIR / "charlie_memory.db"
        profiles._profile_name_from_config = lambda: "Alice"
        profiles._change_notifier = None

    def tearDown(self):
        profiles.MEMORY_DIR = self.originals["MEMORY_DIR"]
        profiles.PROFILES_DIR = self.originals["PROFILES_DIR"]
        profiles.REGISTRY_PATH = self.originals["REGISTRY_PATH"]
        profiles.LEGACY_MEMORY_PATH = self.originals["LEGACY_MEMORY_PATH"]
        profiles.LEGACY_DB_PATH = self.originals["LEGACY_DB_PATH"]
        profiles._profile_name_from_config = self.originals["profile_name"]
        profiles._change_notifier = self.originals["notifier"]
        self.temp.cleanup()

    def test_family_profiles_isolate_long_term_memory(self):
        self.assertEqual(profiles.active_profile()["name"], "Alice")
        remember("favorite_food", "pasta", "preferences")

        bob = profiles.create_profile("Bob")
        profiles.switch_profile(bob["id"])
        self.assertFalse(load_memory()["preferences"])
        self.assertTrue(search_memory("pasta").lower().startswith("nothing stored"))
        remember("favorite_food", "biryani", "preferences")

        profiles.switch_profile("Alice")
        alice = load_memory()["preferences"]["favorite_food"]["value"]
        self.assertEqual(alice, "pasta")
        self.assertIn("pasta", search_memory("pasta").lower())
        profiles.switch_profile("Bob")
        bob_value = load_memory()["preferences"]["favorite_food"]["value"]
        self.assertEqual(bob_value, "biryani")

    def test_goals_planner_learning_and_meeting(self):
        goal = hub.add_goal("Ship CHARLIE", "2026-10-01", "Finish companion mode")
        hub.update_goal(goal["id"], progress=40)
        task = hub.add_task("Review tests", "2026-09-21 09:00", "high")
        event = hub.add_event("Demo", "2026-09-22 14:00", "Office")
        course = hub.start_learning("English", "Interview fluency", "Hinglish")
        hub.update_learning(course["id"], progress=20, note="Practised introductions")
        meeting = hub.start_meeting("Product review")
        hub.record_conversation_turn("User", "We will launch on Friday.")
        stopped = hub.stop_meeting()
        hub.finalize_meeting(stopped["id"], "Launch planned for Friday.", ["Prepare release notes"])

        plan = hub.daily_plan()
        self.assertEqual(plan["goals"][0]["progress"], 40)
        self.assertEqual(plan["tasks"][0]["id"], task["id"])
        self.assertEqual(plan["events"][0]["id"], event["id"])
        saved_meeting = hub.load_hub()["meetings"][0]
        self.assertEqual(saved_meeting["status"], "completed")
        self.assertIn("launch on Friday", saved_meeting["transcript"][0]["text"])

    def test_companion_mode_and_prompt_context(self):
        hub.set_companion("listen", "daily")
        speech = hub.set_speech_preferences("companion", "slow", "hinglish", "none")
        self.assertEqual(speech["style"], "companion")
        self.assertEqual(speech["pace"], "slow")
        self.assertTrue(hub.checkin_due())
        hub.mark_checkin()
        self.assertFalse(hub.checkin_due())
        context = hub.prompt_context()
        self.assertIn("Active user profile: Alice", context)
        self.assertIn("Companion mode: listen", context)
        self.assertIn("Do not give advice", context)
        self.assertIn("Style: companion", context)
        self.assertIn("Language: hinglish", context)
        self.assertIn("Do not use names, honorifics, sir", context)

    def test_speech_preferences_are_profile_private(self):
        hub.set_speech_preferences("calm", "slow", "english", "name")
        bob = profiles.create_profile("Bob")
        profiles.switch_profile(bob["id"])
        self.assertEqual(hub.load_hub()["speech"]["style"], "warm")
        hub.set_speech_preferences("energetic", "fast", "hindi", "casual")
        profiles.switch_profile("Alice")
        speech = hub.load_hub()["speech"]
        self.assertEqual(speech["style"], "calm")
        self.assertEqual(speech["language"], "english")

    def test_profile_details_are_validated_and_saved_per_profile(self):
        updated = profiles.update_active_profile({
            "name": "Alice Chaudhary",
            "email": "Alice@Gmail.com",
            "phone": "+91 99999 00000",
            "occupation": "Designer",
            "location": "New Delhi, India",
            "language": "Hinglish",
            "timezone": "Asia/Kolkata",
        })
        self.assertEqual(updated["name"], "Alice Chaudhary")
        self.assertEqual(updated["email"], "alice@gmail.com")
        self.assertEqual(profiles.active_profile()["occupation"], "Designer")

        bob = profiles.create_profile("Bob")
        profiles.switch_profile(bob["id"])
        self.assertNotIn("email", profiles.active_profile())
        with self.assertRaises(ValueError):
            profiles.update_active_profile({"name": "Bob", "email": "invalid"})


if __name__ == "__main__":
    unittest.main()
