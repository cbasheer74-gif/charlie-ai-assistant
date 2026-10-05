"""Local Qwen 3.5 agent bridge for CHARLIE."""

from __future__ import annotations

from core.llm_client import check_model_available, ensure_ollama_running, get_llm_settings
from engine.ai.core import ModelIntelligenceLayer
from engine.ai.models import RoutingPolicy


_AI = ModelIntelligenceLayer()


def ollama_agent(parameters: dict, player=None, **_unused) -> str:
    params = parameters or {}
    action = str(params.get("action") or "ask").strip().lower()
    url, model = get_llm_settings()

    if action == "status":
        online = ensure_ollama_running(timeout=5)
        available = online and check_model_available()
        return (
            f"Local agent: {'online' if online else 'offline'} at {url}. "
            f"Model: {model}. {'Model is ready.' if available else f'Run: ollama pull {model}'}"
        )

    prompt = str(params.get("prompt") or params.get("task") or "").strip()
    if not prompt:
        return "Tell me what you want the local Qwen agent to do."
    if not ensure_ollama_running(timeout=10):
        return f"Ollama is not available. Install Ollama, start it, then run: ollama pull {model}"
    if not check_model_available():
        return f"The local model is not downloaded. Run: ollama pull {model}"

    role = str(params.get("role") or "general").strip().lower()
    system = (
        "You are the local Qwen 3.5 agent inside CHARLIE. Be precise, practical, "
        "and honest about what you verified. You may plan coding, research, "
        "troubleshooting, and computer tasks, but never claim to have changed "
        "the computer unless CHARLIE confirms it. Current specialist role: " + role
    )
    result = _AI.process_request(
        prompt,
        user_metadata={"agent_role": role},
        policy_override=RoutingPolicy.LOCAL_FIRST,
        user_model_override="local_qwen35",
    )
    if not result.get("success"):
        return f"Local Qwen agent failed: {result.get('error', 'unknown error')}"
    response = result.get("response") or {}
    text = response.get("text") if isinstance(response, dict) else str(response)
    return text.strip() or "The local agent returned no answer."


TOOL = {
    "name": "ollama_agent",
    "description": (
        "Use the local Qwen 3.5 agent for private planning, coding, research, "
        "troubleshooting, and task breakdown. Use action=status to check Ollama. "
        "This agent does not directly change the computer; use Charlie's guarded tools for actions."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["ask", "status"]},
            "prompt": {"type": "STRING", "description": "Task or question for the local agent."},
            "role": {
                "type": "STRING",
                "enum": ["general", "coding", "research", "troubleshooting", "planning", "computer"],
            },
        },
        "required": ["action"],
    },
    "handler": ollama_agent,
}
