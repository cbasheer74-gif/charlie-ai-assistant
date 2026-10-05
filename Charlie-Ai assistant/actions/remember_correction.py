"""Store an explicit user correction so future answers can use it."""
from __future__ import annotations

import hashlib
from memory.memory_manager import update_memory


def remember_correction(parameters: dict, player=None, session_memory=None) -> str:
    params = parameters or {}
    corrected = str(params.get("correction") or params.get("corrected") or "").strip()
    if not corrected:
        return "Tell me the correction you want me to remember."
    context = str(params.get("context") or "").strip()
    value = corrected if not context else f"{corrected} (Context: {context})"
    key = "correction_" + hashlib.sha1(value.casefold().encode("utf-8")).hexdigest()[:12]
    update_memory({"corrections": {key: {"value": value}}})
    if player:
        try:
            player.write_log("SYS: User correction saved for future conversations.")
        except Exception:
            pass
    return "I will remember that correction for future answers."


TOOL = {
    "name": "remember_correction",
    "description": (
        "Store an explicit correction from the user so CHARLIE avoids repeating "
        "the mistake. Use only when the user clearly corrects a fact, preference, "
        "project detail, or workflow. Never store passwords, tokens, or one-time data."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "correction": {"type": "STRING", "description": "The corrected fact or instruction"},
            "context": {"type": "STRING", "description": "Optional project or workflow context"},
        },
        "required": ["correction"],
    },
    "handler": remember_correction,
}
