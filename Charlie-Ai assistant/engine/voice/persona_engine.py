"""
engine/voice/persona_engine.py
Multi-voice conversational persona engine with regional accent and tone adaptation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class VoicePersona:
    id: str
    display_name: str
    accent: str           # "British", "Indian", "American", "Australian"
    tone_style: str       # "formal", "warm", "balanced", "philosophical", "energetic"
    tts_female: str
    tts_male: str
    speech_rate: str      # e.g., "+0%", "+5%", "-5%"
    system_prompt_addon: str


PERSONAS: dict[str, VoicePersona] = {
    "jarvis": VoicePersona(
        id="jarvis",
        display_name="Charlie (British)",
        accent="British",
        tone_style="formal",
        tts_female="en-GB-SoniaNeural",
        tts_male="en-GB-RyanNeural",
        speech_rate="+0%",
        system_prompt_addon=(
            "Persona: You are Charlie. Respond with crisp British precision, subtle wit, and utmost efficiency. "
            "Address the user respectfully as 'Sir' or 'Ma'am'. Keep sentences clear, composed, and mathematically exact."
        )
    ),
    "friday": VoicePersona(
        id="friday",
        display_name="F.R.I.D.A.Y.",
        accent="Irish/British",
        tone_style="warm",
        tts_female="en-IE-EmilyNeural",
        tts_male="en-IE-ConnorNeural",
        speech_rate="+5%",
        system_prompt_addon=(
            "Persona: You are F.R.I.D.A.Y. Speak warmly, briskly, and proactively. "
            "Anticipate the user's needs, confirm actions immediately, and maintain an energetic, supportive presence."
        )
    ),
    "charlie_core": VoicePersona(
        id="charlie_core",
        display_name="Charlie Core",
        accent="American",
        tone_style="balanced",
        tts_female="en-US-JennyNeural",
        tts_male="en-US-GuyNeural",
        speech_rate="+0%",
        system_prompt_addon=(
            "Persona: You are Charlie. Direct, intelligent, modern personal AI desktop assistant. "
            "Balanced, concise, highly capable, and always helpful."
        )
    ),
    "desi_buddy": VoicePersona(
        id="desi_buddy",
        display_name="Desi Buddy",
        accent="Indian",
        tone_style="energetic",
        tts_female="en-IN-NeerjaNeural",
        tts_male="en-IN-PrabhatNeural",
        speech_rate="+5%",
        system_prompt_addon=(
            "Persona: You are Desi Buddy. Friendly, approachable, highly relatable Indian English / Hinglish companion. "
            "Use natural Indian conversational warmth (e.g., 'haan bilkul', 'done!', 'batao kya karna hai')."
        )
    ),
    "socrates": VoicePersona(
        id="socrates",
        display_name="Socrates",
        accent="Greek/European",
        tone_style="philosophical",
        tts_female="el-GR-AthinaNeural",
        tts_male="el-GR-NestorasNeural",
        speech_rate="-5%",
        system_prompt_addon=(
            "Persona: You are Socrates. Thoughtful, patient, and intellectually rigorous. "
            "Ask sharp clarifying questions to help the user uncover root causes and deepen understanding."
        )
    ),
}


class PersonaManager:
    """Manages active conversational persona and regional accent voicing."""

    def __init__(self, default_id: str = "charlie_core"):
        self._active_id = default_id if default_id in PERSONAS else "charlie_core"

    @property
    def active_persona(self) -> VoicePersona:
        return PERSONAS.get(self._active_id, PERSONAS["charlie_core"])

    def set_persona(self, persona_id: str) -> Optional[VoicePersona]:
        clean = persona_id.lower().strip()
        if clean in PERSONAS:
            self._active_id = clean
            return PERSONAS[clean]
        return None

    def get_voice(self, is_female: bool = True) -> str:
        p = self.active_persona
        return p.tts_female if is_female else p.tts_male

    def get_system_prompt_directive(self) -> str:
        return self.active_persona.system_prompt_addon


_global_persona_mgr: Optional[PersonaManager] = None


def get_persona_manager() -> PersonaManager:
    global _global_persona_mgr
    if _global_persona_mgr is None:
        _global_persona_mgr = PersonaManager()
    return _global_persona_mgr
