"""engine.voice — Voice, Wake Word, Natural Conversation, and Real-Time Command Engine."""

from engine.voice.audio_device_mgr import AudioDeviceManager
from engine.voice.barge_in import BargeInManager, InterruptScope
from engine.voice.capture import MicrophoneCapture
from engine.voice.command_engine import VoiceCommandEngine, VoicePermissionConfirmation
from engine.voice.conversation import ConversationTurnManager
from engine.voice.models import (
    AudioDevice,
    BargeInEvent,
    CommandConfidence,
    PendingConfirmation,
    Transcript,
    VoiceIntent,
    VoiceSession,
    VoiceSettings,
    VoiceState,
)
from engine.voice.orchestrator import VoiceOrchestrator
from engine.voice.recovery import AudioRecoveryEngine
from engine.voice.stt import (
    FasterWhisperSTTProvider,
    MockSTTProvider,
    SpeechRecognitionManager,
    SpeechRecognitionProvider,
    TranscriptNormalizer,
    VocabularyContextManager,
)
from engine.voice.tts import (
    EdgeTTSProvider,
    MockTTSProvider,
    TTSProvider,
    TextToSpeechManager,
)
from engine.voice.vad import VoiceActivityDetector
from engine.voice.wake_word import WakeWordEngine

__all__ = [
    "VoiceOrchestrator",
    "VoiceState",
    "VoiceIntent",
    "CommandConfidence",
    "AudioDevice",
    "VoiceSettings",
    "Transcript",
    "BargeInEvent",
    "PendingConfirmation",
    "VoiceSession",
    "AudioDeviceManager",
    "VoiceActivityDetector",
    "MicrophoneCapture",
    "WakeWordEngine",
    "SpeechRecognitionProvider",
    "SpeechRecognitionManager",
    "FasterWhisperSTTProvider",
    "MockSTTProvider",
    "VocabularyContextManager",
    "TranscriptNormalizer",
    "TextToSpeechManager",
    "TTSProvider",
    "EdgeTTSProvider",
    "MockTTSProvider",
    "BargeInManager",
    "InterruptScope",
    "ConversationTurnManager",
    "VoiceCommandEngine",
    "VoicePermissionConfirmation",
    "AudioRecoveryEngine",
]
