import tempfile
import unittest
from pathlib import Path

from memory import game_room as games
from memory import learning_brain as brain
from memory import profile_manager as profiles


class TestGameRoom(unittest.TestCase):
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
        for key, value in self.originals.items():
            if key in {"profile_name", "notifier"}:
                continue
            setattr(profiles, key, value)
        profiles._profile_name_from_config = self.originals["profile_name"]
        profiles._change_notifier = self.originals["notifier"]
        self.temp.cleanup()

    def test_all_ten_games_start_in_requested_order(self):
        self.assertEqual(len(games.GAME_ORDER), 10)
        for game in games.GAME_ORDER:
            result = games.start_game(game, theme="space")
            self.assertEqual(result["session"]["game"], game)
            self.assertIn("wait", result["instruction"].lower())
            games.finish_game()
        status = games.status()
        self.assertEqual(status["stats"]["plays"], 10)
        self.assertEqual(len(status["stats"]["games"]), 10)
        self.assertIn("Game Room Master", [x["title"] for x in status["achievements"]])

    def test_scoring_streak_memory_levels_and_saved_context(self):
        started = games.start_game("memory_challenge")
        first_sequence = started["session"]["sequence"]
        turn = games.record_turn("correct")
        self.assertEqual(turn["score"], 10)
        self.assertGreater(len(turn["next_sequence"]), len(first_sequence))
        games.record_turn("correct")
        games.record_turn("correct")
        self.assertEqual(games.status()["stats"]["best_streak"], 3)
        self.assertIn("Active Game Room session", brain.prompt_context())

    def test_family_scores_leaderboard_and_profile_privacy(self):
        bob = profiles.create_profile("Bob")
        games.start_game("family_game_night", participants=["Alice", "Bob"])
        turn = games.record_turn("correct", participant="Alice")
        self.assertEqual(turn["family_scores"]["Alice"], 10)
        games.finish_game("win")
        board = games.leaderboard()
        self.assertEqual(board[0]["profile"], "Alice")
        profiles.switch_profile(bob["id"])
        self.assertEqual(games.status()["stats"]["plays"], 0)

    def test_daily_and_mood_games(self):
        brain.observe_user_turn("I feel stressed and overwhelmed")
        mood = games.start_game("mood_games")["session"]["recommendation"]
        self.assertEqual(mood["observed_cue"], "stressed")
        games.finish_game()
        daily = games.start_game("daily_brain_challenge")["session"]
        self.assertIn("challenge", daily)
        games.finish_game("success")
        self.assertEqual(games.status()["stats"]["daily_streak"], 1)


if __name__ == "__main__":
    unittest.main()
