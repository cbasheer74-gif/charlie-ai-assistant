import tempfile
import unittest
from pathlib import Path
from engine.brain_booster import BrainResponseCache, get_boosted_parameters, compress_context_messages


class BrainBoosterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_booster.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cache_put_and_hit(self):
        cache = BrainResponseCache(max_ram_entries=4, db_path=self.db_path)
        cache.put("explain photosynthesis", "Plants convert light to chemical energy.", "learning")

        # RAM hit
        hit1 = cache.get("explain photosynthesis", "learning")
        self.assertEqual(hit1, "Plants convert light to chemical energy.")

        # Re-create cache from DB to verify SQLite persistence
        cache2 = BrainResponseCache(max_ram_entries=4, db_path=self.db_path)
        hit2 = cache2.get("explain photosynthesis", "learning")
        self.assertEqual(hit2, "Plants convert light to chemical energy.")

        stats = cache2.stats()
        self.assertEqual(stats["hits"], 1)

    def test_parameter_boost(self):
        coding_p = get_boosted_parameters("coding")
        self.assertEqual(coding_p["temperature"], 0.1)

        creative_p = get_boosted_parameters("creative")
        self.assertEqual(creative_p["temperature"], 0.7)

    def test_context_compressor(self):
        messages = [
            {"role": "user", "content": "A" * 3000},
            {"role": "assistant", "content": "B" * 3000},
            {"role": "user", "content": "recent question"},
            {"role": "assistant", "content": "recent answer"},
        ]
        compressed = compress_context_messages(messages, max_turns=4, max_content_len=500)
        self.assertEqual(len(compressed), 4)
        self.assertIn("context compressed", compressed[0]["content"])
        self.assertEqual(compressed[2]["content"], "recent question")


if __name__ == '__main__':
    unittest.main()
