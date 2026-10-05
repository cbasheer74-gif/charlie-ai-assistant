"""tests/test_rag.py — Comprehensive tests for Local RAG doc-search."""

import tempfile
import unittest
from pathlib import Path

from actions.rag_search import rag_search
from engine.rag import LocalRAG, _chunk_text, _extract_text_from_file


class LocalRAGTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "test_rag.sqlite3"
        self.rag = LocalRAG(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_chunking_short_and_long_text(self):
        short = "Short text under limit."
        chunks = _chunk_text(short, chunk_size=100)
        self.assertEqual(chunks, [short])

        long_text = ("Sentence one. " * 30) + "\n\n" + ("Paragraph two content. " * 30)
        long_chunks = _chunk_text(long_text, chunk_size=200, overlap=30)
        self.assertGreater(len(long_chunks), 1)

    def test_index_and_search_text_file(self):
        doc = self.temp_path / "architecture.md"
        doc.write_text(
            "# System Architecture\n\n"
            "CHARLIE utilizes a local microkernel engine with offline speech and digital human articulation.\n\n"
            "The neural network coordinates visemes and facial rigs in real-time.\n",
            encoding="utf-8",
        )

        res = self.rag.index_file(doc)
        self.assertEqual(res["status"], "indexed")
        self.assertGreater(res["chunks"], 0)

        # Re-indexing unchanged file is up_to_date
        res2 = self.rag.index_file(doc)
        self.assertEqual(res2["status"], "up_to_date")

        # Search for keyword
        results = self.rag.search("visemes facial rigs")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["filename"], "architecture.md")
        self.assertIn("visemes", results[0]["snippet"].lower())

    def test_directory_indexing(self):
        sub = self.temp_path / "docs"
        sub.mkdir()
        (sub / "doc1.txt").write_text("Quantum computing leverages qubits and superposition.", encoding="utf-8")
        (sub / "doc2.py").write_text("def calculate_orbit(): return 'orbital trajectory velocity'", encoding="utf-8")

        res = self.rag.index_directory(sub)
        self.assertEqual(res["indexed_files"], 2)
        self.assertGreater(res["total_new_chunks"], 1)

        # Search python code snippet
        code_res = self.rag.search("orbital trajectory")
        self.assertGreater(len(code_res), 0)
        self.assertEqual(code_res[0]["filename"], "doc2.py")

        # Status inspection
        status = self.rag.get_status()
        self.assertEqual(status["total_documents"], 2)
        self.assertGreater(status["total_chunks"], 1)

    def test_clear_database(self):
        doc = self.temp_path / "temp.txt"
        doc.write_text("Secret cryptographic encryption key details.", encoding="utf-8")
        self.rag.index_file(doc)
        self.assertGreater(len(self.rag.search("cryptographic")), 0)

        self.rag.clear()
        self.assertEqual(len(self.rag.search("cryptographic")), 0)
        status = self.rag.get_status()
        self.assertEqual(status["total_documents"], 0)


class RAGActionToolTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.test_file = self.temp_path / "project_notes.txt"
        self.test_file.write_text("Apollo 11 landed on the lunar surface on July 20, 1969.", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_tool_lifecycle(self):
        # 1. Index
        idx_msg = rag_search({"action": "index", "path": str(self.test_file)})
        self.assertIn("indexed", idx_msg.lower())

        # 2. Search
        search_msg = rag_search({"action": "search", "query": "Apollo 11 lunar landing", "limit": 2})
        self.assertIn("Apollo 11", search_msg)

        # 3. Status
        status_msg = rag_search({"action": "status"})
        self.assertIn("Local RAG Status", status_msg)

        # 4. Clear
        clear_msg = rag_search({"action": "clear"})
        self.assertIn("cleared successfully", clear_msg)


if __name__ == "__main__":
    unittest.main()
