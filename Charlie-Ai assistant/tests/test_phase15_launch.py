"""
CHARLIE Phase 15: Launch Operations & Release Management Test Suite
Verifies scope lock, multi-persona UAT, bug reproduction gates, incident containment,
deterministic Go/No-Go release decisions, staged rollouts, and launch rehearsals.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from engine.launch.models import (
    FreezeState,
    GoNoGoDecision,
    IncidentLifecycle,
    IncidentSeverity,
    IssueSeverity,
    IssueStatus,
    PilotStage,
    UATPersona,
    UATStatus,
)
from engine.launch.freeze import ReleaseFreezeManager, V1ScopeLock
from engine.launch.uat_pilot import FeedbackManager, PilotManager, UATManager
from engine.launch.triage_issues import BugTriageManager, HotfixManager, IssueRegistry
from engine.launch.support import OperationalRunbookManager, SupportManager
from engine.launch.incidents import IncidentManager
from engine.launch.readiness import (
    GoNoGoManager,
    KnownIssuesManager,
    PostLaunchMonitor,
    ReleaseReadinessManager,
    RolloutManager,
    UserCommunicationManager,
)
from engine.launch.core import LaunchOperationsPlatform
from actions.launch_control import LaunchControlActions


class TestPhase15Launch(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.platform = LaunchOperationsPlatform(data_dir=Path(self.temp_dir))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_v1_scope_lock(self):
        """Test scope lock rejects feature creep and permits bug fixes."""
        lock = self.platform.scope_lock
        # Allowed fix
        res1 = lock.validate_change("P0_BUGFIX", "Fix concurrency race condition in task scheduler")
        self.assertTrue(res1["allowed"])

        # Forbidden feature creep
        res2 = lock.validate_change("P0_BUGFIX", "Add experimental_dashboard for AI monitoring")
        self.assertFalse(res2["allowed"])
        self.assertIn("FEATURE_CREEP_DETECTED", res2["reason"])

        # Unapproved change type
        res3 = lock.validate_change("NEW_FEATURE", "Implement new connector ecosystem")
        self.assertFalse(res3["allowed"])

    def test_02_release_freeze_lifecycle(self):
        """Test freeze transitions across lifecycle states."""
        mgr = self.platform.freeze_mgr
        self.assertEqual(mgr.get_freeze_state(), FreezeState.OPEN_DEVELOPMENT)

        mgr.transition_state(FreezeState.FEATURE_FREEZE, "TechLead")
        self.assertEqual(mgr.get_freeze_state(), FreezeState.FEATURE_FREEZE)

        mgr.transition_state(FreezeState.CODE_FREEZE, "ReleaseManager")
        self.assertEqual(mgr.get_freeze_state(), FreezeState.CODE_FREEZE)

        mgr.transition_state(FreezeState.RELEASE_CANDIDATE, "QA_Lead")
        self.assertEqual(mgr.get_freeze_state(), FreezeState.RELEASE_CANDIDATE)

    def test_03_freeze_exceptions(self):
        """Test code freeze exception governance."""
        mgr = self.platform.freeze_mgr
        mgr.transition_state(FreezeState.CODE_FREEZE, "ReleaseManager")

        # P0 exception: approved
        res1 = mgr.register_freeze_exception(
            issue_id="BUG_01",
            severity=IssueSeverity.P0_CRITICAL,
            reason="Fix memory deadlock on startup",
            risk="LOW",
            approver="TechLead",
            required_tests=["test_memory_deadlock"],
        )
        self.assertTrue(res1["approved"])

        # P2 exception: rejected during code freeze
        res2 = mgr.register_freeze_exception(
            issue_id="BUG_02",
            severity=IssueSeverity.P2_MEDIUM,
            reason="Adjust button padding",
            risk="LOW",
            approver="Designer",
            required_tests=[],
        )
        self.assertFalse(res2["approved"])

    def test_04_uat_execution_and_evidence(self):
        """Test multi-persona UAT execution and evidence recording."""
        uat = self.platform.uat_mgr
        cases = uat.list_cases()
        self.assertTrue(len(cases) >= 6)

        # Execute Beginner case
        res = uat.record_uat_result(
            uat_id="UAT_BEGINNER_01",
            status=UATStatus.PASS,
            actual_behavior="Install, onboarding, and Notepad task executed with zero terminal use.",
            evidence_ref="EVID_UAT_BEGINNER_PASS",
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "PASS")

        case = uat.get_case("UAT_BEGINNER_01")
        self.assertEqual(case.status, UATStatus.PASS)
        self.assertEqual(case.user_persona, UATPersona.BEGINNER)

    def test_05_pilot_cohort_registration(self):
        """Test pilot cohort registration and cohort health evaluation."""
        pilot = self.platform.pilot_mgr
        d1 = pilot.register_device(cohort=PilotStage.DOGFOOD, ram_gb=32.0)
        d2 = pilot.register_device(cohort=PilotStage.DOGFOOD, ram_gb=16.0)

        health = pilot.evaluate_cohort_health(PilotStage.DOGFOOD)
        self.assertEqual(health["total_devices"], 2)
        self.assertEqual(health["healthy_devices"], 2)
        self.assertTrue(health["gate_passed"])

    def test_06_feedback_submission(self):
        """Test user feedback collection."""
        fb = self.platform.feedback_mgr
        item = fb.submit_feedback(category="USABILITY", description="Onboarding was smooth and fast", rating=5)
        self.assertTrue(item.feedback_id.startswith("FB_"))
        self.assertEqual(fb.get_feedback_count(), 1)

    def test_07_issue_reproduction_gate(self):
        """Test reproduction gate: cannot mark FIXED without reproduction."""
        reg = self.platform.issue_registry
        issue = reg.create_issue(
            title="Spurious voice wake during playback",
            component="voice",
            severity=IssueSeverity.P1_HIGH,
            reproduction_steps="",  # Not reproduced yet
        )

        # Attempt to mark FIXED without reproduction -> blocked
        res1 = reg.update_issue_status(issue.issue_id, IssueStatus.FIXED)
        self.assertFalse(res1["success"])
        self.assertIn("REPRODUCTION_REQUIRED", res1["reason"])

        # Now reproduce and update
        issue.reproduced = True
        res2 = reg.update_issue_status(issue.issue_id, IssueStatus.FIXED)
        self.assertTrue(res2["success"])

        # Attempt to CLOSE without verification -> blocked
        res3 = reg.update_issue_status(issue.issue_id, IssueStatus.CLOSED, evidence_ref="")
        self.assertFalse(res3["success"])
        self.assertIn("VERIFICATION_REQUIRED", res3["reason"])

        # Provide verification evidence -> closed
        res4 = reg.update_issue_status(issue.issue_id, IssueStatus.CLOSED, evidence_ref="EVID_VOICE_VERIFIED")
        self.assertTrue(res4["success"])

    def test_08_bug_triage_release_blockers(self):
        """Test bug triage blocks release if open P0 issues exist."""
        reg = self.platform.issue_registry
        triage = self.platform.triage_mgr

        # Initially clean
        status1 = triage.is_launch_blocked()
        self.assertFalse(status1["is_blocked"])

        # Create critical P0 bug
        p0_bug = reg.create_issue(
            title="Unchecked shell command execution in plugin",
            component="plugins",
            severity=IssueSeverity.P0_CRITICAL,
            reproduction_steps="Invoke untrusted plugin command",
        )

        status2 = triage.is_launch_blocked()
        self.assertTrue(status2["is_blocked"])
        self.assertEqual(status2["open_p0_count"], 1)

        # Resolve P0 bug
        reg.update_issue_status(p0_bug.issue_id, IssueStatus.VERIFIED, evidence_ref="EVID_FIX_TEST")
        reg.update_issue_status(p0_bug.issue_id, IssueStatus.CLOSED, evidence_ref="EVID_FIX_TEST")

        status3 = triage.is_launch_blocked()
        self.assertFalse(status3["is_blocked"])

    def test_09_hotfix_creation(self):
        """Test hotfix creation workflow."""
        hf_mgr = self.platform.hotfix_mgr
        plan = hf_mgr.create_hotfix_plan(
            issue_id="BUG_99",
            root_cause="Null pointer on audio stream close",
            target_version="1.0.1",
            regression_tests=["test_audio_close"],
        )
        self.assertTrue(plan["hotfix_id"].startswith("HF_"))
        self.assertEqual(plan["target_version"], "1.0.1")

    def test_10_support_self_diagnosis(self):
        """Test support self-diagnosis inspection."""
        support = self.platform.support_mgr
        diag = support.run_self_diagnosis()
        self.assertTrue(diag["all_healthy"])
        self.assertEqual(diag["core_services"], "HEALTHY")
        self.assertEqual(diag["security_core"], "ENFORCED")

    def test_11_support_bundle_redaction(self):
        """Test support bundle generation with zero secrets."""
        support = self.platform.support_mgr
        bundle = support.generate_support_bundle("App reported tool error")
        self.assertTrue(bundle["support_bundle_id"].startswith("SUP_"))
        self.assertFalse(bundle["contains_secrets"])
        self.assertTrue(bundle["redaction_verified"])

    def test_12_operational_runbooks(self):
        """Test searchable operational runbooks."""
        runbooks = self.platform.runbooks
        topics = runbooks.list_topics()
        self.assertTrue("CHARLIE_WONT_START" in topics or "JARVIS_WONT_START" in topics)
        self.assertIn("VOICE_UNAVAILABLE", topics)

        rb = runbooks.get_runbook("CHARLIE_WONT_START") or runbooks.get_runbook("JARVIS_WONT_START")
        self.assertIn("Fails to Start or Freezes on Splash", rb["title"])
        self.assertTrue(len(rb["steps"]) >= 3)

    def test_13_incident_lifecycle_and_containment(self):
        """Test incident declaration and automated containment."""
        inc_mgr = self.platform.incident_mgr
        inc = inc_mgr.declare_incident(
            title="Plugin spamming API requests",
            severity=IncidentSeverity.SEV1_MAJOR_OUTAGE,
            subsystem="plugin_manager",
        )
        self.assertEqual(inc.lifecycle, IncidentLifecycle.DETECTED)

        # Automated containment
        res = inc_mgr.execute_automated_containment(inc.incident_id)
        self.assertTrue(res["success"])
        self.assertIn("PLUGIN_QUARANTINED", res["actions_taken"])
        self.assertEqual(inc.lifecycle, IncidentLifecycle.CONTAINED)

    def test_14_incident_postmortem(self):
        """Test postmortem generation."""
        inc_mgr = self.platform.incident_mgr
        inc = inc_mgr.declare_incident(
            title="Update download timeout",
            severity=IncidentSeverity.SEV2_FEATURE_DEGRADED,
            subsystem="updates",
        )
        pm = inc_mgr.generate_postmortem(
            incident_id=inc.incident_id,
            root_cause="CDN edge server 504 gateway timeout",
            what_worked=["Automatic retry", "Core remained functional"],
            what_failed=["Staged package incomplete"],
            corrective_actions=["Add secondary CDN mirror"],
            new_tests=["test_update_mirror_fallback"],
        )
        self.assertEqual(pm.incident_id, inc.incident_id)
        self.assertEqual(inc.lifecycle, IncidentLifecycle.POSTMORTEM)

    def test_15_known_issues_catalog(self):
        """Test catalog of accepted limitations."""
        ki_mgr = self.platform.known_issues_mgr
        issues = ki_mgr.list_known_issues()
        self.assertTrue(len(issues) >= 2)
        self.assertIn("Voice Wake Word", issues[0].title)

    def test_16_go_no_go_decision(self):
        """Test deterministic Go/No-Go release decision."""
        # 1. Clean state -> CONDITIONAL_GO (due to known accepted limitations)
        rep1 = self.platform.evaluate_v1_release_decision(phase13_certified=True)
        self.assertEqual(rep1.decision, GoNoGoDecision.CONDITIONAL_GO)
        self.assertEqual(len(rep1.open_blockers), 0)

        # 2. Phase 13 NOT certified -> strict NO_GO
        rep2 = self.platform.evaluate_v1_release_decision(phase13_certified=False)
        self.assertEqual(rep2.decision, GoNoGoDecision.NO_GO)
        self.assertIn("BLOCKER_PHASE13_NOT_CERTIFIED", rep2.open_blockers)

        # 3. Open P0 bug -> strict NO_GO
        self.platform.issue_registry.create_issue(
            title="Critical memory corruption bug",
            component="memory",
            severity=IssueSeverity.P0_CRITICAL,
            reproduction_steps="Corrupt database header",
        )
        rep3 = self.platform.evaluate_v1_release_decision(phase13_certified=True)
        self.assertEqual(rep3.decision, GoNoGoDecision.NO_GO)

    def test_17_staged_rollout_progression(self):
        """Test progressive staged rollout advancing."""
        rollout = self.platform.rollout_mgr
        self.assertEqual(rollout.get_active_stage().percentage, 5)

        # Stage 1 -> Stage 2 (Pilot 20%)
        res1 = rollout.advance_stage()
        self.assertTrue(res1["success"])
        self.assertEqual(res1["percentage"], 20)

        # Stage 2 -> Stage 3 (Controlled 50%)
        res2 = rollout.advance_stage()
        self.assertTrue(res2["success"])
        self.assertEqual(res2["percentage"], 50)

        # Stage 3 -> Stage 4 (Stable 100%)
        res3 = rollout.advance_stage()
        self.assertTrue(res3["success"])
        self.assertEqual(res3["percentage"], 100)

    def test_18_rollout_auto_pause_on_anomaly(self):
        """Test rollout automatically pauses when failure rate exceeds threshold."""
        rollout = self.platform.rollout_mgr
        res = rollout.record_metrics_and_check_health(failure_rate_percent=3.5)
        self.assertEqual(res["health"], "ANOMALY_DETECTED")
        self.assertEqual(res["action"], "ROLLOUT_PAUSED")
        self.assertTrue(rollout.get_active_stage().auto_paused)

        # Attempting to advance while paused is blocked
        adv = rollout.advance_stage()
        self.assertFalse(adv["success"])
        self.assertIn("ROLLOUT_PAUSED", adv["reason"])

    def test_19_launch_rehearsal(self):
        """Test end-to-end launch rehearsal drill."""
        rehearsal = self.platform.execute_launch_rehearsal()
        self.assertEqual(rehearsal["rehearsal_status"], "SUCCESS")
        self.assertEqual(rehearsal["freeze_state"], FreezeState.CODE_FREEZE.value)
        self.assertTrue(rehearsal["support_diagnosis"]["all_healthy"])

    def test_20_launch_control_actions(self):
        """Test assistant action tool for launch operations."""
        actions = LaunchControlActions(self.platform)
        dash = actions.get_launch_dashboard()
        self.assertIn("freeze_state", dash)

        # Execute UAT case via action
        uat_res = actions.execute_uat_case("UAT_DEVELOPER_02", True, "Coding project resumed and tests passed.")
        self.assertTrue(uat_res["success"])

        # Report issue via action
        issue_res = actions.report_issue("Slow UI animation", "ui", "P3_LOW", "Open modal")
        self.assertTrue(issue_res["issue_id"].startswith("BUG_"))

        # Declare incident via action
        inc_res = actions.declare_production_incident("Audio device timeout", "SEV2_FEATURE_DEGRADED", "voice")
        self.assertEqual(inc_res["lifecycle"], "CONTAINED")

        # Evaluate decision via action
        dec = actions.evaluate_go_no_go(phase13_certified=True)
        self.assertIn(dec["decision"], ["GO", "CONDITIONAL_GO"])


if __name__ == "__main__":
    unittest.main()
