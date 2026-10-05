import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core import audio_devices
from core import wake_word


class StartupResponsivenessTests(unittest.TestCase):
    def test_wake_readiness_does_not_import_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            models = Path(tmp) / "resources" / "models"
            models.mkdir(parents=True)
            for name in (
                "hey_charlie.onnx",
                "melspectrogram.onnx",
                "embedding_model.onnx",
            ):
                (models / name).touch()
            spec = SimpleNamespace(
                submodule_search_locations=[tmp], origin=None)
            sys.modules.pop("openwakeword", None)
            with patch("importlib.util.find_spec", return_value=spec):
                self.assertTrue(wake_word.is_ready())
            self.assertNotIn("openwakeword", sys.modules)

    def test_resolving_saved_device_does_not_scan_all_devices(self):
        fake_sounddevice = SimpleNamespace(
            query_devices=lambda: [
                {"name": "My Speaker", "hostapi": 0,
                 "max_input_channels": 0, "max_output_channels": 2},
            ],
            query_hostapis=lambda: [{"name": "Windows WASAPI"}],
        )
        with (
            patch.dict(sys.modules, {"sounddevice": fake_sounddevice}),
            patch.object(audio_devices, "list_devices",
                         side_effect=AssertionError("full scan entered startup path")),
            patch.object(audio_devices, "_usable", return_value=True),
        ):
            self.assertEqual(audio_devices.resolve("My Speaker", "output"), 0)


if __name__ == "__main__":
    unittest.main()
