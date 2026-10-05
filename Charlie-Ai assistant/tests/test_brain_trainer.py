import tempfile
import unittest
from pathlib import Path
from engine.brain_trainer import BrainTrainer, train_charlie_brain_and_memory
from engine.db import get_db, init_db


class BrainTrainerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_charlie_memory.db"
        init_db(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_complete_brain_training_and_idempotence(self):
        trainer = BrainTrainer(db_path=self.db_path)

        # First training run
        results1 = trainer.train_all()
        self.assertGreaterEqual(results1["facts_trained"], 18)
        self.assertGreaterEqual(results1["playbooks_trained"], 6)
        self.assertGreaterEqual(results1["recoveries_trained"], 4)
        self.assertGreaterEqual(results1["kg_entities_trained"], 18)

        # Verify database contents
        with get_db(self.db_path) as conn:
            fact_count = conn.execute("SELECT COUNT(*) as c FROM user_memories WHERE is_active = 1").fetchone()["c"]
            self.assertGreaterEqual(fact_count, 18)

            playbook = conn.execute("SELECT * FROM procedural_memories WHERE name = 'camera_ocr_inspection'").fetchone()
            self.assertIsNotNone(playbook)
            self.assertIn("Laplacian focus", playbook["steps_json"])

            error_rec = conn.execute("SELECT * FROM error_memories WHERE error_signature = 'CameraDeviceBusyOrUnavailable'").fetchone()
            self.assertIsNotNone(error_rec)
            self.assertIn("Settings -> Privacy -> Camera", error_rec["successful_fix"])

        # Second training run (verify idempotence — no duplicates)
        results2 = trainer.train_all()
        with get_db(self.db_path) as conn:
            fact_count_after = conn.execute("SELECT COUNT(*) as c FROM user_memories WHERE is_active = 1").fetchone()["c"]
            self.assertEqual(fact_count, fact_count_after)

            pb_count = conn.execute("SELECT COUNT(*) as c FROM procedural_memories").fetchone()["c"]
            self.assertEqual(results2["playbooks_trained"], pb_count)


if __name__ == '__main__':
    unittest.main()
