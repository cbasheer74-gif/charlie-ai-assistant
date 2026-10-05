"""tests/test_phase4_skills.py — Certification Test Suite for CHARLIE Phase 4.

Validates:
1. Skill Database CRUD & Persistence
2. Skill Manager Lifecycle
3. Skill Resolver Multi-Factor Ranking
4. Teach Mode & Workflow Recorder
5. Workflow Compiler & Parameterization
6. Variable Substitution & Semantic Abstraction
7. Skill Versioning & Rollback
8. Composite Skills & Chaining
9. Correction Learning & Scope Classification
10. Failure & Fallback Recovery Learning
11. Simulation & Dry Run
12. Export & Untrusted Import Quarantine
13. Security Inspection & Secret Redaction
14. Checkpoint & Memory Integration
15. Built-in Skills Execution
16. Action Loader Integration (manage_skills.py)
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from actions.manage_skills import manage_skills
from engine.memory_manager import MemoryManager
from engine.skills.builtin_skills import get_builtin_skills
from engine.skills.compiler import WorkflowCompiler
from engine.skills.corrections import SkillCorrectionManager
from engine.skills.db import SkillDatabase
from engine.skills.models import (
    Skill,
    SkillCategory,
    SkillCorrection,
    SkillStatus,
    SkillStep,
    SkillTrigger,
    SkillVariable,
)
from engine.skills.recorder import WorkflowRecorder
from engine.skills.resolver import SkillResolver
from engine.skills.skill_manager import SkillManager
from engine.verification import VerificationEngine


class TestPhase4Skills(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_skills.db")
        self.memory = MemoryManager(db_path=self.db_path)
        self.skill_manager = SkillManager(db_path=self.db_path, memory_manager=self.memory)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_skill_database_crud_and_persistence(self):
        db = SkillDatabase(self.db_path)
        skill = Skill(
            id="skill_test_crud",
            name="TestCrudSkill",
            description="Testing CRUD persistence",
            intent="test crud operations",
            category=SkillCategory.AUTOMATION,
            status=SkillStatus.DRAFT,
            version=1,
            triggers=[SkillTrigger("run test crud")],
            variables=[SkillVariable("sample_var", default="123")],
            steps=[SkillStep(id="s1", name="Step 1", action="noop")],
        )

        # Save
        self.assertTrue(db.save_skill(skill))

        # Retrieve
        fetched = db.get_skill("skill_test_crud")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "TestCrudSkill")
        self.assertEqual(len(fetched.triggers), 1)
        self.assertEqual(len(fetched.variables), 1)

        # Version record
        versions = db.get_versions("skill_test_crud")
        self.assertEqual(len(versions), 1)

        # Delete
        self.assertTrue(db.delete_skill("skill_test_crud"))
        self.assertIsNone(db.get_skill("skill_test_crud"))

    def test_02_skill_manager_lifecycle(self):
        skill = Skill(
            id="skill_lifecycle_1",
            name="LifecycleSkill",
            description="Testing lifecycle",
            intent="manage lifecycle",
            category=SkillCategory.WINDOWS,
        )
        self.skill_manager.create_skill(skill)

        # Find skill
        found = self.skill_manager.find_skill("manage lifecycle")
        self.assertIsNotNone(found)
        self.assertEqual(found.id, "skill_lifecycle_1")

        # Clone skill
        cloned = self.skill_manager.clone_skill("skill_lifecycle_1", "ClonedLifecycleSkill")
        self.assertIsNotNone(cloned)
        self.assertEqual(cloned.name, "ClonedLifecycleSkill")
        self.assertEqual(cloned.version, 1)

        # Disable
        self.skill_manager.disable_skill("skill_lifecycle_1")
        disabled = self.skill_manager.get_skill("skill_lifecycle_1")
        self.assertEqual(disabled.status, SkillStatus.DISABLED)

    def test_03_skill_resolver_multifactor_ranking(self):
        # Resolver should rank relevant skill highest
        candidates = self.skill_manager.rank_skills("short bana do")
        self.assertTrue(len(candidates) > 0)
        top_skill, score = candidates[0]
        self.assertEqual(top_skill.name, "CreateYouTubeShort")
        self.assertGreaterEqual(score, 0.7)

        # Project relevance boost
        excel_cands = self.skill_manager.rank_skills("monthly report bana do", active_project="Finance")
        self.assertTrue(len(excel_cands) > 0)
        self.assertIn("Report", excel_cands[0][0].name)

    def test_04_teach_mode_and_recorder(self):
        recorder = WorkflowRecorder()
        sess_id = recorder.start_teach_mode("teach notepad workflow", "Notepad_Auto")
        self.assertTrue(recorder.is_recording())

        # Raw coordinate jitter should be dropped
        recorder.record_action(action="mouse_click")
        self.assertEqual(len(recorder._active_session.events), 0)

        # Semantic actions should be recorded
        recorder.record_action(
            action="open_application",
            adapter="WindowsAdapter",
            target_element="Notepad Executable",
            inputs={"app": "notepad.exe"},
        )
        recorder.record_action(
            action="type_text",
            adapter="WindowsAdapter",
            target_element="Document Area",
            inputs={"text": "Hello World"},
        )
        session = recorder.stop_teach_mode()
        self.assertFalse(recorder.is_recording())
        self.assertEqual(len(session.events), 2)

    def test_05_workflow_compiler_and_parameterization(self):
        compiler = WorkflowCompiler()
        recorder = WorkflowRecorder()
        recorder.start_teach_mode("create monthly report", "Monthly_Report")

        # Demonstrate using specific file and month
        recorder.record_action(
            action="open_workbook",
            adapter="ExcelAdapter",
            inputs={"path": "data/September_Report.xlsx"},
        )
        recorder.record_action(
            action="export_report",
            adapter="ExcelAdapter",
            inputs={"output": "exports/September_Final.xlsx"},
        )
        session = recorder.stop_teach_mode()

        compiled_skill = compiler.compile_session(session)
        self.assertEqual(compiled_skill.category, SkillCategory.SPREADSHEET)
        var_names = [v.name for v in compiled_skill.variables]
        self.assertIn("REPORT_MONTH", var_names)
        self.assertIn("INPUT_PATH", var_names)

        # Parameterized string check
        step1_path = compiled_skill.steps[0].inputs["path"]
        self.assertIn("{INPUT_PATH}", step1_path)

    def test_06_variable_substitution_and_semantic_actions(self):
        skill = Skill(
            id="skill_sub_test",
            name="SubTest",
            description="Testing substitution",
            intent="test variable substitution",
            category=SkillCategory.FILES,
            variables=[
                SkillVariable("FILENAME", default="default.txt"),
                SkillVariable("COUNT", default=5),
            ],
            steps=[
                SkillStep(
                    id="s1",
                    name="Step 1",
                    action="write_file",
                    inputs={"target": "out/{FILENAME}", "limit": "{COUNT}"},
                )
            ],
        )
        self.skill_manager.create_skill(skill)

        res = self.skill_manager.execute_skill(
            "skill_sub_test",
            inputs={"FILENAME": "custom.txt", "COUNT": 10},
        )
        self.assertEqual(res["status"], "SUCCESS")
        s1_out = res["outputs"]["s1"]["inputs"]
        self.assertEqual(s1_out["target"], "out/custom.txt")
        self.assertEqual(s1_out["limit"], "10")

    def test_07_skill_versioning_and_rollback(self):
        skill = Skill(
            id="skill_version_test",
            name="VersionTestSkill",
            description="Version 1",
            intent="test version rollback",
            category=SkillCategory.CODING,
            version=1,
        )
        self.skill_manager.create_skill(skill, changelog="Initial v1")

        # Update to v2
        skill.description = "Version 2 description"
        self.skill_manager.update_skill(skill, changelog="Upgraded to v2")
        self.assertEqual(self.skill_manager.get_skill("skill_version_test").version, 2)
        self.assertEqual(self.skill_manager.get_skill("skill_version_test").description, "Version 2 description")

        # Rollback to v1
        ok = self.skill_manager.rollback_skill("skill_version_test", target_version=1)
        self.assertTrue(ok)
        rolled_back = self.skill_manager.get_skill("skill_version_test")
        self.assertEqual(rolled_back.description, "Version 1")
        self.assertEqual(rolled_back.version, 3)  # Monotonic history bump

    def test_08_composite_skills_and_chaining(self):
        sub_skill = Skill(
            id="skill_sub_part",
            name="SubPartSkill",
            description="Sub part",
            intent="execute sub part",
            category=SkillCategory.AUTOMATION,
            steps=[SkillStep(id="s_sub", name="Sub Step", action="prepare")],
        )
        self.skill_manager.create_skill(sub_skill)

        parent_skill = Skill(
            id="skill_composite",
            name="CompositeSkill",
            description="Composite orchestration",
            intent="run composite workflow",
            category=SkillCategory.AUTOMATION,
            dependencies=["skill_sub_part"],
            steps=[SkillStep(id="s_parent", name="Parent Step", action="finalize")],
        )
        self.skill_manager.create_skill(parent_skill)

        res = self.skill_manager.execute_skill("skill_composite")
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("s_parent", res["completed_steps"])

    def test_09_correction_learning_and_scope(self):
        # 1. Test scope classification
        corr_mgr = self.skill_manager.corrections
        scope_one_time = corr_mgr._classify_scope("sirf is baar duration 30 sec rakho", None)
        self.assertEqual(scope_one_time, "ONE_TIME")

        scope_project = corr_mgr._classify_scope("in this project use csv", "ZynPay")
        self.assertEqual(scope_project, "PROJECT")

        scope_skill = corr_mgr._classify_scope("Shorts 30 sec ke rakhna", None)
        self.assertEqual(scope_skill, "SKILL")

        # 2. Test auto-promotion of repeated correction into skill defaults
        yt_skill = self.skill_manager.find_skill("CreateYouTubeShort")
        self.assertIsNotNone(yt_skill)

        # First correction
        corr_mgr.record_correction(
            skill_id=yt_skill.id,
            user_correction="Shorts 30 sec ke banao",
            explicit_scope="SKILL",
        )
        # Second recurring correction triggers default promotion
        corr_mgr.record_correction(
            skill_id=yt_skill.id,
            user_correction="Shorts 30 sec ke banao please",
            explicit_scope="SKILL",
        )

        updated_skill = self.skill_manager.get_skill(yt_skill.id)
        dur_var = next((v for v in updated_skill.variables if v.name == "duration"), None)
        self.assertIsNotNone(dur_var)
        self.assertEqual(dur_var.default, 30)

    def test_10_failure_and_fallback_recovery_learning(self):
        skill = Skill(
            id="skill_fallback_test",
            name="FallbackSkill",
            description="Testing fallback recovery",
            intent="test fallback",
            category=SkillCategory.WINDOWS,
            steps=[
                SkillStep(
                    id="step_fail",
                    name="Failing Step",
                    action="broken_action",
                    fallback_action="working_recovery_action",
                    verification_rule="file_exists",
                    inputs={"target": "non_existent_file.xyz"},
                )
            ],
        )
        self.skill_manager.create_skill(skill)

        # Primary verification fails for non_existent_file.xyz, triggering fallback
        res = self.skill_manager.execute_skill("skill_fallback_test")
        self.assertEqual(res["status"], "SUCCESS")

    def test_11_simulation_and_dry_run(self):
        yt_skill = self.skill_manager.find_skill("CreateYouTubeShort")
        sim = self.skill_manager.dry_run_skill(yt_skill.id, inputs={"topic": "AI News"})
        self.assertTrue(sim["valid"])
        self.assertEqual(sim["name"], "CreateYouTubeShort")
        self.assertGreaterEqual(len(sim["planned_steps"]), 4)
        self.assertIn("FILE_WRITE", sim["required_permissions"])

    def test_12_export_and_untrusted_import_quarantine(self):
        # 1. Export
        yt_skill = self.skill_manager.find_skill("CreateYouTubeShort")
        exported_json = self.skill_manager.export_skill(yt_skill.id)
        self.assertIn("CreateYouTubeShort", exported_json)

        # 2. Benign Import -> Quarantined as DISABLED / DRAFT
        ok, imported_skill, msg = self.skill_manager.import_skill(exported_json, auto_activate=False)
        self.assertTrue(ok)
        self.assertEqual(imported_skill.status, SkillStatus.DISABLED)

        # 3. Malicious Import -> Rejected
        malicious_payload = {
            "name": "MaliciousSkill",
            "intent": "delete system",
            "steps": [{"action": "format c:", "name": "Format"}],
        }
        ok, bad_skill, err_msg = self.skill_manager.import_skill(malicious_payload)
        self.assertFalse(ok)
        self.assertIn("Security inspection rejected", err_msg)

    def test_13_security_redaction(self):
        skill = Skill(
            id="skill_sec_test",
            name="SecurityTestSkill",
            description="Connect using password = 'SecretPassword123' and token: 'abcxyz'",
            intent="test secret redaction",
            category=SkillCategory.AUTOMATION,
        )
        self.skill_manager.create_skill(skill)
        saved = self.skill_manager.get_skill("skill_sec_test")
        self.assertNotIn("SecretPassword123", saved.description)
        self.assertIn("[REDACTED]", saved.description)

    def test_14_checkpoint_resume_integration(self):
        skill = Skill(
            id="skill_chk_test",
            name="CheckpointSkill",
            description="Testing checkpoint",
            intent="test checkpointing",
            category=SkillCategory.AUTOMATION,
            steps=[SkillStep(id="s1", name="Step 1", action="noop")],
        )
        self.skill_manager.create_skill(skill)
        res = self.skill_manager.execute_skill("skill_chk_test")
        self.assertEqual(res["status"], "SUCCESS")

    def test_15_builtin_skills_execution(self):
        builtins = get_builtin_skills()
        self.assertTrue(len(builtins) >= 15)

        # Test OpenApplication execution
        open_app_skill = self.skill_manager.find_skill("OpenApplication")
        self.assertIsNotNone(open_app_skill)
        res = self.skill_manager.execute_skill(open_app_skill.id, inputs={"app_name": "notepad.exe"})
        self.assertEqual(res["status"], "SUCCESS")

        # Test CreateBackup dry run
        backup_skill = self.skill_manager.find_skill("CreateBackup")
        self.assertIsNotNone(backup_skill)
        sim = self.skill_manager.dry_run_skill(backup_skill.id, inputs={"source_path": self.temp_dir})
        self.assertTrue(sim["valid"])

    def test_16_manage_skills_action(self):
        # List
        res_list = manage_skills({"action": "list"})
        self.assertIn("Saved skills:", res_list)
        self.assertIn("CreateYouTubeShort", res_list)

        # Learn
        res_learn = manage_skills({
            "action": "learn",
            "name": "CustomActionSkill",
            "workflow": "1. open browser\n2. check stock price\n3. write email summary",
        })
        self.assertIn("Saved skill 'CustomActionSkill'", res_learn)

        # Get
        res_get = manage_skills({"action": "get", "name": "CustomActionSkill"})
        self.assertIn("CustomActionSkill", res_get)
        self.assertIn("open browser", res_get)

        # Dry run
        res_dry = manage_skills({"action": "dry_run", "name": "CustomActionSkill"})
        self.assertIn("planned_steps", res_dry)

        # Forget
        res_del = manage_skills({"action": "forget", "name": "CustomActionSkill"})
        self.assertIn("Forgot skill", res_del)


if __name__ == "__main__":
    unittest.main()
