import unittest
from unittest.mock import Mock, patch
from engine.context_builder import ContextBuilder
from engine.rag import LocalRAG
import actions.screen_explainer as screen_explainer


class BrainBoostTests(unittest.TestCase):
    def test_rag_search_context_formatting(self):
        rag = LocalRAG()
        mock_results = [
            {"filename": "guide.txt", "score": 0.88, "snippet": "Charlie setup instructions"},
            {"filename": "api.md", "score": 0.74, "snippet": "Endpoint details"},
        ]
        with patch.object(rag, "search", return_value=mock_results):
            ctx = rag.search_context("how to setup", top_k=2)
            self.assertIn("[RETRIEVED DOCUMENT KNOWLEDGE]", ctx)
            self.assertIn("guide.txt", ctx)
            self.assertIn("Charlie setup instructions", ctx)

    def test_context_builder_caching(self):
        mem = Mock()
        mem.get_project_context.return_value = {"facts": {"app": {"name": "Charlie"}}}
        mem.search.return_value = []
        mem.get_recent_task_context.return_value = None
        mem.get_procedure.return_value = None
        mem.find_error_solution.return_value = None

        cb = ContextBuilder(mem, cache_ttl_sec=30.0)
        c1 = cb.build_context("build feature", active_project="charlie")
        self.assertIn("ACTIVE PROJECT: CHARLIE", c1)
        self.assertEqual(mem.get_project_context.call_count, 1)

        # Second call within TTL hits cache
        c2 = cb.build_context("build feature", active_project="charlie")
        self.assertEqual(c1, c2)
        self.assertEqual(mem.get_project_context.call_count, 1)

        # Invalidate cache
        cb.invalidate_cache()
        c3 = cb.build_context("build feature", active_project="charlie")
        self.assertEqual(c1, c3)
        self.assertEqual(mem.get_project_context.call_count, 2)

    def test_screen_explainer_modes(self):
        with patch("engine.vision_ocr.extract_screen_text", return_value={"text": "def test():\n    pass", "width": 1920, "height": 1080}), \
             patch.object(screen_explainer, "_get_active_window_title", return_value="Visual Studio Code"):
            res_code = screen_explainer.execute(mode="code_diff")
            self.assertIn("Code & Diff Analysis", res_code)
            self.assertIn("Visual Studio Code", res_code)

            res_ui = screen_explainer.execute(mode="ui_inspect")
            self.assertIn("UI & Controls Inspection", res_ui)

            res_chart = screen_explainer.execute(mode="chart_explain")
            self.assertIn("Visual Data & Chart Explanation", res_chart)


if __name__ == '__main__':
    unittest.main()
