"""Unit and regression tests for Groq provider integration in CHARLIE.

Validates:
A. Provider and model registration in ModelIntelligenceLayer and ModelRegistry.
B. Missing API key handling (graceful failure, no crashes).
C. Successful mocked chat completion and streaming.
D. API failure isolation and fallback handling (auth, rate limits, timeouts).
E. Gemini remains the default provider and behavior is unchanged.
F. Gemini Live voice pipeline is isolated from Groq.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure paths
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.groq_client import (
    DEPRECATED_MODELS,
    GROQ_FAST_MODEL,
    GROQ_PRIMARY_MODEL,
    chat_text,
    format_messages,
    get_groq_client,
    is_configured,
    resolve_model,
    stream_chat,
)
from engine.ai.core import ModelIntelligenceLayer
from engine.ai.models import DeploymentType, ModelCapability, ModelSpec
from engine.ai.providers import GroqProvider
from engine.hybrid_brain import HybridBrain


class TestGroqProvider(unittest.TestCase):
    """Test suite for Groq provider integration."""

    def setUp(self):
        # Clear any env var overrides before each test
        self.original_groq_env = os.environ.get("GROQ_API_KEY")
        if "GROQ_API_KEY" in os.environ:
            del os.environ["GROQ_API_KEY"]

    def tearDown(self):
        if self.original_groq_env is not None:
            os.environ["GROQ_API_KEY"] = self.original_groq_env
        elif "GROQ_API_KEY" in os.environ:
            del os.environ["GROQ_API_KEY"]

    # --------------------------------------------------------------------------
    # A. Provider Registration
    # --------------------------------------------------------------------------
    def test_a1_provider_registration_in_layer(self):
        """Test GroqProvider is registered in ModelIntelligenceLayer provider registry."""
        layer = ModelIntelligenceLayer()
        provider = layer.provider_registry.get_provider("groq")
        self.assertIsNotNone(provider)
        self.assertIsInstance(provider, GroqProvider)

    def test_a2_model_registry_contains_groq_models(self):
        """Test ModelRegistry registers groq_primary and groq_fast models."""
        layer = ModelIntelligenceLayer()
        primary = layer.model_registry.get_model("groq_primary")
        fast = layer.model_registry.get_model("groq_fast")

        self.assertIsNotNone(primary)
        self.assertEqual(primary.provider, "groq")
        self.assertEqual(primary.deployment_type, DeploymentType.CLOUD)
        self.assertTrue(primary.has_capability(ModelCapability.CHAT))
        self.assertTrue(primary.has_capability(ModelCapability.CODING))

        self.assertIsNotNone(fast)
        self.assertEqual(fast.provider, "groq")
        self.assertTrue(fast.has_capability(ModelCapability.FAST_CLASSIFICATION))

    def test_a3_model_guidance_constants(self):
        """Test production model constants adhere to current guidance and forbid deprecated models."""
        self.assertEqual(GROQ_PRIMARY_MODEL, "openai/gpt-oss-120b")
        self.assertEqual(GROQ_FAST_MODEL, "openai/gpt-oss-20b")

        # Verify deprecated model strings are remapped
        self.assertEqual(resolve_model("llama-3.3-70b-versatile"), GROQ_PRIMARY_MODEL)
        self.assertEqual(resolve_model("llama-3.1-8b-instant"), GROQ_FAST_MODEL)

    def test_a4_gemini_priority_remains_higher_than_groq(self):
        """Test Gemini default priority exceeds Groq priority."""
        layer = ModelIntelligenceLayer()
        gemini_strong = layer.model_registry.get_model("cloud_strong_reasoning")
        groq_primary = layer.model_registry.get_model("groq_primary")

        gemini_fast = layer.model_registry.get_model("cloud_fast_cheap")
        groq_fast = layer.model_registry.get_model("groq_fast")

        self.assertGreater(gemini_strong.priority, groq_primary.priority)
        self.assertGreater(gemini_fast.priority, groq_fast.priority)

    # --------------------------------------------------------------------------
    # B. Missing API Key
    # --------------------------------------------------------------------------
    def test_b1_missing_api_key_handling(self):
        """Test unconfigured API key fails gracefully without raising exceptions."""
        with patch("memory.config_manager.load_api_keys", return_value={}):
            self.assertFalse(is_configured())
            # chat_text must return empty string safely
            res = chat_text([{"role": "user", "content": "Hello"}])
            self.assertEqual(res, "")

    def test_b2_groq_provider_missing_key_health_check(self):
        """Test health check returns False when key is missing."""
        with patch("memory.config_manager.load_api_keys", return_value={}):
            provider = GroqProvider()
            self.assertFalse(provider.health_check())

    def test_b3_groq_provider_generate_missing_key_raises_connection_error(self):
        """Test GroqProvider.generate raises clean ConnectionError for fallback manager."""
        with patch("memory.config_manager.load_api_keys", return_value={}):
            provider = GroqProvider()
            spec = ModelSpec(
                model_id="groq_primary",
                provider="groq",
                display_name="Groq Primary",
                deployment_type=DeploymentType.CLOUD,
            )
            with self.assertRaises(ConnectionError):
                provider.generate(spec, "Test prompt")

    # --------------------------------------------------------------------------
    # C. Successful Mocked Completion
    # --------------------------------------------------------------------------
    def test_c1_message_formatting(self):
        """Test message conversion from Charlie format to Groq format."""
        charlie_msgs = [
            {"role": "user", "content": "How are you?"},
            {"role": "model", "content": "I am Charlie."},
            {"role": "assistant", "content": "Ready to help."},
            {"role": "user", "content": "Write code."},
        ]
        formatted = format_messages(charlie_msgs, system="System prompt here.")
        self.assertEqual(formatted[0], {"role": "system", "content": "System prompt here."})
        self.assertEqual(formatted[1], {"role": "user", "content": "How are you?"})
        self.assertEqual(formatted[2], {"role": "assistant", "content": "I am Charlie."})
        self.assertEqual(formatted[3], {"role": "assistant", "content": "Ready to help."})
        self.assertEqual(formatted[4], {"role": "user", "content": "Write code."})

    @patch("core.groq_client.get_groq_client")
    def test_c2_successful_mocked_completion(self, mock_get_client):
        """Test successful chat completion via Groq."""
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "Mocked Groq Answer"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        reply = chat_text([{"role": "user", "content": "Hi"}], key="mock-groq-key-12345")
        self.assertEqual(reply, "Mocked Groq Answer")

    @patch("core.groq_client.get_groq_client")
    def test_c3_groq_provider_generate_success(self, mock_get_client):
        """Test GroqProvider.generate returns compliant dictionary with token counts."""
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "Provider reply"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage.prompt_tokens = 25
        mock_response.usage.completion_tokens = 10
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        provider = GroqProvider(api_key="mock-key-123456789")
        spec = ModelSpec(
            model_id="groq_primary",
            provider="groq",
            display_name="Groq Primary",
            deployment_type=DeploymentType.CLOUD,
            cost_per_1k_input=0.0005,
            cost_per_1k_output=0.0015,
        )
        res = provider.generate(spec, "Explain quantum physics", system_prompt="You are Charlie.")
        self.assertEqual(res["text"], "Provider reply")
        self.assertEqual(res["provider"], "groq")
        self.assertEqual(res["model_id"], GROQ_PRIMARY_MODEL)
        self.assertEqual(res["input_tokens"], 25)
        self.assertEqual(res["output_tokens"], 10)
        self.assertGreater(res["cost_usd"], 0.0)

    @patch("core.groq_client.get_groq_client")
    def test_c4_streaming_success(self, mock_get_client):
        """Test stream_chat yields text deltas."""
        mock_client = MagicMock()
        chunk1 = MagicMock()
        chunk1.choices = [MagicMock(delta=MagicMock(content="Hello "))]
        chunk2 = MagicMock()
        chunk2.choices = [MagicMock(delta=MagicMock(content="World!"))]
        mock_client.chat.completions.create.return_value = iter([chunk1, chunk2])
        mock_get_client.return_value = mock_client

        tokens = list(stream_chat([{"role": "user", "content": "hi"}], key="test-key-12345"))
        self.assertEqual("".join(tokens), "Hello World!")

    # --------------------------------------------------------------------------
    # D. API Failure Graceful Fallback / Controlled Error
    # --------------------------------------------------------------------------
    @patch("core.groq_client.get_groq_client")
    def test_d1_api_rate_limit_failure_isolated(self, mock_get_client):
        """Test RateLimitError does not crash Charlie and returns empty string."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("Rate limit reached 429")
        mock_get_client.return_value = mock_client

        # chat_text must not raise
        reply = chat_text([{"role": "user", "content": "Test"}], key="mock-key-1234567")
        self.assertEqual(reply, "")

    @patch("core.groq_client.get_groq_client")
    def test_d2_timeout_isolated(self, mock_get_client):
        """Test API timeout is caught and isolated."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = TimeoutError("Timed out")
        mock_get_client.return_value = mock_client

        reply = chat_text([{"role": "user", "content": "Test"}], key="mock-key-1234567")
        self.assertEqual(reply, "")

    @patch("core.groq_client.get_groq_client")
    def test_d3_malformed_response_isolated(self, mock_get_client):
        """Test response with empty choices does not cause IndexError."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = []  # Empty choices
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        reply = chat_text([{"role": "user", "content": "Test"}], key="mock-key-1234567")
        self.assertEqual(reply, "")

    # --------------------------------------------------------------------------
    # E. Gemini Default Behavior Unchanged
    # --------------------------------------------------------------------------
    def test_e1_hybrid_brain_cloud_generate_uses_gemini_by_default(self):
        """Test HybridBrain._cloud_generate uses Gemini by default and does not call Groq when Gemini succeeds."""
        with patch("core.gemini.chat_text", return_value="Gemini cloud response") as mock_gemini, \
             patch("core.groq_client.chat_text", return_value="Groq response") as mock_groq, \
             patch("memory.config_manager.load_api_keys", return_value={"cloud_provider": "gemini"}):

            reply = HybridBrain._cloud_generate("system prompt", [{"role": "user", "content": "What is AI?"}])
            self.assertEqual(reply, "Gemini cloud response")
            mock_gemini.assert_called_once()
            mock_groq.assert_not_called()

    def test_e2_hybrid_brain_cloud_generate_falls_back_to_groq_if_gemini_fails(self):
        """Test HybridBrain._cloud_generate falls back to Groq if Gemini returns empty and Groq is ready."""
        with patch("core.gemini.chat_text", return_value="") as mock_gemini, \
             patch("core.groq_client.is_configured", return_value=True), \
             patch("core.groq_client.chat_text", return_value="Groq fallback answer") as mock_groq, \
             patch("memory.config_manager.load_api_keys", return_value={}):

            reply = HybridBrain._cloud_generate("system", [{"role": "user", "content": "Help me"}])
            self.assertEqual(reply, "Groq fallback answer")
            mock_gemini.assert_called_once()
            mock_groq.assert_called_once()

    # --------------------------------------------------------------------------
    # F. Gemini Live Voice Untouched
    # --------------------------------------------------------------------------
    def test_f1_gemini_live_voice_unaffected_by_groq(self):
        """Test that Gemini Live voice pipeline has zero invocation of Groq."""
        with patch("core.groq_client.chat_text") as mock_groq_chat:
            # Simulate a Live turn through core.gemini._live_call mock
            with patch("core.gemini._live_call", return_value=MagicMock(text="Live voice transcript")):
                from core.gemini import chat_text as gemini_chat_text
                with patch("core.gemini.api_key", return_value="fake-gemini-key"):
                    res = gemini_chat_text([{"role": "user", "content": "hello"}], system="Be helpful")
                    self.assertEqual(res, "Live voice transcript")
            mock_groq_chat.assert_not_called()


if __name__ == "__main__":
    unittest.main()
