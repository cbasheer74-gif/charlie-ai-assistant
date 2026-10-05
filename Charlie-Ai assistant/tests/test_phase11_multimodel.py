"""
CHARLIE Phase 11: Multi-Model Intelligence Test Suite
Validates Golden Tests 113 to 131 and Section 132 Certification Matrix:
- Deterministic Bypass & Zero Token Waste
- Memory / Graph deterministic lookup
- Local vs Cloud selection based on Complexity
- Strict Privacy & Secret Redaction (HIGHLY_SENSITIVE -> LOCAL_ONLY)
- Offline AI Operation & graceful degradation
- Health tracking, Circuit Breaker & Fallback Chain
- Budget & Cost Cap Enforcement
- Semantic Cache & File-Hash Invalidation
- Context Compression & Token Accounting
- Smart Escalation & De-escalation
- Vision Routing & Capability Mismatch Defense
"""

import os
import shutil
import tempfile
import unittest

from engine.ai.core import ModelIntelligenceLayer
from engine.ai.models import (
    ComplexityLevel,
    DeploymentType,
    ModelCapability,
    ModelHealthState,
    NetworkState,
    PrivacyLevel,
    RoutingPolicy,
)


class TestPhase11MultiModel(unittest.TestCase):

    def setUp(self):
        self.ai = ModelIntelligenceLayer()

    # --- 113. Test Simple Request (Deterministic Bypass) ---
    def test_golden_113_simple_command_deterministic(self):
        res = self.ai.process_request("Open Notepad")
        self.assertTrue(res["success"])
        self.assertTrue(res["is_deterministic"])
        self.assertIsNone(res["model_used"])
        self.assertEqual(res["tokens_used"], 0)
        self.assertEqual(res["cost_usd"], 0.0)

    # --- 114. Test Memory Lookup ---
    def test_golden_114_memory_lookup_efficiency(self):
        profile, _ = self.ai.task_profiler.profile_task("What time is it or status")
        self.assertTrue(profile.requires_deterministic_only)

    # --- 115. Test Simple Summarization (Local Model) ---
    def test_golden_115_simple_summarization_local(self):
        res = self.ai.process_request("Summarize this short user note: Meeting tomorrow at 10am.")
        self.assertTrue(res["success"])
        self.assertFalse(res.get("is_deterministic", False))
        # Complexity is LOW -> should pick local model
        self.assertEqual(res["decision"].chosen_model.deployment_type, DeploymentType.LOCAL)
        self.assertEqual(res["cost_usd"], 0.0)

    # --- 116. Test Hard Coding (Cloud Reasoning/Coding Model) ---
    def test_golden_116_hard_coding_cloud(self):
        prompt = "Diagnose distributed race condition in backend concurrency deadlock"
        res = self.ai.process_request(prompt)
        self.assertTrue(res["success"])
        # High complexity coding -> Cloud Strong model
        chosen = res["decision"].chosen_model
        self.assertEqual(chosen.deployment_type, DeploymentType.CLOUD)
        self.assertIn(ModelCapability.CODING, chosen.capabilities)
        self.assertEqual(chosen.coding_strength, "EXPERT")

    # --- 117. Test Privacy (HIGHLY_SENSITIVE -> Local Only) ---
    def test_golden_117_privacy_highly_sensitive_local_only(self):
        # Explicit contract prompt
        prompt = "Summarize this private confidential contract and medical insurance policy."
        res = self.ai.process_request(prompt)
        self.assertTrue(res["success"])
        # Must enforce local-only
        self.assertTrue(res["decision"].local_only_enforced)
        self.assertEqual(res["decision"].chosen_model.deployment_type, DeploymentType.LOCAL)

    # --- 118. Test Secret Redaction (API Keys) ---
    def test_golden_118_secret_redaction(self):
        prompt = "Debug this script: api_key = 'sk-1234567890abcdef1234567890' with bearer token"
        profile, sanitized = self.ai.task_profiler.profile_task(prompt)
        self.assertEqual(profile.privacy_level, PrivacyLevel.SECRET)
        self.assertIn("[REDACTED_SECRET]", sanitized)
        self.assertNotIn("sk-1234567890abcdef1234567890", sanitized)

    # --- 119. Test Offline Execution (No Crash, Local Only) ---
    def test_golden_119_offline_execution(self):
        self.ai.offline_manager.set_network_state(NetworkState.OFFLINE)
        res = self.ai.process_request("Write a quick python helper function to reverse a string")
        self.assertTrue(res["success"])
        self.assertEqual(res["decision"].chosen_model.deployment_type, DeploymentType.LOCAL)
        self.assertTrue(res["decision"].local_only_enforced)

    # --- 120. Test Offline Current News Block ---
    def test_golden_120_offline_current_news_blocked(self):
        self.ai.offline_manager.set_network_state(NetworkState.OFFLINE)
        allowed, msg = self.ai.offline_manager.check_research_allowed(is_live_web_query=True)
        self.assertFalse(allowed)
        self.assertIn("unavailable in offline mode", msg)

    # --- 121. Test Provider Failure & Fallback ---
    def test_golden_121_provider_failure_and_fallback(self):
        # Simulate failure on cloud provider
        self.ai.cloud_provider.simulated_failure = True

        prompt = "Diagnose distributed race condition bug"
        res = self.ai.process_request(prompt)
        # Should fallback to local coder or another available model
        self.assertTrue(res["success"])
        self.assertNotEqual(res["model_used"], "cloud_strong_reasoning")

        # Verify cloud model marked degraded/unavailable
        health = self.ai.health_manager.get_health("cloud_strong_reasoning")
        self.assertIn(health, (ModelHealthState.DEGRADED, ModelHealthState.UNAVAILABLE))

    # --- 122. Test Capability Mismatch Defense ---
    def test_golden_122_capability_mismatch(self):
        # Force a request requiring audio capability which no model currently has
        profile, sanitized = self.ai.task_profiler.profile_task("Generate speech audio waveform")
        profile.required_capabilities = [ModelCapability.AUDIO]
        profile.requires_deterministic_only = False

        decision = self.ai.router.route(profile)
        self.assertIsNone(decision.chosen_model)
        self.assertIn("Capability mismatch", decision.reasoning)

    # --- 123. Test Budget Cap Enforcement ---
    def test_golden_123_budget_cap_enforcement(self):
        # Exhaust daily cost budget
        self.ai.cost_manager.daily_cost_cap_usd = 0.05
        self.ai.cost_manager.add_cost(0.06)
        self.assertTrue(self.ai.cost_manager.is_cost_cap_reached())

        # Now route a complex coding task
        prompt = "Fix complex memory leak in compiler engine"
        res = self.ai.process_request(prompt)
        self.assertTrue(res["success"])
        # Should fall back to local model to prevent cost overrun
        self.assertEqual(res["decision"].chosen_model.deployment_type, DeploymentType.LOCAL)

    # --- 124. Test Semantic Context Compression ---
    def test_golden_124_context_compression(self):
        giant_log = "\n".join([f"Line {i}: Info normal processing" for i in range(200)])
        giant_log += "\nERROR: Port 8080 already in use\nTraceback (most recent call last):\n  File app.py line 45"
        giant_log += "\n" + "\n".join([f"Line {i}: Additional log info" for i in range(200)])

        compressed = self.ai.context_compressor.compress_log_output(giant_log, max_lines=20)
        self.assertIn("ERROR: Port 8080 already in use", compressed)
        self.assertLess(len(compressed.splitlines()), 30)

    # --- 125. Test Semantic Cache Reuse ---
    def test_golden_125_semantic_cache_reuse(self):
        prompt = "Summarize the design pattern of ModelRouter"
        res1 = self.ai.process_request(prompt)
        self.assertTrue(res1["success"])
        self.assertFalse(res1.get("from_cache", False))

        # Second identical request
        res2 = self.ai.process_request(prompt)
        self.assertTrue(res2["success"])
        self.assertTrue(res2.get("from_cache", False))
        self.assertEqual(res2["model_used"], "cache")

    # --- 126. Test Cache Invalidation on File Modification ---
    def test_golden_126_cache_invalidation_on_file_change(self):
        files_v1 = {"main.py": "def add(a, b): return a + b"}
        prompt = "Review math helper functions"

        res1 = self.ai.process_request(prompt, file_contents=files_v1)
        self.assertTrue(res1["success"])
        self.assertFalse(res1.get("from_cache", False))

        # Modifying file invalidates cache
        files_v2 = {"main.py": "def add(a, b): return a * b  # changed logic"}
        res2 = self.ai.process_request(prompt, file_contents=files_v2)
        self.assertTrue(res2["success"])
        self.assertFalse(res2.get("from_cache", False))

    # --- 127. Test Smart Escalation ---
    def test_golden_127_smart_escalation(self):
        # Simulate local model failing coding task repeatedly
        self.ai.performance_tracker.record_run("local_coder_7b", "CODING_DEBUG", passed=False, latency_seconds=0.2)
        self.ai.performance_tracker.record_run("local_coder_7b", "CODING_DEBUG", passed=False, latency_seconds=0.2)

        should_esc = self.ai.performance_tracker.should_escalate_model("local_coder_7b", "CODING_DEBUG")
        self.assertTrue(should_esc)

    # --- 128. Test De-escalation (Planner / Executor Split) ---
    def test_golden_128_planner_executor_deescalation(self):
        # Planner task (high reasoning)
        plan_profile, _ = self.ai.task_profiler.profile_task("Architect financial reconciliation engine")
        plan_dec = self.ai.router.route(plan_profile)
        self.assertEqual(plan_dec.chosen_model.deployment_type, DeploymentType.CLOUD)

        # Implementation step (trivial formatting / simple task)
        exec_profile, _ = self.ai.task_profiler.profile_task("Add a docstring to this utility method")
        exec_dec = self.ai.router.route(exec_profile)
        self.assertEqual(exec_dec.chosen_model.deployment_type, DeploymentType.LOCAL)

    # --- 129. Test Vision Routing & Privacy ---
    def test_golden_129_vision_routing(self):
        route_text_ocr = self.ai.vision_router.route_vision_request(has_complex_layout=False)
        self.assertEqual(route_text_ocr, "LOCAL_OCR")

        route_complex = self.ai.vision_router.route_vision_request(has_complex_layout=True)
        self.assertEqual(route_complex, "CLOUD_VISION")

    # --- 130. Test Model Health & Circuit Breaker ---
    def test_golden_130_model_health_circuit_breaker(self):
        m_id = "test_model_cb"
        self.ai.health_manager.record_failure(m_id, "500 Internal Error")
        self.ai.health_manager.record_failure(m_id, "500 Internal Error")
        self.assertEqual(self.ai.health_manager.get_health(m_id), ModelHealthState.DEGRADED)

        # Third failure trips circuit
        self.ai.health_manager.record_failure(m_id, "500 Internal Error")
        self.assertEqual(self.ai.health_manager.get_health(m_id), ModelHealthState.UNAVAILABLE)

    # --- 131. Test Golden Benchmark Evaluation ---
    def test_golden_131_benchmark_evaluation(self):
        self.ai.performance_tracker.record_run("local_fast_small", "GENERAL_QUERY", passed=True, latency_seconds=0.04)
        rate = self.ai.performance_tracker.get_success_rate("local_fast_small", "GENERAL_QUERY")
        self.assertEqual(rate, 1.0)


if __name__ == "__main__":
    unittest.main()
