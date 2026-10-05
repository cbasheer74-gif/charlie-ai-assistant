"""Unit tests for Phase 3 Step 13: Central tool groups, shadow resolution, and filtering."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.action_loader import ActionRecord, ActionRegistry
from core.plugin_loader import PluginRecord, PluginRegistry
from core.tool_groups import (
    CONTEXTUAL_TOOLS_ENABLED,
    TOOL_GROUPS,
    TOOL_TO_GROUP,
    get_core_tools,
    get_tool_group,
    get_tools_for_group,
    get_tools_for_groups,
    is_contextual_tools_enabled,
    measure_schema_size,
    resolve_groups_for_intent,
    validate_tool_registry,
)


class TestToolGroupsRegistry(unittest.TestCase):
    """Test central tool group registry integrity, mapping, and APIs."""

    def test_canonical_core_tools_count_and_members(self):
        core = get_core_tools()
        expected = {
            "system_status",
            "undo",
            "save_memory",
            "recall_memory",
            "quick_calc",
            "open_app",
            "computer_settings",
            "media_control",
            "voice_control",
            "screen_process",
            "close_camera",
            "file_controller",
            "web_search",
            "reminder",
            "shutdown_charlie",
        }
        self.assertEqual(core, expected)
        self.assertEqual(len(core), 15)

    def test_total_mapped_tools_count(self):
        total_mapped = sum(len(tools) for tools in TOOL_GROUPS.values())
        self.assertEqual(total_mapped, 73)
        self.assertEqual(len(TOOL_TO_GROUP), 73)

    def test_get_tool_group_lookup(self):
        self.assertEqual(get_tool_group("system_status"), "CORE")
        self.assertEqual(get_tool_group("file_catalog"), "FILES")
        self.assertEqual(get_tool_group("dev_agent"), "DEVELOPER")
        self.assertEqual(get_tool_group("browser_control"), "WEB_EXTENDED")
        self.assertEqual(get_tool_group("spotify_integration"), "PLUGINS")
        self.assertIsNone(get_tool_group("nonexistent_tool_xyz"))

    def test_get_tools_for_group(self):
        files_tools = get_tools_for_group("FILES")
        self.assertIn("file_catalog", files_tools)
        self.assertIn("file_organizer", files_tools)
        self.assertIn("file_processor", files_tools)
        self.assertIn("excel_worker", files_tools)

        # Case-insensitive
        self.assertEqual(get_tools_for_group("files"), files_tools)

        # Unknown group fails safely
        self.assertEqual(get_tools_for_group("UNKNOWN_GROUP_XYZ"), set())

    def test_get_tools_for_groups_combines_correctly(self):
        combined = get_tools_for_groups(["FILES", "DEVELOPER"], include_core=True)
        self.assertTrue(get_core_tools().issubset(combined))
        self.assertIn("file_processor", combined)
        self.assertIn("dev_agent", combined)

        # Developer filter does not unexpectedly include destructive system tools
        dev_only = get_tools_for_groups(["DEVELOPER"], include_core=False)
        self.assertNotIn("shutdown_charlie", dev_only)
        self.assertNotIn("computer_settings", dev_only)

    def test_registry_validation(self):
        # All 73 tools present
        all_tools = set(TOOL_TO_GROUP.keys())
        val = validate_tool_registry(all_tools)
        self.assertTrue(val["is_valid"])
        self.assertEqual(val["unmapped"], [])
        self.assertEqual(val["missing_tools"], [])
        self.assertEqual(val["core_missing"], [])

        # Missing core tool detected
        tampered = all_tools - {"undo"}
        val_bad = validate_tool_registry(tampered)
        self.assertFalse(val_bad["is_valid"])
        self.assertIn("undo", val_bad["core_missing"])

        # Unmapped tool reported safely
        with_extra = all_tools | {"brand_new_experimental_tool"}
        val_extra = validate_tool_registry(with_extra)
        self.assertFalse(val_extra["is_valid"])
        self.assertIn("brand_new_experimental_tool", val_extra["unmapped"])


class TestActionLoaderFiltering(unittest.TestCase):
    """Test ActionRegistry filtering behavior and backward compatibility."""

    def setUp(self):
        self.mock_actions = {
            "open_app": ActionRecord(name="open_app", description="desc", parameters={"type": "OBJECT"}, valid=True),
            "quick_calc": ActionRecord(name="quick_calc", description="desc", parameters={"type": "OBJECT"}, valid=True),
            "file_catalog": ActionRecord(name="file_catalog", description="desc", parameters={"type": "OBJECT"}, valid=True),
            "dev_agent": ActionRecord(name="dev_agent", description="desc", parameters={"type": "OBJECT"}, valid=True),
            "game_room": ActionRecord(name="game_room", description="desc", parameters={"type": "OBJECT"}, valid=True),
        }
        self.registry = ActionRegistry(self.mock_actions, logger=lambda _: None)

    def test_default_loader_returns_complete_inventory(self):
        decls = self.registry.get_tool_declarations()
        names = [d["name"] for d in decls]
        self.assertEqual(sorted(names), ["dev_agent", "file_catalog", "game_room", "open_app", "quick_calc"])

    def test_filter_by_group(self):
        decls = self.registry.get_tool_declarations(allowed_groups={"CORE"})
        names = [d["name"] for d in decls]
        # open_app and quick_calc are in CORE
        self.assertIn("open_app", names)
        self.assertIn("quick_calc", names)
        self.assertNotIn("file_catalog", names)
        self.assertNotIn("dev_agent", names)

    def test_filter_by_allowed_tools(self):
        decls = self.registry.get_tool_declarations(allowed_tools={"dev_agent"})
        names = [d["name"] for d in decls]
        self.assertEqual(names, ["dev_agent"])


class TestPluginLoaderConfiguredCheck(unittest.TestCase):
    """Test PluginRegistry auth detection and filtering."""

    def test_is_configured_and_list_unconfigured(self):
        rec_configured = PluginRecord(
            name="spotify_integration",
            valid=True,
            settings={
                "namespace": "spotify_integration",
                "fields": [{"key": "client_id"}],
            },
        )
        rec_unconfigured = PluginRecord(
            name="github_integration",
            valid=True,
            settings={
                "namespace": "github_integration",
                "fields": [{"key": "token"}],
            },
        )
        rec_no_settings = PluginRecord(
            name="simple_helper",
            valid=True,
            settings=None,
        )

        plugins = {
            "spotify_integration": rec_configured,
            "github_integration": rec_unconfigured,
            "simple_helper": rec_no_settings,
        }
        registry = PluginRegistry(plugins, logger=lambda _: None)

        with patch("core.plugin_loader.get_plugin_enabled", return_value=True), \
             patch("core.plugin_loader.get_plugin_config") as mock_cfg:
            def cfg_side_effect(ns):
                if ns == "spotify_integration":
                    return {"client_id": "valid_client_id_123"}
                return {}
            mock_cfg.side_effect = cfg_side_effect

            self.assertTrue(registry.is_configured("spotify_integration"))
            self.assertFalse(registry.is_configured("github_integration"))
            self.assertTrue(registry.is_configured("simple_helper"))

            unconf = registry.list_unconfigured_plugins()
            self.assertIn("github_integration", unconf)
            self.assertNotIn("spotify_integration", unconf)

            # Default returns all enabled (backward compatibility)
            all_decls = registry.get_tool_declarations(only_configured=False)
            self.assertEqual(len(all_decls), 3)

            # Filtered returns only configured
            conf_decls = registry.get_tool_declarations(only_configured=True)
            conf_names = [d["name"] for d in conf_decls]
            self.assertIn("spotify_integration", conf_names)
            self.assertIn("simple_helper", conf_names)
            self.assertNotIn("github_integration", conf_names)


class TestIntentResolver(unittest.TestCase):
    """Test deterministic intent to tool-group resolution."""

    def test_intent_files(self):
        res = resolve_groups_for_intent("find invoice PDF")
        self.assertIn("FILES", res)
        self.assertIn("CORE", res)

    def test_intent_desktop(self):
        res = resolve_groups_for_intent("open Chrome")
        self.assertIn("DESKTOP", res)
        self.assertIn("CORE", res)

    def test_intent_vision(self):
        res = resolve_groups_for_intent("read screenshot")
        self.assertIn("VISION_EXTENDED", res)
        self.assertIn("CORE", res)

    def test_intent_developer(self):
        res = resolve_groups_for_intent("fix Python code")
        self.assertIn("DEVELOPER", res)
        self.assertIn("CORE", res)

    def test_intent_multi_group(self):
        res = resolve_groups_for_intent("find invoice and email it")
        self.assertIn("FILES", res)
        self.assertIn("COMMUNICATION", res)
        self.assertIn("CORE", res)

    def test_intent_ambiguous_normal_chat(self):
        res = resolve_groups_for_intent("hello how are you doing today")
        self.assertEqual(res, {"CORE"})

        res_empty = resolve_groups_for_intent("")
        self.assertEqual(res_empty, {"CORE"})


class TestShadowModeAndSchemaMeasurement(unittest.TestCase):
    """Test shadow mode toggle and schema measurement helpers."""

    def test_shadow_mode_defaults_to_false(self):
        self.assertFalse(CONTEXTUAL_TOOLS_ENABLED)
        self.assertFalse(is_contextual_tools_enabled())

    def test_schema_measurement_helper(self):
        mock_decls = [
            {"name": "tool1", "description": "desc1", "parameters": {"type": "OBJECT"}},
            {"name": "tool2", "description": "desc2", "parameters": {"type": "OBJECT"}},
        ]
        measured = measure_schema_size(mock_decls)
        self.assertEqual(measured["count"], 2)
        self.assertGreater(measured["json_chars"], 50)
        self.assertGreater(measured["json_bytes"], 50)


class TestPluginsIntentAndGatewayResolution(unittest.TestCase):
    """Test Phase 3 Step 18: PLUGINS intent recognition, provider ranking, and false-positive guards."""

    def test_github_intent(self):
        res = resolve_groups_for_intent("check my GitHub issues")
        self.assertIn("PLUGINS", res)

    def test_jira_intent(self):
        res = resolve_groups_for_intent("create a Jira ticket")
        self.assertIn("PLUGINS", res)

    def test_slack_intent(self):
        res = resolve_groups_for_intent("post this to Slack")
        self.assertIn("PLUGINS", res)
        self.assertIn("COMMUNICATION", res)

    def test_notion_intent(self):
        res = resolve_groups_for_intent("save this in Notion")
        self.assertIn("PLUGINS", res)

    def test_google_drive_mixed_intent(self):
        res = resolve_groups_for_intent("upload this file to Google Drive")
        self.assertIn("FILES", res)
        self.assertIn("PLUGINS", res)

    def test_developer_github_mixed_intent(self):
        res = resolve_groups_for_intent("diagnose this Python problem and create a GitHub issue")
        self.assertIn("DEVELOPER", res)
        self.assertIn("PLUGINS", res)

    def test_generic_file_no_plugins_false_positive(self):
        res = resolve_groups_for_intent("find my invoice")
        self.assertIn("FILES", res)
        self.assertNotIn("PLUGINS", res)

    def test_generic_productivity_no_plugins_false_positive(self):
        res = resolve_groups_for_intent("write meeting notes")
        self.assertIn("PRODUCTIVITY", res)
        self.assertNotIn("PLUGINS", res)

    def test_generic_message_no_plugins_false_positive(self):
        res = resolve_groups_for_intent("send a message")
        self.assertIn("COMMUNICATION", res)
        self.assertNotIn("PLUGINS", res)

    def test_unconfigured_plugin_filtering_and_configured_discovery(self):
        from core.tool_gateway import discover_candidates
        from core.plugin_loader import PluginRecord, PluginRegistry

        mock_plugins = {
            "github_integration": PluginRecord(
                name="github_integration",
                description="Manage GitHub repositories and issues.",
                valid=True,
                settings={"namespace": "github_integration", "fields": [{"key": "token"}]},
            ),
            "jira_integration": PluginRecord(
                name="jira_integration",
                description="Create and track Jira tickets.",
                valid=True,
                settings={"namespace": "jira_integration", "fields": [{"key": "api_token"}]},
            ),
            "notion_integration": PluginRecord(
                name="notion_integration",
                description="Manage Notion pages and databases.",
                valid=True,
                settings={"namespace": "notion_integration", "fields": [{"key": "token"}]},
            ),
        }
        plugin_reg = PluginRegistry(mock_plugins, logger=lambda _: None)

        with patch.object(plugin_reg, "is_configured") as mock_conf:
            # Only Jira is configured; GitHub and Notion are unconfigured
            mock_conf.side_effect = lambda name: name == "jira_integration"

            # A. Unconfigured GitHub must NOT be returned
            candidates_git = discover_candidates(
                intent="check my GitHub issues",
                session_id="test_step18_session",
                plugin_registry=plugin_reg,
            )
            git_names = [c["tool_name"] for c in candidates_git]
            self.assertNotIn("github_integration", git_names)

            # B. Configured Jira MUST be returned
            candidates_jira = discover_candidates(
                intent="create a Jira ticket",
                session_id="test_step18_session",
                plugin_registry=plugin_reg,
            )
            jira_names = [c["tool_name"] for c in candidates_jira]
            self.assertIn("jira_integration", jira_names)
            self.assertEqual(jira_names[0], "jira_integration")

            # C. Discovery candidate count <= 5
            self.assertLessEqual(len(candidates_jira), 5)


if __name__ == "__main__":
    unittest.main()
