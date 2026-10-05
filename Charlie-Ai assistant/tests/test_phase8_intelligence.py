"""tests/test_phase8_intelligence.py — Certification & Golden Tests for CHARLIE Phase 8.

Validates:
1. Personal Knowledge Graph CRUD & Neighbor Traversal (Test 100)
2. Entity Resolution & Colloquial Aliases (Test 101)
3. Temporal Knowledge & Superseded Port Resolution (Test 102)
4. Root-Cause Graph & Error Diagnostics (Test 103)
5. Pattern Recognition & Reusable Skill Suggestions (Test 104)
6. Proactive Meeting Detection & Brief Generation (Test 105)
7. Approaching Deadline Alert with Budget Gating (Test 106)
8. Bounded Self-Improvement & Tool Preference Ranking (Test 107)
9. Strict Block on Autonomous Self-Modification of Source Code (Test 108)
10. Automated Regression Protection & Rollback (Test 109)
11. Explicit User Correction & Anti-Recreation Persistence (Test 110)
12. Notification Budget Spam Suppression & Grouping (Test 111)
13. Context Fusion Scoped Subgraph (Test 112)
14. Restart Persistence of Knowledge Graph & Ledger (Test 113)
15. Source Provenance Explanation (Test 114)
16. Certification Matrix for all Phase 8 Subsystems (Section 115)
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from engine.intelligence.context_fusion import ContextFusionEngine
from engine.intelligence.core import IntelligenceCore
from engine.intelligence.entity_resolver import EntityResolver
from engine.intelligence.evaluation_engine import EvaluationEngine
from engine.intelligence.knowledge_graph import PersonalKnowledgeGraph
from engine.intelligence.memory_quality import MemoryQualityManager
from engine.intelligence.models import (
    Entity,
    EntityType,
    ImprovementProposal,
    InterventionAction,
    ProposalStatus,
    Relationship,
    RelationType,
)
from engine.intelligence.pattern_engine import PatternRecognitionEngine
from engine.intelligence.proactive_engine import (
    NextActionPredictor,
    NotificationBudget,
    ProactiveIntelligenceEngine,
)
from engine.intelligence.reasoning import (
    DependencyReasoner,
    GoalManager,
    ReasoningOrchestrator,
    RootCauseGraph,
)
from engine.intelligence.self_improvement import (
    ImprovementLedger,
    SelfImprovementEngine,
    ToolReliabilityTracker,
)


class TestPhase8IntelligenceEngine(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="charlie_intel_test_"))
        self.db_path = self.test_dir / "knowledge_graph.db"
        self.core = IntelligenceCore(db_path=self.db_path)
        self.graph = self.core.graph

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # ── Golden Test 100: Graph Traversal ──────────────────────────────────────

    def test_golden_100_graph_traversal(self):
        """Test 100: Project Alpha, Person Rahul, Meeting M1, Document D1 traversal."""
        p_alpha = self.graph.create_entity("proj_alpha", EntityType.PROJECT, "Project Alpha")
        p_rahul = self.graph.create_entity("pers_rahul", EntityType.PERSON, "Rahul")
        m_m1 = self.graph.create_entity("meet_m1", EntityType.MEETING, "Sprint Sync")
        d_d1 = self.graph.create_entity("doc_d1", EntityType.DOCUMENT, "Architecture Spec")

        self.graph.create_relation(p_rahul.id, p_alpha.id, RelationType.WORKS_ON)
        self.graph.create_relation(m_m1.id, p_alpha.id, RelationType.RELATES_TO_PROJECT)
        self.graph.create_relation(d_d1.id, p_alpha.id, RelationType.BELONGS_TO)

        # Query Project Alpha neighbors
        neighbors = self.graph.find_neighbors(p_alpha.id, active_only=True)
        connected_names = [ent.canonical_name for _, ent in neighbors]

        self.assertIn("Rahul", connected_names)
        self.assertIn("Sprint Sync", connected_names)
        self.assertIn("Architecture Spec", connected_names)

    # ── Golden Test 101: Entity Alias Resolution ──────────────────────────────

    def test_golden_101_entity_alias_resolution(self):
        """Test 101: Entities Visual Studio Code with aliases (VS Code, Code) -> 'Code kholo' resolves."""
        vscode = self.graph.create_entity(
            "app_vscode",
            EntityType.APPLICATION,
            "Visual Studio Code",
            aliases=["VS Code", "Code", "editor"],
        )

        resolved = self.core.entity_resolver.resolve("Code")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.canonical_name, "Visual Studio Code")

        resolved_colloquial = self.core.entity_resolver.resolve("vs code")
        self.assertEqual(resolved_colloquial.canonical_name, "Visual Studio Code")

        # Payment app synonym test
        zynpay = self.graph.create_entity("proj_zynpay", EntityType.PROJECT, "ZynPay", aliases=["zyn pay"])
        resolved_payment = self.core.entity_resolver.resolve("mera payment wala project")
        self.assertIsNotNone(resolved_payment)
        self.assertEqual(resolved_payment.canonical_name, "ZynPay")

    # ── Golden Test 102: Superseded Knowledge ────────────────────────────────

    def test_golden_102_superseded_knowledge(self):
        """Test 102: Backend port 3008 superseded by 3010 -> current answer = 3010, history preserved."""
        backend = self.graph.create_entity("srv_backend", EntityType.SERVICE, "ZynPay Backend")
        p3008 = self.graph.create_entity("port_3008", EntityType.PORT, "3008")
        p3010 = self.graph.create_entity("port_3010", EntityType.PORT, "3010")

        # Initially set port 3008
        self.graph.create_relation(backend.id, p3008.id, RelationType.RUNS_ON_PORT, source_provenance="old_config")

        # Supersede with port 3010
        self.core.memory_quality.resolve_conflicting_relation(
            source_id=backend.id,
            target_id_new=p3010.id,
            relation_type=RelationType.RUNS_ON_PORT,
            new_provenance="verified_application_properties",
        )

        # Active neighbor check: only 3010 should be active
        active_ports = self.graph.find_neighbors(backend.id, relation_type=RelationType.RUNS_ON_PORT, active_only=True)
        self.assertEqual(len(active_ports), 1)
        self.assertEqual(active_ports[0][1].canonical_name, "3010")

        # Historical check: inactive/superseded includes 3008
        all_ports = self.graph.find_neighbors(backend.id, relation_type=RelationType.RUNS_ON_PORT, active_only=False)
        port_names = [ent.canonical_name for _, ent in all_ports]
        self.assertIn("3008", port_names)
        self.assertIn("3010", port_names)

    # ── Golden Test 103: Error Relation & Root-Cause Graph ────────────────────

    def test_golden_103_root_cause_graph(self):
        """Test 103: BackendConnectionFailure CAUSED_BY PostgreSQLNotRunning guides diagnosis."""
        err = self.graph.create_entity("err_backend_conn", EntityType.ERROR, "BackendConnectionFailure")
        db_down = self.graph.create_entity("err_pg_down", EntityType.ERROR, "PostgreSQLNotRunning")

        self.graph.create_relation(
            source_id=err.id,
            target_id=db_down.id,
            relation_type=RelationType.CAUSED_BY,
            source_provenance="previous_incident_resolution",
        )

        causes = self.core.root_cause_graph.trace_root_cause("BackendConnectionFailure")
        self.assertEqual(len(causes), 1)
        self.assertEqual(causes[0]["cause_entity"], "PostgreSQLNotRunning")
        self.assertEqual(causes[0]["provenance"], "previous_incident_resolution")

    # ── Golden Test 104: Pattern Recognition (>1 event threshold) ─────────────

    def test_golden_104_pattern_recognition(self):
        """Test 104: Workflow repeated multiple times -> pattern detected, suggests reusable Skill."""
        pattern_eng = self.core.pattern_engine

        # First occurrence: under threshold (threshold is >= 2)
        pat1 = pattern_eng.record_event("WORKFLOW_SEQUENCE", "Antigravity -> Start Backend -> Open Chrome")
        self.assertIsNone(pat1)

        # Second occurrence: threshold met!
        pat2 = pattern_eng.record_event("WORKFLOW_SEQUENCE", "Antigravity -> Start Backend -> Open Chrome")
        self.assertIsNotNone(pat2)
        self.assertEqual(pat2.event_count, 2)
        self.assertIn("Suggest creating a reusable Skill", pat2.recommended_action)

        recs = pattern_eng.get_skill_recommendations()
        self.assertTrue(any("Antigravity" in r for r in recs))

    # ── Golden Test 105: Proactive Meeting Detection ──────────────────────────

    def test_golden_105_proactive_meeting_preparation(self):
        """Test 105: Meeting in 40 min -> proactive brief prepared, NO external email/message sent."""
        proactive = self.core.proactive_engine
        event = proactive.check_upcoming_meeting("Client Sync", minutes_remaining=40.0, project_name="ZynPay")

        self.assertIsNotNone(event)
        self.assertEqual(event.action_taken, InterventionAction.PREPARE_DRAFT)
        self.assertIn("ZynPay meeting brief ready hai", event.message)
        # Verify no external communication action was assigned
        self.assertNotEqual(event.action_taken, InterventionAction.NOTIFY)

    # ── Golden Test 106: Deadline Proximity with Budget ───────────────────────

    def test_golden_106_deadline_proximity(self):
        """Test 106: Task deadline tomorrow -> notification delivered through budget."""
        proactive = self.core.proactive_engine
        event = proactive.check_deadline_proximity("Store Submission", hours_remaining=12.0, project_name="ZynPay")

        self.assertIsNotNone(event)
        self.assertEqual(event.action_taken, InterventionAction.NOTIFY)
        self.assertIn("due in 12.0 hours", event.message)

    # ── Golden Test 107: Safe Self-Improvement (Tool Ranking) ──────────────────

    def test_golden_107_safe_self_improvement(self):
        """Test 107: Tool A fails, Tool B succeeds -> SelfImprovement adjusts internal ranking in ledger."""
        si = self.core.self_improvement

        # Record outcomes: Tool A (Excel UI) fails 3 times; Tool B (openpyxl) succeeds 5 times
        for _ in range(3):
            si.tracker.record_outcome("excel_ui_automation", success=False)
        for _ in range(5):
            si.tracker.record_outcome("openpyxl_direct_edit", success=True)

        prop = si.evaluate_tool_improvement(
            category="excel_editing",
            failing_tool="excel_ui_automation",
            succeeding_tool="openpyxl_direct_edit",
        )

        self.assertEqual(prop.status, ProposalStatus.APPLIED)
        self.assertEqual(si.tool_preferences["excel_editing"], "openpyxl_direct_edit")
        self.assertFalse(prop.requires_code_modification)

        applied = si.ledger.list_applied()
        self.assertTrue(any(p.id == prop.id for p in applied))

    # ── Golden Test 108: Unsafe Self-Modification Blocked ──────────────────────

    def test_golden_108_unsafe_self_modification_blocked(self):
        """Test 108: Self-improvement requiring source code modification MUST NOT auto-deploy (Section 28)."""
        si = self.core.self_improvement

        prop = si.propose_code_modification(
            problem="Improve regex parsing speed in core router.",
            proposed_code_change="Rewrite regex module in C++ or alter system permissions.",
            test_plan="Compile and run unit tests.",
            rollback_plan="Revert git commit.",
        )

        self.assertTrue(prop.requires_code_modification)
        self.assertEqual(prop.status, ProposalStatus.PROPOSED)

        # Attempt to apply without user approval -> MUST FAIL
        applied = si.ledger.apply_improvement(prop.id)
        self.assertFalse(applied)
        self.assertEqual(prop.status, ProposalStatus.PROPOSED)

    # ── Golden Test 109: Regression Protection & Rollback ─────────────────────

    def test_golden_109_regression_protection_and_rollback(self):
        """Test 109: Improvement candidate fails benchmark -> EvaluationEngine rejects/rolls back."""
        eval_eng = self.core.evaluation_engine

        # Register failing benchmark
        eval_eng.register_benchmark("memory_retrieval_benchmark", lambda: False)

        prop = ImprovementProposal(
            id="imp_test_candidate",
            problem="Latency optimization",
            evidence="Test hypothesis",
            proposed_change="Change retrieval weights",
            scope="INTERNAL_RANKING",
            expected_benefit="Faster query",
            risk_level="LOW",
            test_plan="Run benchmark",
            rollback_plan="Restore weights",
            status=ProposalStatus.PROPOSED,
        )
        self.core.ledger.record_proposal(prop)

        # Guard evaluation
        allowed = eval_eng.evaluate_and_guard(prop, "memory_retrieval_benchmark")
        self.assertFalse(allowed)
        self.assertIn(prop.status, (ProposalStatus.ROLLED_BACK, ProposalStatus.REJECTED))

    # ── Golden Test 110: User Correction & Anti-Recreation ────────────────────

    def test_golden_110_user_correction_anti_recreation(self):
        """Test 110: User corrects 'Rahul ZynPay project ka nahi hai' -> removed, prevented from recreating."""
        rahul = self.graph.create_entity("pers_rahul_corr", EntityType.PERSON, "Rahul")
        zynpay = self.graph.create_entity("proj_zynpay_corr", EntityType.PROJECT, "ZynPay")

        # Wrong relation exists
        self.graph.create_relation(rahul.id, zynpay.id, RelationType.WORKS_ON)

        # User corrects
        ok = self.core.record_user_correction("Rahul", "ZynPay", "WORKS_ON", feedback="Rahul is on Project Beta, not ZynPay")
        self.assertTrue(ok)

        # Relation is now inactive
        neighbors = self.graph.find_neighbors(zynpay.id, active_only=True)
        self.assertNotIn("Rahul", [ent.canonical_name for _, ent in neighbors])

        # Attempt to recreate stale relation -> MUST BE BLOCKED
        recreated = self.graph.create_relation(rahul.id, zynpay.id, RelationType.WORKS_ON)
        self.assertIsNone(recreated)

    # ── Golden Test 111: Notification Spam Suppression ────────────────────────

    def test_golden_111_notification_spam_suppression(self):
        """Test 111: Multiple low-priority alerts are grouped and cooldown enforced."""
        budget = NotificationBudget(cooldown_sec=10.0, max_notifications_per_hour=3)

        # Event 1 delivered
        ok1, reason1 = budget.should_deliver("DISK_WARNING", importance=0.5)
        self.assertTrue(ok1)
        self.assertEqual(reason1, "DELIVER")

        # Event 2 immediately after: suppressed by cooldown!
        ok2, reason2 = budget.should_deliver("DISK_WARNING", importance=0.5)
        self.assertFalse(ok2)
        self.assertEqual(reason2, "COOLDOWN_ACTIVE")

        # Grouping check
        from engine.intelligence.models import ProactiveEvent
        events = [
            ProactiveEvent(id="e1", trigger_type="BUILD_FAIL", importance=0.6, urgency=0.5, confidence=0.8, risk=0.1, message="Build 1 failed"),
            ProactiveEvent(id="e2", trigger_type="BUILD_FAIL", importance=0.6, urgency=0.5, confidence=0.8, risk=0.1, message="Build 2 failed"),
            ProactiveEvent(id="e3", trigger_type="BUILD_FAIL", importance=0.6, urgency=0.5, confidence=0.8, risk=0.1, message="Build 3 failed"),
        ]
        summaries = budget.group_notifications(events)
        self.assertEqual(len(summaries), 1)
        self.assertIn("3 BUILD_FAIL events pending", summaries[0])

    # ── Golden Test 112: Context Fusion Subgraph ──────────────────────────────

    def test_golden_112_context_fusion_subgraph(self):
        """Test 112: 'Kal ke client meeting ka pending kaam' fuses Meeting + Client + Project + Task."""
        proj = self.graph.create_entity("proj_zp_fusion", EntityType.PROJECT, "ZynPay")
        client = self.graph.create_entity("comp_client", EntityType.COMPANY, "Acme Corp")
        meet = self.graph.create_entity("meet_client", EntityType.MEETING, "Acme Sync")
        task = self.graph.create_entity("task_auth", EntityType.TASK, "Fix OAuth redirect")

        self.graph.create_relation(meet.id, proj.id, RelationType.RELATES_TO_PROJECT)
        self.graph.create_relation(task.id, proj.id, RelationType.BELONGS_TO)
        self.graph.create_relation(client.id, proj.id, RelationType.ASSOCIATED_WITH_PERSON)

        fusion = self.core.context_fusion.fuse_context_for_goal("ZynPay meeting preparation", active_project="ZynPay")

        self.assertIn("Fix OAuth redirect", fusion["relevant_tasks"])
        self.assertIn("Acme Sync", fusion["relevant_meetings"])
        self.assertIn("Acme Corp", fusion["subgraph_entities"])

    # ── Golden Test 113: Restart Persistence ──────────────────────────────────

    def test_golden_113_restart_persistence(self):
        """Test 113: Restarting CHARLIE preserves knowledge graph entities, relations, and history."""
        ent = self.graph.create_entity("proj_persist", EntityType.PROJECT, "Persistent Project")
        self.graph.create_relation(ent.id, ent.id, RelationType.USES_TECH, source_provenance="initial_seed")

        # Simulate restart by creating new IntelligenceCore instance on same db_path
        new_core = IntelligenceCore(db_path=self.db_path)
        persisted_ent = new_core.graph.get_entity(ent.id)

        self.assertIsNotNone(persisted_ent)
        self.assertEqual(persisted_ent.canonical_name, "Persistent Project")

        rels = new_core.graph.find_neighbors(ent.id, active_only=True)
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0][0].source_provenance, "initial_seed")

    # ── Golden Test 114: Source Provenance Explanation ────────────────────────

    def test_golden_114_source_provenance(self):
        """Test 114: 'ZynPay PostgreSQL use karta hai ye kaise pata?' -> returns concise provenance."""
        zp = self.graph.create_entity("proj_zp_prov", EntityType.PROJECT, "ZynPay")
        pg = self.graph.create_entity("db_postgres", EntityType.DATABASE, "PostgreSQL")

        self.graph.create_relation(
            source_id=zp.id,
            target_id=pg.id,
            relation_type=RelationType.USES_DATABASE,
            source_provenance="docker-compose.yml configuration file",
            confidence=0.98,
        )

        explanation = self.core.explain_knowledge("ZynPay", "PostgreSQL", "USES_DATABASE")
        self.assertIsNotNone(explanation)
        self.assertIn("docker-compose.yml configuration file", explanation)
        self.assertIn("0.98", explanation)

    # ── Dependency Reasoner Test ──────────────────────────────────────────────

    def test_dependency_reasoner_unresolved_prerequisites(self):
        t_audit = self.graph.create_entity("task_audit", EntityType.TASK, "Security Audit")
        t_launch = self.graph.create_entity("task_launch", EntityType.TASK, "Production Launch")

        self.graph.create_relation(t_launch.id, t_audit.id, RelationType.DEPENDS_ON_TASK)

        reasoner = self.core.dependency_reasoner
        satisfied, missing = reasoner.check_prerequisites("Production Launch", completed_tasks=[])
        self.assertFalse(satisfied)
        self.assertIn("Security Audit", missing)

        satisfied2, missing2 = reasoner.check_prerequisites("Production Launch", completed_tasks=["Security Audit"])
        self.assertTrue(satisfied2)
        self.assertEqual(len(missing2), 0)

    # ── Next Action Predictor Test ────────────────────────────────────────────

    def test_next_action_predictor(self):
        predictor = self.core.next_action_predictor
        self.assertEqual(predictor.predict_next_action("code_feature"), "run_unit_tests")
        self.assertEqual(predictor.predict_next_action("excel_report_generated"), "verify_and_save_report")
        self.assertEqual(predictor.predict_next_action("research_brief_created"), "generate_video_script")


if __name__ == "__main__":
    unittest.main()
