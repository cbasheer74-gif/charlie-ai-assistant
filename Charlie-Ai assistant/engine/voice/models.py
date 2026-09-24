"""engine/voice/models.py — Data Models, Enums, and State Machine for Voice Interaction."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class VoiceState(str, Enum):
    SLEEPING = "SLEEPING"
    WAKE_DETECTED = "WAKE_DETECTED"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    ACTING = "ACTING"
    SPEAKING = "SPEAKING"
    INTERRUPTED = "INTERRUPTED"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    PAUSED = "PAUSED"
    ERROR = "ERROR"


class VoiceIntent(str, Enum):
    QUESTION = "QUESTION"
    COMPUTER_COMMAND = "COMPUTER_COMMAND"
    PROJECT_COMMAND = "PROJECT_COMMAND"
    RESEARCH_COMMAND = "RESEARCH_COMMAND"
    EMAIL_COMMAND = "EMAIL_COMMAND"
    CALENDAR_COMMAND = "CALENDAR_COMMAND"
    FILE_COMMAND = "FILE_COMMAND"
    SPREADSHEET_COMMAND = "SPREADSHEET_COMMAND"
    VIDEO_COMMAND = "VIDEO_COMMAND"
    CODING_COMMAND = "CODING_COMMAND"
    SKILL_COMMAND = "SKILL_COMMAND"
    CONVERSATION = "CONVERSATION"
    STOP = "STOP"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    CORRECTION = "CORRECTION"
    CONFIRMATION = "CONFIRMATION"


class CommandConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    CLARIFY = "CLARIFY"


@dataclass
class AudioDevice:
    name: str
    index: int
    channels: int = 1
    sample_rate: int = 16000
    is_default: bool = False


@dataclass
class VoiceSettings:
    voice_enabled: bool = True
    wake_word_enabled: bool = True
    wake_phrase: str = "Hey Charlie"
    wake_threshold: float = 0.5
    preferred_microphone: str = ""
    preferred_speaker: str = ""
    stt_provider: str = "AUTO"  # AUTO, LOCAL, CLOUD
    tts_provider: str = "AUTO"  # AUTO, LOCAL, CLOUD, SAPI
    voice_speed: float = 1.0
    voice_volume: float = 1.0
    follow_up_window_sec: float = 10.0
    push_to_talk_hotkey: str = "ctrl+alt+c"
    keep_voice_history: bool = False
    quiet_mode: bool = False
    silence_threshold_sec: float = 1.2
    energy_threshold: float = 0.015


@dataclass
class Transcript:
    raw_transcript: str
    normalized_transcript: str
    language: str = "en"
    confidence: float = 0.95
    is_partial: bool = False
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    session_id: str = ""


@dataclass
class BargeInEvent:
    trigger_word: str
    timestamp: float
    interrupted_tts_text: str = ""


@dataclass
class PendingConfirmation:
    action_id: str
    session_id: str
    action_type: str
    description: str
    target_payload: Dict[str, Any]
    expires_at: float
    confirmed: Optional[bool] = None


@dataclass
class VoiceSession:
    session_id: str
    active_project: Optional[str] = None
    last_action: Optional[str] = None
    last_referent: Optional[str] = None
    last_interaction_time: float = 0.0
    turns: List[Transcript] = field(default_factory=list)
    pending_confirmation: Optional[PendingConfirmation] = None

    def is_active(self, window_sec: float = 10.0) -> bool:
        if self.last_interaction_time <= 0.0:
            return False
        return (time.time() - self.last_interaction_time) <= window_sec
