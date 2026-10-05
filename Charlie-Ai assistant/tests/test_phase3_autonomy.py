"""tests/test_phase3_autonomy.py — Comprehensive Test Suite for Phase 3 Autonomous Work Engine.

Validates TaskGraph, AutonomyOrchestrator, Resource Locks, Loop Detection, Replanning,
and Golden Scenarios: Coding, Antigravity, Excel, Video, Recovery, Restart, Interruption, and Safety.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.agents.debug_agent import DebugAgent
from engine.agents.security_agent import SecurityAgent
from engine.agents.verification_agent import VerificationAgent
from engine.autonomy.classifier import GoalInterpreter, TaskComplexity, TaskComplexityClassifier
from engine.autonomy.context import ArtifactRegistry, ExecutionContext
from engine.autonomy.guard import ExternalActionGuard, ExternalActionType
from engine.autonomy.loop_detector import LoopDetector
from engine.autonomy.orchestrator import ActionBudget, AutonomyLevel, AutonomyOrchestrator
from engine.autonomy.queue_locks import ResourceLockManager, TaskPriority, TaskQueueManager
from engine.autonomy.replanner import Replanner
from engine.autonomy.resume_manager import CheckpointManager, ResumeManager
from engine.autonomy.task_graph import TaskGraph, TaskNode, TaskStatus
from engine.error_recovery import ErrorRecoveryEngine
from engine.memory_manager import MemoryManager
from engine.permissions import PermissionManager
from engine.rollback import RollbackManager
from engine.router import AgentRouter
from engine.tool_registry import ToolRegistry
from engine.verification import VerificationEngine


class TestPhase3Autonomy(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_autonomy.db")
        self.memory = MemoryManager(db_path=self.db_path)
        self.permissions = PermissionManager()
        self.verification = VerificationEngine()
        self.recovery = ErrorRecoveryEngine(self.memory)
        self.rollback = RollbackManager(backup_dir=Path(self.temp_dir) / ".backups")
        self.tools = ToolRegistry(permissions=self.permissions, verification=self.verification)
        self.router = AgentRouter(
            memory=self.memory,
            planner=None,
            permissions=self.permissions,
            verification=self.verification,
            recovery=self.recovery,
            rollback=self.rollback,
        )
        self.orchestrator = AutonomyOrchestrator(
            memory_manager=self.memory,
            agent_router=self.router,
            tool_registry=self.tools,
            permission_manager=self.permissions,
            verification_engine=self.verification,
            error_recovery=self.recovery,
            rollback_manager=self.rollback,
            autonomy_level=AutonomyLevel.LEVEL_3_AUTONOMOUS_WORKFLOW,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # --- 1. TaskGraph & DAG Tests ---
    def test_task_graph_dependency_resolution(self):
        graph = TaskGraph("g1", "Test DAG")
        n0 = TaskNode("n0", "Step 0", "First step", "GeneralAgent")
        n1 = TaskNode("n1", "Step 1", "Second step", "GeneralAgent", dependencies=["n0"])
        n2 = TaskNode("n2", "Step 2", "Third step", "GeneralAgent", dependencies=["n1"])

        graph.add_node(n0)
        graph.add_node(n1)
        graph.add_node(n2)

        # Initially, only n0 is ready
        ready = graph.get_ready_nodes()
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0].id, "n0")

        # Complete n0
        graph.mark_completed("n0")
        ready = graph.get_ready_nodes()
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0].id, "n1")

        # Complete n1
        graph.mark_completed("n1")
        ready = graph.get_ready_nodes()
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0].id, "n2")

        graph.mark_completed("n2")
        self.assertTrue(graph.is_completed())

    def test_task_graph_cycle_detection(self):
        graph = TaskGraph("g_cycle", "Cycle DAG")
        n0 = TaskNode("n0", "Node 0", "", "GeneralAgent", dependencies=["n2"])
        n1 = TaskNode("n1", "Node 1", "", "GeneralAgent", dependencies=["n0"])
        n2 = TaskNode("n2", "Node 2", "", "GeneralAgent", dependencies=["n1"])

        graph.add_node(n0)
        graph.add_node(n1)
        graph.add_node(n2)

        self.assertTrue(graph.detect_cycles())

    # --- 2. Classification & Goal Interpretation ---
    def test_task_complexity_classifier(self):
        self.assertEqual(
            TaskComplexityClassifier.classify("Open Chrome"),
            TaskComplexity.SIMPLE,
        )
        self.assertEqual(
            TaskComplexityClassifier.classify("Clean this Excel file"),
            TaskComplexity.MODERATE,
        )
        self.assertEqual(
            TaskComplexityClassifier.classify("Fix backend login bug and test"),
            TaskComplexity.COMPLEX,
        )
        self.assertEqual(
            TaskComplexityClassifier.classify("Create YouTube Short from today's trend"),
            TaskComplexity.LONG_WORKFLOW,
        )

    def test_goal_interpreter_minimum_question_defaults(self):
        interpreter = GoalInterpreter(self.memory)
        goal = interpreter.interpret("Charlie mere YouTube ke liye 45 sec short bana do")

        self.assertEqual(goal.complexity, TaskComplexity.LONG_WORKFLOW)
        self.assertEqual(goal.inferred_defaults.get("aspect_ratio"), "9:16 (1080x1920)")
        self.assertEqual(goal.inferred_defaults.get("duration_seconds"), 45)
        self.assertIn("video_studio", goal.tools_required)
        self.assertEqual(len(goal.missing_information), 0)

    # --- 3. Resource Locks & Task Queue ---
    def test_resource_lock_manager_mutual_exclusion(self):
        lock_mgr = ResourceLockManager()

        # Task 1 acquires mouse
        acquired = lock_mgr.acquire("mouse", "task_1", timeout_sec=0.2)
        self.assertTrue(acquired)
        self.assertTrue(lock_mgr.is_locked("mouse"))
        self.assertEqual(lock_mgr.get_owner("mouse"), "task_1")

        # Task 2 cannot acquire mouse
        acquired_2 = lock_mgr.acquire("mouse", "task_2", timeout_sec=0.1)
        self.assertFalse(acquired_2)

        # Release task 1
        lock_mgr.release("mouse", "task_1")
        self.assertFalse(lock_mgr.is_locked("mouse"))

        # Task 2 can now acquire
        acquired_3 = lock_mgr.acquire("mouse", "task_2", timeout_sec=0.2)
        self.assertTrue(acquired_3)

    def test_task_queue_priority(self):
        queue = TaskQueueManager()
        queue.enqueue("t_norm", "Normal task", TaskPriority.NORMAL)
        queue.enqueue("t_urgent", "Urgent rollback", TaskPriority.URGENT)
        queue.enqueue("t_high", "User click", TaskPriority.HIGH)

        first = queue.dequeue()
        self.assertEqual(first.task_id, "t_urgent")
        second = queue.dequeue()
        self.assertEqual(second.task_id, "t_high")
        third = queue.dequeue()
        self.assertEqual(third.task_id, "t_norm")

    # --- 4. Loop Detection & Replanning ---
    def test_loop_detector(self):
        detector = LoopDetector(max_identical_threshold=2)

        detector.record_step("click_ui", {"x": 100, "y": 200}, "Error: not found", success=False)
        is_loop, _ = detector.is_looping()
        self.assertFalse(is_loop)

        detector.record_step("click_ui", {"x": 100, "y": 200}, "Error: not found", success=False)
        is_loop, reason = detector.is_looping()
        self.assertTrue(is_loop)
        self.assertIn("Repetitive tool failure", reason)

    def test_replanner_in_flight_branch_mutation(self):
        graph = TaskGraph("g_replan", "Replanning test")
        n0 = TaskNode("n0", "GUI Edit", "", "VideoAgent", tool="desktop_control")
        n1 = TaskNode("n1", "Verify", "", "VerificationAgent", dependencies=["n0"])
        graph.add_node(n0)
        graph.add_node(n1)

        replanned = Replanner.replan_on_failure(graph, "n0", "GUI window crashed")
        self.assertTrue(replanned)

        # Switched from GUI to direct CLI tool
        node_0 = graph.get_node("n0")
        self.assertEqual(node_0.tool, "powershell_execute")
        self.assertEqual(node_0.status, TaskStatus.READY)

    # --- 5. External Action Guard ---
    def test_external_action_guard(self):
        guard = ExternalActionGuard(self.permissions)

        # PUBLISH action should be blocked without explicit confirmation
        allowed, reason = guard.validate_action("PUBLISH", "YouTube", {"title": "Test"})
        self.assertFalse(allowed)
        self.assertIn("External action barrier", reason)

        # With explicit true confirmation callback
        allowed_conf, _ = guard.validate_action(
            "PUBLISH",
            "YouTube",
            {"title": "Test"},
            confirm_callback=lambda msg: True,
        )
        self.assertTrue(allowed_conf)

    # --- 6. DebugAgent ---
    def test_debug_agent_known_fix_retrieval(self):
        # Seed an error fix in memory
        self.memory.store_error_solution(
            error_signature="Port 3008 in use",
            solution="terminate stale development process on 3008",
            application="ZynPay",
        )

        debug_agent = DebugAgent(self.memory, self.recovery)
        task_node = TaskNode("n_dbg", "Diagnose error", "", "DebugAgent", inputs={"error": "Port 3008 in use"})
        ctx = ExecutionContext("t_dbg", "Fix error", project_id="ZynPay")

        res = debug_agent.execute(task_node, ctx)
        self.assertEqual(res.status, "SUCCESS")
        self.assertIn("terminate stale development process", str(res.output.get("known_solution")))

    # --- 7. Checkpoint & ResumeManager ---
    def test_checkpoint_and_resume(self):
        task_id = self.memory.create_task("Test Workflow", goal="Build App", project_id="ZynPay")
        graph = TaskGraph(task_id, "Build App")
        n0 = TaskNode("n0", "Setup", "", "GeneralAgent", status=TaskStatus.COMPLETED)
        n1 = TaskNode("n1", "Compile", "", "GeneralAgent", dependencies=["n0"], status=TaskStatus.RUNNING)
        graph.add_node(n0)
        graph.add_node(n1)

        ctx = ExecutionContext(task_id, "Build App", project_id="ZynPay")
        ctx.artifacts.register(os.path.join(self.temp_dir, "test.py"), "source_code", "CodingAgent", task_id)

        chk_mgr = CheckpointManager(self.memory)
        chk_mgr.save_checkpoint(graph, ctx, current_stage="Compile Stage")

        # Resume using ResumeManager
        resumer = ResumeManager(self.memory, chk_mgr)
        res = resumer.get_resumable_task(project_id="ZynPay")
        self.assertIsNotNone(res)
        restored_graph, restored_ctx, stage = res

        self.assertEqual(stage, "Compile Stage")
        self.assertEqual(len(restored_graph.nodes), 2)
        self.assertEqual(restored_graph.get_node("n0").status, TaskStatus.COMPLETED)
        # In-flight RUNNING node was safely reset to READY
        self.assertEqual(restored_graph.get_node("n1").status, TaskStatus.READY)
        self.assertEqual(len(restored_ctx.artifacts.all()), 1)

    # --- 8. GOLDEN SCENARIO: Coding Autonomy ---
    def test_golden_scenario_coding_autonomy(self):
        res = self.orchestrator.execute_goal("Charlie mera last app continue karo", active_project="ZynPay")
        self.assertIn(res["status"], ("COMPLETED", "PARTIAL"))
        self.assertEqual(res["progress"]["percent"], 100)
        self.assertTrue(res["progress"]["completed"] >= 5)

    # --- 9. GOLDEN SCENARIO: Antigravity Guided Workflow ---
    def test_golden_scenario_antigravity_autonomy(self):
        res = self.orchestrator.execute_goal(
            "Antigravity kholo aur meri app ka pending feature complete karao",
            active_project="ZynPay",
        )
        self.assertIn(res["status"], ("COMPLETED", "PARTIAL"))
        self.assertEqual(res["progress"]["percent"], 100)

    # --- 10. GOLDEN SCENARIO: Excel Autonomy ---
    def test_golden_scenario_excel_autonomy(self):
        # Create a sample workbook
        import openpyxl
        wb_path = os.path.join(self.temp_dir, "sales.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sales"
        ws.append(["Item", "Price", "Qty"])
        ws.append(["Widget", 10.0, 5])
        wb.save(wb_path)

        res = self.orchestrator.execute_goal("Latest Excel file ka professional report bana do")
        self.assertIn(res["status"], ("COMPLETED", "PARTIAL"))
        self.assertEqual(res["progress"]["percent"], 100)

    # --- 11. GOLDEN SCENARIO: Video Autonomy ---
    def test_golden_scenario_video_autonomy(self):
        res = self.orchestrator.execute_goal("Aaj ke trend par 30-second YouTube Short bana do")
        self.assertIn(res["status"], ("COMPLETED", "PARTIAL"))
        self.assertEqual(res["progress"]["percent"], 100)
        self.assertTrue(res["progress"]["completed"] >= 7)

    # --- 12. GOLDEN SCENARIO: Recovery from Tool Failure ---
    def test_golden_scenario_recovery(self):
        task_id = "task_rec_test"
        graph = TaskGraph(task_id, "Test Recovery")
        n0 = TaskNode("n0", "Failing Step", "Will fail once", "TroubleshootingAgent", tool="diagnose_error")
        graph.add_node(n0)

        # Trigger replan on node
        Replanner.replan_on_failure(graph, "n0", "Initial connection timeout", alternative_tool="powershell_execute")
        self.assertEqual(graph.get_node("n0").tool, "powershell_execute")
        self.assertEqual(graph.get_node("n0").status, TaskStatus.READY)

    # --- 13. GOLDEN SCENARIO: User Interruption Parameter Update ---
    def test_golden_scenario_user_interruption(self):
        task_id = "task_interrupt"
        graph = self.orchestrator.build_domain_graph(task_id, "Create YouTube Short")

        # User interrupts: "Video 45 seconds ke badle 25 seconds karo"
        updated = Replanner.replan_on_user_modification(
            graph,
            param_updates={"duration_seconds": 25},
            target_domain="video",
        )
        self.assertTrue(updated > 0)
        # Check downstream node received updated duration
        edit_node = graph.get_node("n5_edit")
        self.assertEqual(edit_node.inputs.get("duration_seconds"), 25)

    # --- 14. GOLDEN SCENARIO: Safety Boundary Barrier ---
    def test_golden_scenario_safety_barrier(self):
        res = self.orchestrator.execute_goal("Clean my PC and delete everything")
        # Destructive request classified as HIGH_IMPACT and blocked by guard
        self.assertEqual(res["status"], "BLOCKED")
        self.assertIn("SAFETY_BARRIER", res["message"])


    # --- 15. Resume Manager List & Dependency Repair ---
    def test_resume_manager_list_and_dependency_repair(self):
        task_id = self.memory.create_task("Data Pipeline", goal="ETL Workflow", project_id="ZynPay")
        graph = TaskGraph(task_id, "ETL Workflow")
        n0 = TaskNode("n0", "Extract", "", "GeneralAgent", status=TaskStatus.COMPLETED)
        n1 = TaskNode("n1", "Transform", "", "GeneralAgent", dependencies=["n0"], status=TaskStatus.RUNNING)
        n2 = TaskNode("n2", "Load", "", "GeneralAgent", dependencies=["n1"], status=TaskStatus.RUNNING)
        graph.add_node(n0)
        graph.add_node(n1)
        graph.add_node(n2)

        ctx = ExecutionContext(task_id, "ETL Workflow", project_id="ZynPay")
        chk_mgr = CheckpointManager(self.memory)
        chk_mgr.save_checkpoint(graph, ctx, current_stage="Transform Stage", status="STOPPED")

        resumer = ResumeManager(self.memory, chk_mgr)
        tasks = resumer.list_resumable_tasks(project_id="ZynPay")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_id"], task_id)
        self.assertEqual(tasks[0]["current_stage"], "Transform Stage")
        self.assertEqual(tasks[0]["progress"]["completed"], 1)

        # Restore
        restored = resumer.get_resumable_task(task_id=task_id)
        self.assertIsNotNone(restored)
        rest_graph, rest_ctx, stage = restored
        self.assertEqual(stage, "Transform Stage")
        # n1's dependency (n0) is COMPLETED -> n1 becomes READY
        self.assertEqual(rest_graph.get_node("n1").status, TaskStatus.READY)
        # n2's dependency (n1) is NOT completed -> n2 becomes PENDING
        self.assertEqual(rest_graph.get_node("n2").status, TaskStatus.PENDING)

    # --- 16. Orchestrator Resume Execution to Completion ---
    def test_orchestrator_resume_execution_loop(self):
        task_id = self.memory.create_task("Report Generation", goal="Build Financial Report", project_id="FinanceApp")
        graph = TaskGraph(task_id, "Build Financial Report")
        n0 = TaskNode("n0", "Query DB", "Query metrics", "GeneralAgent", status=TaskStatus.COMPLETED)
        n1 = TaskNode("n1", "Compile PDF", "Assemble report", "GeneralAgent", dependencies=["n0"], status=TaskStatus.RUNNING)
        graph.add_node(n0)
        graph.add_node(n1)

        ctx = ExecutionContext(task_id, "Build Financial Report", project_id="FinanceApp")
        chk_mgr = CheckpointManager(self.memory)
        chk_mgr.save_checkpoint(graph, ctx, current_stage="Query DB Done", status="PAUSED")

        # Resume execution through orchestrator
        res = self.orchestrator.resume_execution(task_id=task_id)
        self.assertEqual(res["status"], "COMPLETED")
        self.assertEqual(res["progress"]["percent"], 100)
        self.assertEqual(res["resumed_from_stage"], "Query DB Done")

    # --- 17. Orchestrator Execute Goal with Resume Intent ---
    def test_orchestrator_execute_goal_resume_intent(self):
        task_id = self.memory.create_task("Backup Task", goal="Backup system files", project_id="SysAdmin")
        graph = TaskGraph(task_id, "Backup system files")
        n0 = TaskNode("n0", "Scan files", "Scan directories", "GeneralAgent", status=TaskStatus.COMPLETED)
        n1 = TaskNode("n1", "Compress archive", "Tar and gzip", "GeneralAgent", dependencies=["n0"], status=TaskStatus.RUNNING)
        graph.add_node(n0)
        graph.add_node(n1)

        ctx = ExecutionContext(task_id, "Backup system files", project_id="SysAdmin")
        chk_mgr = CheckpointManager(self.memory)
        chk_mgr.save_checkpoint(graph, ctx, current_stage="Scan Done", status="STOPPED")

        # Calling execute_goal with "resume" automatically detects and completes the interrupted task
        res = self.orchestrator.execute_goal("resume", active_project="SysAdmin")
        self.assertEqual(res["status"], "COMPLETED")
        self.assertEqual(res["progress"]["percent"], 100)
        self.assertEqual(res["resumed_from_stage"], "Scan Done")

    # --- 18. Actions Autonomous Work Resume & List ---
    def test_actions_autonomous_work_resume_and_list(self):
        from actions.autonomous_work import autonomous_work, _orchestrator
        orig_memory = _orchestrator.memory
        orig_resumer = _orchestrator.resumer
        orig_checkpointer = _orchestrator.checkpointer
        try:
            _orchestrator.memory = self.memory
            _orchestrator.checkpointer = CheckpointManager(self.memory)
            _orchestrator.resumer = ResumeManager(self.memory, _orchestrator.checkpointer)

            task_id = self.memory.create_task("Video Render", goal="Render 4k Video", project_id="Studio")
            graph = TaskGraph(task_id, "Render 4k Video")
            n0 = TaskNode("n0", "Render Frames", "Render", "GeneralAgent", status=TaskStatus.COMPLETED)
            n1 = TaskNode("n1", "Mux Audio", "Audio", "GeneralAgent", dependencies=["n0"], status=TaskStatus.RUNNING)
            graph.add_node(n0)
            graph.add_node(n1)

            ctx = ExecutionContext(task_id, "Render 4k Video", project_id="Studio")
            _orchestrator.checkpointer.save_checkpoint(graph, ctx, current_stage="Render Done", status="PAUSED")

            # Test list action
            list_res = autonomous_work({"action": "list", "project": "Studio"})
            self.assertIn("Found 1 resumable task(s)", list_res)
            self.assertIn(task_id, list_res)

            # Test resume action
            resume_res = autonomous_work({"action": "resume", "project": "Studio"})
            self.assertIn("[AUTONOMY RESUMED: COMPLETED]", resume_res)
            self.assertIn("100%", resume_res)
        finally:
            _orchestrator.memory = orig_memory
            _orchestrator.resumer = orig_resumer
            _orchestrator.checkpointer = orig_checkpointer


if __name__ == "__main__":
    unittest.main()
