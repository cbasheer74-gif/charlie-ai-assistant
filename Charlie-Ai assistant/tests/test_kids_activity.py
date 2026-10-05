"""tests/test_kids_activity.py — Comprehensive tests for Kids Activity Suite."""

import tempfile
import unittest
from pathlib import Path

from actions.kids_activity import kids_activity
from memory import kids_activity as kids
from memory import profile_manager as profiles


class KidsActivityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.orig_store_path = kids._store_path
        kids._store_path = lambda: self.temp_path / "kids_activity.json"

    def tearDown(self):
        kids._store_path = self.orig_store_path
        self.temp_dir.cleanup()

    def test_math_quest_workflow(self):
        prob = kids.generate_math_problem("easy")
        self.assertIn("+", prob["question"])

        # Incorrect answer
        inc = kids.check_math_answer(9999)
        self.assertEqual(inc["status"], "incorrect")

        # Correct answer
        parts = prob["question"].split("+")
        ans = int(parts[0].strip()) + int(parts[1].strip())
        res = kids.check_math_answer(ans)
        self.assertEqual(res["status"], "correct")
        self.assertEqual(res["streak"], 1)
        self.assertEqual(res["total_stars"], 10)

    def test_bedtime_story_branching(self):
        story = kids.start_story("ocean")
        self.assertEqual(story["theme"], "ocean")
        self.assertEqual(story["chapter"], 1)

        nxt = kids.next_chapter("Barnaby visits the coral castle")
        self.assertEqual(nxt["chapter"], 2)
        self.assertIn("Barnaby visits", nxt["instruction"])

    def test_voice_drawing_coach(self):
        coach = kids.start_drawing("cat")
        self.assertEqual(coach["step"], 1)
        self.assertEqual(coach["total_steps"], 4)

        # Advance through steps
        s2 = kids.next_drawing_step()
        self.assertEqual(s2["step"], 2)
        s3 = kids.next_drawing_step()
        self.assertEqual(s3["step"], 3)
        s4 = kids.next_drawing_step()
        self.assertEqual(s4["step"], 4)

        # Completion awards stars
        done = kids.next_drawing_step()
        self.assertTrue(done["finished"])
        self.assertIn("cat", done["instruction"])

    def test_parental_guard_and_pin(self):
        # Bad PIN
        bad = kids.update_guard(True, "0000")
        self.assertEqual(bad["status"], "error")

        # Correct PIN
        ok = kids.update_guard(True, "1234", limit_minutes=45)
        self.assertEqual(ok["status"], "success")
        self.assertTrue(ok["guard_enabled"])
        self.assertEqual(ok["daily_limit_minutes"], 45)

    def test_action_tool_integration(self):
        # 1. Story
        s_msg = kids_activity({"action": "story", "subaction": "start", "topic": "space"})
        self.assertIn("Bedtime Story", s_msg)

        # 2. Math
        m_msg = kids_activity({"action": "math", "subaction": "question", "difficulty": "easy"})
        self.assertIn("Math Quest", m_msg)

        # 3. Draw
        d_msg = kids_activity({"action": "draw", "subaction": "start", "topic": "rocket"})
        self.assertIn("Drawing Coach", d_msg)

        # 4. Status
        st_msg = kids_activity({"action": "status"})
        self.assertIn("Kids Corner Progress", st_msg)


if __name__ == "__main__":
    unittest.main()
