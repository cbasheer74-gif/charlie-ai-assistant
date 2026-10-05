"""Unit tests for Charlie Plugin Store and Download Manager."""
import tempfile
import unittest
from pathlib import Path

from core.plugin_store import (
    CATALOG,
    list_downloadable_plugins,
    install_catalog_plugin,
    install_from_code,
)
from core.plugin_loader import discover_plugins


class TestPluginStore(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.plugins_dir = Path(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_catalog_structure(self):
        self.assertGreaterEqual(len(CATALOG), 8)
        for item in CATALOG:
            self.assertIn("id", item)
            self.assertIn("title", item)
            self.assertIn("desc", item)
            self.assertIn("file", item)
            self.assertIn("code", item)

    def test_list_downloadable_plugins(self):
        items = list_downloadable_plugins(self.plugins_dir)
        self.assertEqual(len(items), len(CATALOG))
        for item in items:
            self.assertFalse(item["installed"])

    def test_install_catalog_plugin(self):
        ok, msg = install_catalog_plugin("weather_radar", self.plugins_dir)
        self.assertTrue(ok)
        self.assertTrue((self.plugins_dir / "weather_radar.py").exists())

        # Verify it now shows as installed
        items = list_downloadable_plugins(self.plugins_dir)
        weather_item = next(it for it in items if it["id"] == "weather_radar")
        self.assertTrue(weather_item["installed"])

    def test_install_from_code(self):
        custom_code = '''
PLUGIN = {
    "name": "custom_echo",
    "description": "Echo test",
    "parameters": {"type": "OBJECT", "properties": {}},
}

def run(parameters):
    return "custom response"
'''
        ok, msg = install_from_code("custom_echo.py", custom_code, self.plugins_dir)
        self.assertTrue(ok)
        self.assertTrue((self.plugins_dir / "custom_echo.py").exists())

        # Test discovery on the dynamically installed plugin
        registry = discover_plugins(self.plugins_dir, set(), lambda m: None)
        self.assertIn("custom_echo", registry._plugins)


if __name__ == "__main__":
    unittest.main()
