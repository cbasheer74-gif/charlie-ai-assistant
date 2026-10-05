"""engine/ai/ollama_provider.py — Local Offline LLM Engine for CHARLIE via Ollama.

Features:
- Zero-dependency local Ollama REST client.
- Auto-discovery of locally installed models (Llama 3, Mistral, Phi-3, Qwen, DeepSeek).
- Fast health checks & automatic graceful fallback when cloud APIs are unavailable.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("charlie.ollama")


@dataclass
class OllamaModelInfo:
    name: str
    size_gb: float
    modified_at: str
    family: str


class OllamaProvider:
    """Manages offline local inference through local Ollama runtime."""

    DEFAULT_HOST = "http://127.0.0.1:11434"
    PREFERRED_MODELS = [
        "llama3.2:latest",
        "llama3.1:latest",
        "llama3:latest",
        "qwen2.5:latest",
        "mistral:latest",
        "phi3:latest",
        "deepseek-r1:latest",
        "gemma2:latest",
    ]

    def __init__(self, host: str = DEFAULT_HOST, default_model: str = ""):
        self.host = host.rstrip("/")
        self.default_model = default_model
        self._cached_models: List[str] = []

    def is_available(self, timeout: float = 1.0) -> bool:
        """Checks if local Ollama daemon is running and responsive."""
        try:
            req = urllib.request.Request(f"{self.host}/api/version", headers={"User-Agent": "CHARLIE-Desktop/1.2"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status == 200
        except Exception:
            return False

    def list_models(self, timeout: float = 2.0) -> List[str]:
        """Retrieves list of installed model names from local Ollama daemon."""
        try:
            req = urllib.request.Request(f"{self.host}/api/tags", headers={"User-Agent": "CHARLIE-Desktop/1.2"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
                self._cached_models = models
                return models
        except Exception as e:
            logger.debug("Ollama list_models failed: %s", e)
            return self._cached_models

    def pick_best_model(self) -> str:
        """Selects the most capable installed model based on preference hierarchy."""
        if self.default_model:
            return self.default_model

        installed = self.list_models()
        if not installed:
            return "llama3.2:latest"

        # Match against preferred models
        for pref in self.PREFERRED_MODELS:
            for inst in installed:
                if pref.split(":")[0] in inst.lower():
                    return inst

        return installed[0]

    def generate(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        model: str = "",
        timeout: float = 45.0,
    ) -> str:
        """Sends chat messages to local Ollama chat endpoint and returns assistant response."""
        chosen_model = model or self.pick_best_model()

        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})

        for m in messages:
            formatted_messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})

        payload = {
            "model": chosen_model,
            "messages": formatted_messages,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_ctx": 4096,
            },
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "CHARLIE-Desktop/1.2",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Ollama returned HTTP {resp.status}")
                res_obj = json.loads(resp.read().decode("utf-8"))
                reply = res_obj.get("message", {}).get("content", "").strip()
                if not reply:
                    raise ValueError("Empty reply from Ollama local model.")
                return reply
        except urllib.error.URLError as e:
            raise RuntimeError(f"Ollama connection error: {e}")


# Singleton
_ollama_instance: Optional[OllamaProvider] = None


def get_ollama_provider() -> OllamaProvider:
    global _ollama_instance
    if _ollama_instance is None:
        _ollama_instance = OllamaProvider()
    return _ollama_instance
