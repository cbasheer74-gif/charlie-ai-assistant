"""Integration tests for live Teach Mode action capture and replay."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import actions.manage_skills as manage_module
from core.action_loader import ActionRecord, ActionRegistry
from engine.skills import teach_runtime
from engine.skills.skill_manager import SkillManager


class TestLiveTeachMode(unittest.TestCase):
    def setUp(self):
        teach_runtime.cancel()
        self.temp_dir = tempfile.TemporaryDirectory()
        manager = SkillManager(db_path=Path(self.temp_dir.name) / "skills.db")
        manager.recorder = teach_runtime.get_recorder()
        self.previous_manager = manage_module._SKILL_MANAGER
        self.previous_store = manage_module._STORE
        manage_module._SKILL_MANAGER = manager
        manage_module._STORE = Path(self.temp_dir.name) / "skills.json"
        self.calls = []

        def sample_action(parameters, **_unused):
            self.calls.append(dict(parameters))
            return f"Opened {parameters.get('target', 'item')}"

        records = {
            "manage_skills": ActionRecord(
                name="manage_skills", handler=manage_module.manage_skills, valid=True
            ),
            "sample_action": ActionRecord(
                name="sample_action", handler=sample_action, valid=True
            ),
        }
        self.registry = ActionRegistry(records, logger=lambda _message: None)
        self.context = {"action_registry": self.registry}

    def tearDown(self):
        teach_runtime.cancel()
        manage_module._SKILL_MANAGER = self.previous_manager
        manage_module._STORE = self.previous_store
        self.temp_dir.cleanup()

    def run_action(self, name, parameters):
        return self.registry.run(name, parameters, self.context)

    def test_records_real_action_and_replays_it(self):
        started = self.run_action("manage_skills", {
            "action": "start_teach",
            "name": "OpenDailyItem",
            "workflow": "open my daily item",
        })
        self.assertIn("TEACH MODE STARTED", started)

        self.assertEqual(self.run_action("sample_action", {"target": "notes"}), "Opened notes")
        self.assertEqual(teach_runtime.status()["event_count"], 1)

        saved = self.run_action("manage_skills", {"action": "stop_teach"})
        self.assertIn("1 real action step", saved)

        skill = manage_module._SKILL_MANAGER.get_skill_by_name("OpenDailyItem")
        self.assertIsNotNone(skill)
        self.assertEqual(skill.steps[0].tool, "sample_action")

        replayed = self.run_action("manage_skills", {
            "action": "execute", "name": "OpenDailyItem"
        })
        self.assertIn("SUCCESS", replayed)
        self.assertEqual(self.calls, [{"target": "notes"}, {"target": "notes"}])

    def test_does_not_record_failures_or_secrets(self):
        self.run_action("manage_skills", {
            "action": "start_teach", "name": "SafeWorkflow", "workflow": "safe workflow"
        })
        self.run_action("sample_action", {"target": "account", "api_key": "top-secret"})
        session = teach_runtime.get_recorder().get_current_session()
        self.assertEqual(session.events[0].inputs["api_key"], "{API_KEY}")

        teach_runtime.record_tool_call(
            "sample_action", {"target": "bad"}, "Tool failed: no", succeeded=False
        )
        self.assertEqual(teach_runtime.status()["event_count"], 1)
        self.run_action("manage_skills", {"action": "stop_teach"})
        refused = self.run_action("manage_skills", {
            "action": "execute", "name": "SafeWorkflow"
        })
        self.assertIn("Missing required workflow input(s): API_KEY", refused)

    def test_prevents_nested_recording_and_empty_save(self):
        self.run_action("manage_skills", {
            "action": "start_teach", "name": "FirstWorkflow", "workflow": "first"
        })
        nested = self.run_action("manage_skills", {
            "action": "start_teach", "name": "SecondWorkflow", "workflow": "second"
        })
        self.assertIn("already recording", nested)
        empty = self.run_action("manage_skills", {"action": "stop_teach"})
        self.assertIn("No successful", empty)


if __name__ == "__main__":
    unittest.main()
