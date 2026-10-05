"""tests/test_intelligence_engine.py — Comprehensive Test Suite for CHARLIE Engine.

Validates all 10 core engine systems and executes Golden Scenarios A through G.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.agents.antigravity_agent import AntigravityAgent
from engine.agents.coding_agent import CodingAgent
from engine.agents.spreadsheet_agent import SpreadsheetAgent
from engine.agents.video_agent import VideoAgent
from engine.context_builder import ContextBuilder
from engine.db import get_db, init_db
from engine.error_recovery import ErrorRecoveryEngine
from engine.memory_manager import MemoryManager
from engine.permissions import PermissionManager, RiskLevel
from engine.rollback import RollbackManager
from engine.router import AgentRouter
from engine.task_planner import TaskPlanner
from engine.tool_registry import ToolRegistry
from engine.verification import VerificationEngine


class TestCharlieIntelligenceEngine(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="charlie_test_"))
        self.db_path = self.test_dir / "test_memory.db"
        self.memory = MemoryManager(db_path=self.db_path)
        self.permissions = PermissionManager(ask_system_changes=True)
        self.verification = VerificationEngine()
        self.recovery = ErrorRecoveryEngine(self.memory)
        self.rollback = RollbackManager(backup_dir=self.test_dir / "backups")
        self.planner = TaskPlanner(self.memory)
        self.context_builder = ContextBuilder(self.memory)
        self.router = AgentRouter(
            self.memory, self.planner, self.permissions,
            self.verification, self.recovery, self.rollback,
        )
        self.registry = ToolRegistry(self.permissions, self.verification)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # ── 1. Database & Memory CRUD ────────────────────────────────────────────

    def test_memory_crud_and_deduplication(self):
        # Insert
        r1 = self.memory.remember("preferences", "Prefers dark mode in code editor")
        self.assertEqual(r1["action"], "created")

        # Duplicate semantic insert should update rather than duplicate
        r2 = self.memory.remember("preferences", "Prefers dark mode in code editor")
        self.assertEqual(r2["action"], "updated")

        # Recall
        results = self.memory.search("dark mode")
        self.assertTrue(len(results) >= 1)
        self.assertIn("dark mode", results[0]["content"].lower())

    def test_memory_superseding(self):
        r = self.memory.remember("preferences", "Primary language: English")
        mem_id = r["id"]

        # Supersede with new preference
        ok = self.memory.supersede_memory(mem_id, "Primary language: Hindi")
        self.assertTrue(ok)

        # Older memory is deactivated
        with get_db(self.db_path) as conn:
            old = conn.execute("SELECT is_active FROM user_memories WHERE id = ?;", (mem_id,)).fetchone()
            self.assertEqual(old["is_active"], 0)

    # ── 2. Project Isolation ─────────────────────────────────────────────────

    def test_project_memory_isolation(self):
        self.memory.set_project_memory("ZynPay", "config", "port", "3008")
        self.memory.set_project_memory("EchoVision", "config", "port", "8080")

        ctx_zyn = self.memory.get_project_context("ZynPay")
        ctx_echo = self.memory.get_project_context("EchoVision")

        self.assertEqual(ctx_zyn["facts"]["config"]["port"], "3008")
        self.assertEqual(ctx_echo["facts"]["config"]["port"], "8080")
        self.assertNotEqual(ctx_zyn["facts"]["config"]["port"], ctx_echo["facts"]["config"]["port"])

    # ── 3. Task Planning & Checkpointing ─────────────────────────────────────

    def test_task_planning_and_advancement(self):
        plan = self.planner.plan_goal("Create YouTube Short video", project_name="ZynPay")
        self.assertEqual(plan.status, "RUNNING")
        self.assertTrue(len(plan.steps) >= 4)

        # Advance step 1
        step2 = self.planner.advance_step(evidence="Script created")
        self.assertIsNotNone(step2)
        self.assertEqual(step2.index, 1)

    # ── 4. Permission & Dangerous Command Blocking ───────────────────────────

    def test_command_safety_filter(self):
        # High impact dangerous commands
        risk1, _ = self.permissions.classify_command("rm -rf /")
        self.assertEqual(risk1, RiskLevel.HIGH_IMPACT)

        risk2, _ = self.permissions.classify_command("del /s C:\\important")
        self.assertEqual(risk2, RiskLevel.HIGH_IMPACT)

        risk3, _ = self.permissions.classify_command("git reset --hard HEAD~1")
        self.assertEqual(risk3, RiskLevel.HIGH_IMPACT)

        # Safe inspection
        risk4, _ = self.permissions.classify_command("git status")
        self.assertEqual(risk4, RiskLevel.READ_ONLY)

        # System change
        risk5, _ = self.permissions.classify_command("npm install -g express")
        self.assertEqual(risk5, RiskLevel.SYSTEM_CHANGE)

    # ── 5. Rollback & Backup ─────────────────────────────────────────────────

    def test_rollback_file_backup(self):
        sample_file = self.test_dir / "app.py"
        sample_file.write_text("print('version 1')", encoding="utf-8")

        backup = self.rollback.backup_file(sample_file)
        self.assertIsNotNone(backup)
        self.assertTrue(backup.exists())

        # Overwrite file
        sample_file.write_text("print('version 2')", encoding="utf-8")

        # Restore
        ok = self.rollback.restore_file(backup, sample_file)
        self.assertTrue(ok)
        self.assertEqual(sample_file.read_text(encoding="utf-8"), "print('version 1')")

    # ── 6. Verification Engine ───────────────────────────────────────────────

    def test_verification_engine(self):
        good_py = self.test_dir / "valid.py"
        good_py.write_text("x = 10\ny = 20\n", encoding="utf-8")
        ok_code, _ = self.verification.verify_code(good_py)
        self.assertTrue(ok_code)

        bad_py = self.test_dir / "invalid.py"
        bad_py.write_text("def broken_syntax(:", encoding="utf-8")
        bad_code, _ = self.verification.verify_code(bad_py)
        self.assertFalse(bad_code)

    # ── 7. Router Intent Dispatch ────────────────────────────────────────────

    def test_agent_router(self):
        name_xl, _ = self.router.route_intent("Clean my sales spreadsheet and report")
        self.assertEqual(name_xl, "spreadsheet")

        name_vid, _ = self.router.route_intent("Create a trending YouTube Short")
        self.assertEqual(name_vid, "video")

        name_anti, _ = self.router.route_intent("Open Antigravity and continue my app")
        self.assertEqual(name_anti, "antigravity")

        name_code, _ = self.router.route_intent("Debug and fix syntax error in auth module")
        self.assertEqual(name_code, "coding")

    # ── 8. GOLDEN SCENARIOS A THROUGH G ──────────────────────────────────────

    def test_golden_scenario_a(self):
        """TEST A: Remember project port 3008, reload memory instance, query port."""
        self.memory.set_project_memory("MyProject", "config", "port", "3008")

        # Simulate restart with fresh MemoryManager instance
        reloaded_memory = MemoryManager(db_path=self.db_path)
        ctx = reloaded_memory.get_project_context("MyProject")
        self.assertEqual(ctx["facts"]["config"]["port"], "3008")

        recalled = reloaded_memory.recall("port", project_name="MyProject")
        self.assertIn("3008", recalled)

    def test_golden_scenario_b(self):
        """TEST B: Complete coding fix -> checkpoint -> restart -> resume project."""
        task_id = self.memory.create_task("Fix port conflict", "Free occupied port 3008", project_name="ZynPay")
        self.memory.store_task_checkpoint(
            task_id=task_id,
            checkpoint_name="Terminated stale process on port 3008",
            summary="Process 1420 killed",
            next_action="Run test suite and restart server",
            status="RUNNING",
        )

        # Fresh instance on restart
        reloaded_planner = TaskPlanner(MemoryManager(db_path=self.db_path))
        resumed = reloaded_planner.resume_task(project_name="ZynPay")
        self.assertIsNotNone(resumed)
        self.assertEqual(resumed["last_checkpoint"], "Terminated stale process on port 3008")
        self.assertEqual(resumed["next_action"], "Run test suite and restart server")

    def test_golden_scenario_c(self):
        """TEST C: Open latest Excel file and create a summary sheet."""
        from openpyxl import Workbook
        wb_path = self.test_dir / "sales.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "SalesData"
        ws.append(["Item", "Amount", "Tax"])
        ws.append(["Widget A", 100, "=B2*0.1"])
        ws.append(["Widget B", 200, "=B3*0.1"])
        wb.save(wb_path)

        agent = SpreadsheetAgent(
            self.memory, self.planner, self.permissions,
            self.verification, self.recovery, self.rollback,
        )
        res = agent.create_summary_sheet(wb_path)
        self.assertEqual(res["status"], "success")
        self.assertIn("Summary", res["summary_sheet"])

        # Check that formulas are intact
        ok, _ = self.verification.verify_excel(wb_path, expected_sheets=["SalesData", "Summary"])
        self.assertTrue(ok)

    def test_golden_scenario_d(self):
        """TEST D: 30-second vertical video task validation."""
        agent = VideoAgent(
            self.memory, self.planner, self.permissions,
            self.verification, self.recovery, self.rollback,
        )
        # Probe non-existent file should be caught
        probe = agent.probe_media(self.test_dir / "missing.mp4")
        self.assertFalse(probe["verified"])

    def test_golden_scenario_e(self):
        """TEST E: Action fails twice -> 2-strike policy triggered."""
        key = "start_flutter_app"
        err = "SocketException: Address already in use on port 3008"

        # Attempt 1
        shift1, g1, _ = self.recovery.record_failure(key, err)
        self.assertFalse(shift1)

        # Attempt 2
        shift2, g2, _ = self.recovery.record_failure(key, err)
        self.assertTrue(shift2)
        self.assertIn("2-STRIKE ALERT", g2)

    def test_golden_scenario_f(self):
        """TEST F: User asks to permanently delete an important folder -> confirmation blocked."""
        risk, reason = self.permissions.classify_command("rm -rf /var/data/critical")
        self.assertEqual(risk, RiskLevel.HIGH_IMPACT)
        self.assertTrue(self.permissions.requires_confirmation(risk))

    def test_golden_scenario_g(self):
        """TEST G: Open Antigravity and continue app -> high-context prompt prepared."""
        self.memory.set_project_memory("ZynPay", "tech_stack", "frontend", "Flutter")
        self.memory.set_project_memory("ZynPay", "config", "port", "3008")

        agent = AntigravityAgent(
            self.memory, self.planner, self.permissions,
            self.verification, self.recovery, self.rollback,
        )
        prep = agent.prepare_antigravity_prompt("ZynPay", "Implement payment gateway callback webhook")
        self.assertEqual(prep["project"], "ZynPay")
        self.assertIn("Flutter", prep["generated_prompt"])
        self.assertIn("3008", prep["generated_prompt"])
        self.assertIn("Implement payment gateway", prep["generated_prompt"])


# Backward-compatibility alias
TestJarvisIntelligenceEngine = TestCharlieIntelligenceEngine


if __name__ == "__main__":
    unittest.main()
