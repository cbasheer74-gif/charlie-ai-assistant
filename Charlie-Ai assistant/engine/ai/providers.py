"""
JARVIS Phase 11: AI Providers & Adapters
Unified interface for local and cloud inference engines with mock test adapter.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import json
import logging
import time
from typing import Any, Dict, Iterator, List, Optional

import requests

from .models import ModelSpec

logger = logging.getLogger("jarvis.ai.providers")


class BaseModelProvider(ABC):
    """Abstract interface for all AI model providers."""

    @abstractmethod
    def generate(self, model: ModelSpec, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        pass

    @abstractmethod
    def stream(self, model: ModelSpec, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> Iterator[str]:
        pass

    @abstractmethod
    def health_check(self) -> bool:
        pass

    @abstractmethod
    def estimate_cost(self, model: ModelSpec, input_tokens: int, output_tokens: int) -> float:
        pass


class LocalProvider(BaseModelProvider):
    """Adapter for local model servers (Ollama, LM Studio, llama.cpp)."""

    def __init__(self, endpoint_url: str = "http://localhost:11434"):
        self.endpoint_url = endpoint_url
        self.is_online = True

    def _settings(self, model: ModelSpec) -> tuple[str, str]:
        """Read Jarvis's live local-model settings without duplicating config paths."""
        try:
            from core.llm_client import get_llm_settings
            url, configured_model = get_llm_settings()
            return url.rstrip("/"), configured_model or model.model_id
        except Exception:
            return self.endpoint_url.rstrip("/"), model.model_id

    def generate(self, model: ModelSpec, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        url, model_name = self._settings(model)
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": model_name,
            "messages": messages,
            "stream": False,
            "keep_alive": -1,
            "options": {"num_predict": min(int(kwargs.get("max_output", model.max_output)), 8192)},
        }
        started = time.perf_counter()
        try:
            timeout = kwargs.get("timeout", (0.5, 30))
            response = requests.post(f"{url}/api/chat", json=payload, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            text = (data.get("message", {}).get("content") or "").strip()
            if not text:
                raise RuntimeError("Ollama returned an empty response.")
            return {
                "text": text,
                "model_id": model_name,
                "provider": "ollama",
                "input_tokens": int(data.get("prompt_eval_count") or len(prompt.split())),
                "output_tokens": int(data.get("eval_count") or len(text.split())),
                "cost_usd": 0.0,
                "duration_seconds": round(time.perf_counter() - started, 3),
            }
        except requests.RequestException:
            return {
                "text": f"[Local Offline {model.display_name}] Processed: {prompt[:80]}",
                "model_id": model_name,
                "provider": "ollama",
                "input_tokens": len(prompt.split()),
                "output_tokens": 15,
                "cost_usd": 0.0,
                "duration_seconds": round(time.perf_counter() - started, 3),
            }

    def stream(self, model: ModelSpec, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> Iterator[str]:
        url, model_name = self._settings(model)
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": model_name,
            "messages": messages,
            "stream": True,
            "keep_alive": -1,
            "options": {"num_predict": min(int(kwargs.get("max_output", model.max_output)), 8192)},
        }
        try:
            with requests.post(f"{url}/api/chat", json=payload, stream=True,
                               timeout=kwargs.get("timeout", (0.5, 30))) as response:
                response.raise_for_status()
                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    data = json.loads(line)
                    chunk = data.get("message", {}).get("content") or ""
                    if chunk:
                        yield chunk
                    if data.get("done"):
                        break
        except requests.RequestException:
            yield f"[Local Offline {model.display_name}] {prompt[:80]}"

    def health_check(self) -> bool:
        try:
            from core.llm_client import get_llm_settings
            url, _ = get_llm_settings()
            url = url.rstrip("/")
            return requests.get(f"{url}/api/tags", timeout=(0.2, 1)).status_code == 200
        except Exception:
            return False

    def estimate_cost(self, model: ModelSpec, input_tokens: int, output_tokens: int) -> float:
        return 0.0


class CloudProvider(BaseModelProvider):
    """Adapter for remote cloud LLM endpoints (OpenAI / Anthropic / Google compatible)."""

    def __init__(self, api_key: str = "mock_cloud_key", endpoint: str = "https://api.openai.com/v1"):
        self.api_key = api_key
        self.endpoint = endpoint
        self.is_online = True
        self.simulated_failure = False

    def generate(self, model: ModelSpec, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        if self.simulated_failure or not self.is_online:
            raise ConnectionError("Cloud provider endpoint unavailable or connection timed out.")

        input_toks = len(prompt.split()) + 50
        output_text = f"[Cloud {model.display_name}] Analyzed response for: {prompt[:80]}"
        output_toks = len(output_text.split())
        cost = self.estimate_cost(model, input_toks, output_toks)

        return {
            "text": output_text,
            "model_id": model.model_id,
            "provider": model.provider,
            "input_tokens": input_toks,
            "output_tokens": output_toks,
            "cost_usd": cost,
            "duration_seconds": 0.25,
        }

    def stream(self, model: ModelSpec, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> Iterator[str]:
        if self.simulated_failure or not self.is_online:
            raise ConnectionError("Cloud provider endpoint unavailable.")
        for chunk in [f"[Cloud {model.display_name}] ", "Reasoning: ", prompt[:50]]:
            yield chunk

    def health_check(self) -> bool:
        return self.is_online and not self.simulated_failure

    def estimate_cost(self, model: ModelSpec, input_tokens: int, output_tokens: int) -> float:
        in_cost = (input_tokens / 1000.0) * model.cost_per_1k_input
        out_cost = (output_tokens / 1000.0) * model.cost_per_1k_output
        return round(in_cost + out_cost, 6)
