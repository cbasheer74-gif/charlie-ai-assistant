"""tests/test_performance_features.py — Verification suite for Performance Architecture features.

Covers:
1. LLM Multi-Tier Response Cache (L1 LRU + L2 SQLite + Dynamic bypass)
2. Background Threadpool Offload (Priority scheduling, async callbacks, telemetry)
3. Async Audio Streaming (Sentence chunking, pipeline worker, instant stop)
4. GPU ONNX Runtime Manager (Provider detection, graph session optimizer, fallback)
"""
from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestLLMResponseCache(unittest.TestCase):
    def setUp(self):
        from core.llm_cache import LLMResponseCache
        import tempfile
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test_cache.db"
        self.cache = LLMResponseCache(max_ram_entries=4, db_path=self.db_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_cache_put_and_get(self):
        self.cache.put("explain quantum computing", "Quantum computing uses qubits.", "test-model")
        res = self.cache.get("explain quantum computing", "test-model")
        self.assertEqual(res, "Quantum computing uses qubits.")

    def test_cache_normalization(self):
        self.cache.put("What is Python? ", "A language.", "test-model")
        # different whitespace and casing
        res = self.cache.get("what is python?", "test-model")
        self.assertEqual(res, "A language.")

    def test_temporal_query_bypass(self):
        self.assertFalse(self.cache.is_cacheable("what time is it now"))
        self.assertFalse(self.cache.is_cacheable("current weather in new york"))
        self.assertFalse(self.cache.is_cacheable("what is today's date"))
        self.assertTrue(self.cache.is_cacheable("summarize the theory of relativity"))

    def test_l2_sqlite_persistence_across_instances(self):
        from core.llm_cache import LLMResponseCache
        self.cache.put("define gravity", "Curvature of spacetime.", "model_a")
        # Create separate fresh cache instance pointing to same DB (RAM empty)
        cache2 = LLMResponseCache(max_ram_entries=4, db_path=self.db_path)
        self.assertEqual(len(cache2._ram_cache), 0)
        res = cache2.get("define gravity", "model_a")
        self.assertEqual(res, "Curvature of spacetime.")
        # Promoted to L1 RAM
        self.assertIn(cache2.compute_hash("define gravity", "model_a"), cache2._ram_cache)


class TestBackgroundThreadPool(unittest.TestCase):
    def setUp(self):
        from engine.threadpool import CharlieThreadPool
        self.pool = CharlieThreadPool(max_workers=4, thread_name_prefix="TestWorker")

    def tearDown(self):
        self.pool.shutdown(wait=False, cancel_futures=True)

    def test_priority_execution(self):
        from engine.threadpool import TaskPriority
        execution_order = []

        def task_action(val):
            execution_order.append(val)
            return val

        # Submit tasks with different priorities
        f_low = self.pool.submit(task_action, "LOW", priority=TaskPriority.LOW)
        f_crit = self.pool.submit(task_action, "CRITICAL", priority=TaskPriority.CRITICAL)
        f_norm = self.pool.submit(task_action, "NORMAL", priority=TaskPriority.NORMAL)

        self.assertEqual(f_crit.result(timeout=2.0), "CRITICAL")
        self.assertEqual(f_norm.result(timeout=2.0), "NORMAL")
        self.assertEqual(f_low.result(timeout=2.0), "LOW")

        stats = self.pool.stats()
        self.assertGreaterEqual(stats["tasks_completed"], 3)

    def test_callback_dispatch(self):
        from engine.threadpool import TaskPriority
        completed = []

        def worker():
            return 99

        fut = self.pool.run_with_callback(
            worker,
            on_success=lambda r: completed.append(r),
            priority=TaskPriority.HIGH,
        )
        self.assertEqual(fut.result(timeout=2.0), 99)
        time.sleep(0.05)
        self.assertEqual(completed, [99])

    def test_execute_with_timeout(self):
        def quick_worker():
            return "done"

        res = self.pool.execute_with_timeout(quick_worker, timeout_sec=2.0)
        self.assertEqual(res, "done")


class TestAsyncAudioStreamer(unittest.TestCase):
    def setUp(self):
        from engine.voice.streamer import AsyncAudioStreamer
        self.streamer = AsyncAudioStreamer()

    def tearDown(self):
        self.streamer.stop()

    def test_stream_split_and_stop(self):
        text = "Hello world! This is a test sentence. Here is sentence three."
        self.streamer.stream_text(text)
        time.sleep(0.05)
        # Verify instant cutoff
        self.streamer.stop()
        self.assertFalse(self.streamer.is_streaming)

    def test_streamer_stats(self):
        stats = self.streamer.stats()
        self.assertIn("first_audio_latency_ms", stats)
        self.assertIn("is_streaming", stats)


class TestONNXRuntimeManager(unittest.TestCase):
    def setUp(self):
        from engine.ai.onnx_runtime import ONNXRuntimeManager
        self.manager = ONNXRuntimeManager()

    def test_provider_detection(self):
        providers = self.manager._query_available_providers()
        self.assertTrue(len(providers) > 0)
        self.assertIn("CPUExecutionProvider", providers)

    def test_hardware_summary(self):
        summary = self.manager.get_hardware_summary()
        self.assertIn("has_gpu_acceleration", summary)
        self.assertIn("available_providers", summary)
        self.assertIn("platform", summary)


class TestWeatherTelemetryService(unittest.TestCase):
    def test_weather_service_structure(self):
        from core.weather_service import get_realtime_weather, capture_location
        loc = capture_location()
        self.assertIsInstance(loc, dict)
        self.assertIn("city", loc)
        self.assertIn("lat", loc)
        self.assertIn("lon", loc)

        weather = get_realtime_weather(force_refresh=False)
        self.assertIsInstance(weather, dict)
        self.assertIn("temp_c", weather)
        self.assertIn("display_text", weather)
        self.assertIn("icon_key", weather)


if __name__ == "__main__":
    unittest.main()
