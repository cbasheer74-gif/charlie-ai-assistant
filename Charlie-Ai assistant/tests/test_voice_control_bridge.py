"""Unit and regression tests for Phase 3 Step 9: Voice Control Runtime Bridge.

Validates:
1. Runtime registration and unregistration in core.runtime_voice_control.
2. Missing-runtime handling (graceful error message, no crash).
3. Active runtime delegation (status, mute, unmute, interrupt, wake, sleep, reconnect, set_voice, toggle_wake_word).
4. Controlled rejection of unsupported legacy actions (test_microphone, set_microphone, simulate_speech, etc.).
5. Exception isolation (runtime error handled gracefully).
6. Absolute guarantee: VoiceOrchestrator is NEVER instantiated in the action path.
7. Action loader auto-discovery compatibility (TOOL dict schema and registration).
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure paths
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.runtime_voice_control import (
    get_voice_runtime,
    register_voice_runtime,
    unregister_voice_runtime,
)
from actions.voice_control import TOOL, voice_control


class FakeCharlieRuntime:
    """Mock representing active CharlieLive runtime."""

    def __init__(self):
        self.ui = MagicMock()
        self.ui.state = "LISTENING"
        self.ui.muted = False
        self._awake = True
        self._wake_enabled = True
        self.session = MagicMock()
        self.interrupted_called = False
        self.wake_called_with = None
        self.sleep_called_with = None
        self.reconnect_called_with = None
        self.voice_change_called = False

    def interrupt(self):
        self.interrupted_called = True

    def wake(self, reason: str = ""):
        self._awake = True
        self.wake_called_with = reason

    def sleep(self, reason: str = ""):
        self._awake = False
        self.sleep_called_with = reason

    def request_reconnect(self, keep_context: bool = True, reason: str = ""):
        self.reconnect_called_with = {"keep_context": keep_context, "reason": reason}

    def _on_voice_change(self):
        self.voice_change_called = True

    def _ensure_wake_detector(self):
        pass


class TestVoiceControlBridge(unittest.TestCase):
    """Test suite for voice_control runtime bridge."""

    def setUp(self):
        unregister_voice_runtime()

    def tearDown(self):
        unregister_voice_runtime()

    # --------------------------------------------------------------------------
    # 1. Registry LifeCycle
    # --------------------------------------------------------------------------
    def test_registry_lifecycle(self):
        """Test registration, retrieval, and unregistration of runtime."""
        self.assertIsNone(get_voice_runtime())

        runtime = FakeCharlieRuntime()
        register_voice_runtime(runtime)
        self.assertIs(get_voice_runtime(), runtime)

        unregister_voice_runtime()
        self.assertIsNone(get_voice_runtime())

    # --------------------------------------------------------------------------
    # 2. Missing Runtime Handling
    # --------------------------------------------------------------------------
    def test_missing_runtime_handling(self):
        """Test action invocation when Charlie runtime is not registered."""
        self.assertIsNone(get_voice_runtime())

        res = voice_control({"action": "status"})
        self.assertIn("not registered", res)
        self.assertIn("Error", res)

        res_mute = voice_control({"action": "mute"})
        self.assertIn("not registered", res_mute)

        res_interrupt = voice_control({"action": "interrupt"})
        self.assertIn("not registered", res_interrupt)

    # --------------------------------------------------------------------------
    # 3. Real Action Delegation
    # --------------------------------------------------------------------------
    def test_status_inspection(self):
        """Test status reports actual state of registered runtime."""
        runtime = FakeCharlieRuntime()
        register_voice_runtime(runtime)

        res = voice_control({"action": "status"})
        self.assertIn("CHARLIE Active Voice Runtime Status", res)
        self.assertIn("LISTENING", res)
        self.assertIn("ACTIVE", res)
        self.assertIn("CONNECTED", res)

    def test_mute_and_unmute_delegation(self):
        """Test mute and unmute actions toggle runtime.ui.muted."""
        runtime = FakeCharlieRuntime()
        register_voice_runtime(runtime)

        # Mute
        res_mute = voice_control({"action": "mute"})
        self.assertIn("Microphone has been muted", res_mute)
        self.assertTrue(runtime.ui.muted)

        # Unmute
        res_unmute = voice_control({"action": "unmute"})
        self.assertIn("Microphone unmuted", res_unmute)
        self.assertFalse(runtime.ui.muted)

    def test_interrupt_delegation(self):
        """Test interrupt / emergency_stop calls runtime.interrupt()."""
        runtime = FakeCharlieRuntime()
        register_voice_runtime(runtime)

        res = voice_control({"action": "interrupt"})
        self.assertIn("Speech interrupted", res)
        self.assertTrue(runtime.interrupted_called)

        # Reset flag and test emergency_stop alias
        runtime.interrupted_called = False
        res_stop = voice_control({"action": "emergency_stop"})
        self.assertIn("Speech interrupted", res_stop)
        self.assertTrue(runtime.interrupted_called)

    def test_wake_and_sleep_delegation(self):
        """Test wake and sleep delegation."""
        runtime = FakeCharlieRuntime()
        register_voice_runtime(runtime)

        # Sleep
        res_sleep = voice_control({"action": "sleep"})
        self.assertIn("put to sleep", res_sleep)
        self.assertFalse(runtime._awake)
        self.assertEqual(runtime.sleep_called_with, "voice_control action")

        # Wake
        res_wake = voice_control({"action": "wake"})
        self.assertIn("now awake", res_wake)
        self.assertTrue(runtime._awake)
        self.assertEqual(runtime.wake_called_with, "voice_control action")

    def test_reconnect_delegation(self):
        """Test reconnect requests reconnect preserving context."""
        runtime = FakeCharlieRuntime()
        register_voice_runtime(runtime)

        res = voice_control({"action": "reconnect"})
        self.assertIn("Reconnecting voice session", res)
        self.assertIsNotNone(runtime.reconnect_called_with)
        self.assertTrue(runtime.reconnect_called_with["keep_context"])

    @patch("memory.config_manager.save_voice")
    def test_set_voice_delegation(self, mock_save_voice):
        """Test voice profile change delegates to save_voice and _on_voice_change."""
        runtime = FakeCharlieRuntime()
        register_voice_runtime(runtime)

        res = voice_control({"action": "set_voice", "voice": "Puck"})
        self.assertIn("Voice changed to 'Puck'", res)
        mock_save_voice.assert_called_with("Puck")
        self.assertTrue(runtime.voice_change_called)

    @patch("memory.config_manager.save_wake_word_enabled")
    def test_toggle_wake_word(self, mock_save_wake):
        """Test toggle wake word updates config and runtime state."""
        runtime = FakeCharlieRuntime()
        register_voice_runtime(runtime)

        res = voice_control({"action": "toggle_wake_word", "enabled": False})
        self.assertIn("disabled", res)
        mock_save_wake.assert_called_with(False)
        self.assertFalse(runtime._wake_enabled)

    # --------------------------------------------------------------------------
    # 4. Unsupported Legacy Actions
    # --------------------------------------------------------------------------
    def test_unsupported_legacy_actions(self):
        """Test legacy VoiceOrchestrator actions return controlled error messages."""
        runtime = FakeCharlieRuntime()
        register_voice_runtime(runtime)

        for act in ["test_microphone", "set_microphone", "process_command", "simulate_speech"]:
            res = voice_control({"action": act})
            self.assertIn("unsupported by active Gemini Live runtime", res)

    # --------------------------------------------------------------------------
    # 5. Exception Isolation
    # --------------------------------------------------------------------------
    def test_exception_isolation(self):
        """Test runtime exception during action is caught and formatted."""
        runtime = FakeCharlieRuntime()
        runtime.interrupt = MagicMock(side_effect=RuntimeError("Audio hardware busy"))
        register_voice_runtime(runtime)

        res = voice_control({"action": "interrupt"})
        self.assertIn("Voice Control error: Audio hardware busy", res)

    # --------------------------------------------------------------------------
    # 6. Absolute Guarantee: No VoiceOrchestrator Instantiation
    # --------------------------------------------------------------------------
    @patch("engine.voice.orchestrator.VoiceOrchestrator", side_effect=AssertionError("VoiceOrchestrator must not be created!"))
    def test_no_voice_orchestrator_created(self, mock_orchestrator):
        """Verify that under no circumstances is VoiceOrchestrator instantiated in voice_control."""
        runtime = FakeCharlieRuntime()
        register_voice_runtime(runtime)

        # Call various actions
        for act in ["status", "mute", "unmute", "interrupt", "sleep", "wake", "reconnect", "test_microphone"]:
            res = voice_control({"action": act})
            self.assertIsInstance(res, str)

        mock_orchestrator.assert_not_called()

    # --------------------------------------------------------------------------
    # 7. Action Loader Tool Discovery Schema
    # --------------------------------------------------------------------------
    def test_tool_declaration_schema(self):
        """Test TOOL dictionary conforms to CHARLIE action declaration spec."""
        self.assertEqual(TOOL["name"], "voice_control")
        self.assertIn("properties", TOOL["parameters"])
        self.assertIn("action", TOOL["parameters"]["properties"])
        self.assertEqual(TOOL["handler"], voice_control)


if __name__ == "__main__":
    unittest.main()
