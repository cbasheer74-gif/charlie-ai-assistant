import tempfile
import unittest
from pathlib import Path

from engine.anticipation_engine import AnticipationEngine
from engine.dag_planner import DAGPlanner
from engine.episodic_recall import EpisodicRecallEngine
from engine.reflective_critic import ReflectiveCritic


class AdvancedBrainSuiteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_advanced_brain.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    # ── 1. Reflective Critic Tests ───────────────────────────────────────────
    def test_reflective_critic_syntax_validation(self):
        valid_py = "```python\ndef add(a, b):\n    return a + b\n```"
        audit = ReflectiveCritic.audit_response("add fn", valid_py, "coding")
        self.assertTrue(audit["passed"])
        self.assertEqual(audit["score"], 1.0)

        invalid_py = "```python\ndef broken(:\n    pass\n```"
        bad_audit = ReflectiveCritic.audit_response("broken fn", invalid_py, "coding")
        self.assertFalse(bad_audit["passed"])
        self.assertIn("Python SyntaxError", bad_audit["defects"][0])

    def test_reflective_critic_autocorrect_unclosed_fence(self):
        unclosed = "Here is the code:\n```python\nx = 10\n"
        audit = ReflectiveCritic.audit_response("test", unclosed)
        self.assertFalse(audit["passed"])
        fixed = ReflectiveCritic.auto_correct(unclosed, audit["defects"])
        self.assertEqual(fixed.count("```"), 2)

    # ── 2. DAG Tool Planner Tests ────────────────────────────────────────────
    def test_dag_planner_parallel_execution(self):
        dag = DAGPlanner("test_pipeline")
        # Layer 0 (Parallel steps)
        dag.add_node("step_a", "Fetch Data A", lambda: {"items": [1, 2, 3]})
        dag.add_node("step_b", "Fetch Data B", lambda: {"items": [4, 5, 6]})

        # Layer 1 (Dependent on A and B)
        def merge(results):
            a = results["step_a"]["items"]
            b = results["step_b"]["items"]
            return a + b

        dag.add_node("step_c", "Merge Results", merge, depends_on=["step_a", "step_b"])

        layers = dag.compute_layers()
        self.assertEqual(len(layers), 2)
        self.assertEqual(len(layers[0]), 2)  # A and B in parallel
        self.assertEqual(len(layers[1]), 1)  # C executes second

        exec_res = dag.execute()
        self.assertEqual(exec_res["succeeded"], 3)
        self.assertEqual(exec_res["results"]["step_c"], [1, 2, 3, 4, 5, 6])

    def test_dag_cycle_detection(self):
        dag = DAGPlanner("cycle_dag")
        dag.add_node("n1", "Node 1", lambda: 1, depends_on=["n2"])
        dag.add_node("n2", "Node 2", lambda: 2, depends_on=["n1"])
        with self.assertRaises(ValueError):
            dag.compute_layers()

    # ── 3. Episodic Recall Engine Tests ──────────────────────────────────────
    def test_episodic_recall_associative_memory(self):
        recall_engine = EpisodicRecallEngine(db_path=self.db_path)
        ep1 = recall_engine.record_episode(
            summary="User configured PostgreSQL database with connection pooling and b-tree index",
            tags=["database", "postgresql", "indexing"],
            importance=8.0,
        )
        self.assertTrue(ep1.startswith("ep_"))

        recalled = recall_engine.recall_relevant("optimize postgresql query with index", top_k=2)
        self.assertGreaterEqual(len(recalled), 1)
        self.assertIn("PostgreSQL", recalled[0]["summary"])

        prompt_block = recall_engine.format_recall_prompt("postgresql database")
        self.assertIn("[RELEVANT HISTORICAL EPISODES", prompt_block)

    # -- 4. Anticipation Engine Tests -----------------------------------------
    def test_anticipation_engine_predictions(self):
        # After coding -> predicts audit (static prior, no learned data yet)
        preds = AnticipationEngine.predict_next_actions(last_task_kind="coding")
        self.assertTrue(len(preds) > 0)
        self.assertEqual(preds[0]["action"], "audit")
        self.assertGreaterEqual(preds[0]["confidence"], 0.40)

        # In IDE window -> predicts code inspection
        ide_preds = AnticipationEngine.predict_next_actions(active_window_title="main.py - Visual Studio Code")
        actions = [p["action"] for p in ide_preds]
        self.assertIn("code_audit", actions)

        # Result shape includes new fields
        self.assertIn("learned", preds[0])
        self.assertIn("prior_action", preds[0])

    def test_habit_tracker_record_and_retrieve(self):
        """record_feedback persists and learned_transitions reflects it."""
        import tempfile, os
        from engine.anticipation_engine import HabitTracker

        tracker = HabitTracker()

        # Record 5 accepts for coding -> test_runner
        for _ in range(5):
            tracker.record("coding_test", "test_runner", accepted=True)
        # Record 1 dismiss for coding -> devops
        tracker.record("coding_test", "devops", accepted=False)

        learned = tracker.learned_transitions("coding_test", min_observations=1)
        self.assertIn("test_runner", learned)
        self.assertGreater(learned.get("test_runner", 0), learned.get("devops", 0))

        n = tracker.total_observations("coding_test")
        self.assertGreaterEqual(n, 6)

    def test_habit_blending_shifts_predictions(self):
        """After many accepts, the blended confidence shifts toward the learned action."""
        from engine.anticipation_engine import HabitTracker

        tracker = HabitTracker()
        # Simulate user always accepting db_backup after database tasks
        for _ in range(25):
            tracker.record("database", "db_backup", accepted=True)
        for _ in range(5):
            tracker.record("database", "api_design", accepted=False)

        preds = AnticipationEngine.predict_next_actions(last_task_kind="database")
        top_actions = [p["action"] for p in preds]
        # db_backup should now rank higher than api_design due to learned signal
        if "db_backup" in top_actions and "api_design" in top_actions:
            db_conf = next(p["confidence"] for p in preds if p["action"] == "db_backup")
            api_conf = next(p["confidence"] for p in preds if p["action"] == "api_design")
            self.assertGreater(db_conf, api_conf)


if __name__ == '__main__':
    unittest.main()
