"""engine/voice/orchestrator.py — VoiceOrchestrator: Coordinates Voice States, VAD, STT, Routing, and Barge-In."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, Optional
import numpy as np

from engine.voice.audio_device_mgr import AudioDeviceManager
from engine.voice.barge_in import BargeInManager, InterruptScope
from engine.voice.capture import MicrophoneCapture
from engine.voice.command_engine import VoiceCommandEngine
from engine.voice.conversation import ConversationTurnManager
from engine.voice.models import (
    AudioDevice,
    CommandConfidence,
    Transcript,
    VoiceIntent,
    VoiceSettings,
    VoiceState,
)
from engine.voice.recovery import AudioRecoveryEngine
from engine.voice.stt import SpeechRecognitionManager, TranscriptNormalizer
from engine.voice.tts import TextToSpeechManager
from engine.voice.vad import VoiceActivityDetector
from engine.voice.wake_word import WakeWordEngine

# Lazy import — facial rig is optional; engine works without it
try:
    from engine.avatar.bone_controller import FacialAnimationController, _approximate_timeline
    _FACIAL_AVAILABLE = True
except ImportError:
    _FACIAL_AVAILABLE = False
    FacialAnimationController = None  # type: ignore
    _approximate_timeline = None      # type: ignore


class VoiceOrchestrator:
    """End-to-End Voice Interaction Coordinator for CHARLIE."""

    def __init__(
        self,
        settings: Optional[VoiceSettings] = None,
        device_manager: Optional[AudioDeviceManager] = None,
        stt_manager: Optional[SpeechRecognitionManager] = None,
        tts_manager: Optional[TextToSpeechManager] = None,
        facial_ctrl: Optional["FacialAnimationController"] = None,
    ):
        self.settings = settings or VoiceSettings()
        self.device_manager = device_manager or AudioDeviceManager()
        self.stt_manager = stt_manager or SpeechRecognitionManager()
        self.tts_manager = tts_manager or TextToSpeechManager()

        # Facial animation controller — auto-initialised if avatar module is present
        if facial_ctrl is not None:
            self.facial_ctrl: Optional[FacialAnimationController] = facial_ctrl
        elif _FACIAL_AVAILABLE:
            self.facial_ctrl = FacialAnimationController()  # type: ignore
            self.facial_ctrl.start_auto_blink()
        else:
            self.facial_ctrl = None

        self.vad = VoiceActivityDetector(
            energy_threshold=self.settings.energy_threshold,
            silence_timeout_sec=self.settings.silence_threshold_sec,
        )
        self.capture = MicrophoneCapture(device_manager=self.device_manager)
        self.wake_engine = WakeWordEngine(
            wake_phrase=self.settings.wake_phrase,
            threshold=self.settings.wake_threshold,
            on_wake_detected=self._on_wake_detected,
        )
        self.barge_in = BargeInManager(tts_manager=self.tts_manager)
        self.conversation = ConversationTurnManager(follow_up_window_sec=self.settings.follow_up_window_sec)
        self.command_engine = VoiceCommandEngine()
        self.recovery = AudioRecoveryEngine(device_manager=self.device_manager)

        self.current_state: VoiceState = VoiceState.SLEEPING
        self.active_task_paused: bool = False
        self._emergency_stop_triggered: bool = False

        self.barge_in.set_emergency_stop_callback(self.emergency_stop)
        self.capture.add_frame_callback(self._on_audio_frame)

    def _on_audio_frame(self, chunk: np.ndarray) -> None:
        """Processes incoming audio frame for acoustic barge-in, VAD, and backchanneling."""
        if chunk is None or len(chunk) == 0:
            return

        energy = self.vad.calculate_energy(chunk)

        # 1. Instant Acoustic Barge-In (<50ms cutoff during assistant speech)
        if self.tts_manager.is_speaking():
            self.barge_in.process_acoustic_frame(energy)

        # 2. Backchanneling evaluation during user speech
        is_voice = energy >= self.vad.energy_threshold
        backchannel_event = self.vad.check_backchannel(is_voice)
        if backchannel_event and backchannel_event.get("visual_nod"):
            if self.facial_ctrl and hasattr(self.facial_ctrl, "set_expression"):
                self.facial_ctrl.set_expression("brow_raise", 0.3)

    def _on_wake_detected(self) -> None:

        if self.current_state != VoiceState.SPEAKING:
            self.current_state = VoiceState.WAKE_DETECTED

    def start(self) -> bool:
        """Starts audio capture and listener threads."""
        self.capture.start()
        self.current_state = VoiceState.SLEEPING
        return True

    def stop(self) -> None:
        """Shuts down audio capture and resets voice state."""
        self.capture.stop()
        self.tts_manager.stop()
        self.current_state = VoiceState.SLEEPING

    def emergency_stop(self) -> None:
        """Immediately aborts all voice actions, stops TTS, and flags emergency stop."""
        self._emergency_stop_triggered = True
        self.tts_manager.stop()
        if self.facial_ctrl:
            self.facial_ctrl.stop()
            self.facial_ctrl.set_expression("neutral", 0.0, smooth=False)
        self.current_state = VoiceState.INTERRUPTED
        self.capture.stop()

    def process_spoken_transcript(self, raw_transcript: str) -> Dict[str, Any]:
        """Core pipeline: Processes recognized speech text into context-resolved action and concise voice response."""
        if not raw_transcript.strip():
            self.current_state = VoiceState.SLEEPING
            return {"status": "EMPTY", "state": self.current_state.value}

        # 1. Check for Immediate Barge-In or Stop
        interrupt_scope = self.barge_in.check_for_interruption(raw_transcript)
        if interrupt_scope:
            if interrupt_scope == InterruptScope.EMERGENCY_STOP_ALL:
                self.emergency_stop()
                return {"status": "EMERGENCY_STOP_TRIGGERED", "state": self.current_state.value}
            elif interrupt_scope == InterruptScope.STOP_CURRENT_TASK:
                if self.facial_ctrl:
                    self.facial_ctrl.stop()
                self.current_state = VoiceState.PAUSED
                self.active_task_paused = True
                return {"status": "TASK_STOPPED", "state": self.current_state.value}
            elif interrupt_scope == InterruptScope.STOP_TTS_ONLY:
                if self.facial_ctrl:
                    self.facial_ctrl.stop()
                self.current_state = VoiceState.SLEEPING
                return {"status": "TTS_STOPPED", "state": self.current_state.value}

        # 2. Check Wake Word or Follow-up Window
        is_wake = self.wake_engine.inspect_text_for_wake(raw_transcript)
        in_follow_up = self.conversation.is_in_follow_up_window()

        if not is_wake and not in_follow_up:
            # Utterance ignored because not addressed to CHARLIE
            self.current_state = VoiceState.SLEEPING
            return {"status": "IGNORED_NO_WAKE", "state": self.current_state.value}

        # 2.5 Pure Wake Word Utterance (e.g. "Hey Charlie", "Hello Charlie")
        cleaned_no_wake = re.sub(r"^(hey\s+|hello\s+)?charlie[\s,!.?]*", "", raw_transcript.strip(), flags=re.I).strip()
        if not cleaned_no_wake:
            self.current_state = VoiceState.LISTENING
            self.conversation.update_activity()
            # Show listening expression on avatar
            if self.facial_ctrl:
                self.facial_ctrl.set_expression("brow_raise", 0.3)
            return {
                "status": "WAKE_DETECTED",
                "state": self.current_state.value,
                "speech_response": "",
            }

        self.current_state = VoiceState.PROCESSING

        # 3. Clean and Normalize Transcript
        normalized = TranscriptNormalizer.normalize(raw_transcript)

        # 4. Resolve Context, Anaphora, and Corrections
        resolved_command = self.conversation.resolve_referents(normalized)

        # Record conversation turn
        transcript_obj = Transcript(
            raw_transcript=raw_transcript,
            normalized_transcript=resolved_command,
            session_id=self.conversation.active_session.session_id,
        )
        self.conversation.record_turn(transcript_obj)

        # 5. Route Command through VoiceCommandEngine
        self.current_state = VoiceState.ACTING
        result = self.command_engine.route_command(
            resolved_command,
            session_id=self.conversation.active_session.session_id,
            active_project=self.conversation.active_session.active_project,
        )

        # Update Session Context
        if "target_project" in result:
            self.conversation.set_active_project(result["target_project"])

        # 6. Speak Concise Voice Output with Self-TTS Lockout
        speech_text = result.get("speech_response", "")
        if speech_text and not self.settings.quiet_mode:
            self.current_state = VoiceState.SPEAKING
            self.wake_engine.set_charlie_speaking(True)

            # ── Facial animation: pick expression from result or default ──
            expression = result.get("emotion", "neutral")
            if self.facial_ctrl and _approximate_timeline:
                phoneme_tl = result.get("phoneme_timeline") or _approximate_timeline(speech_text)
                self.facial_ctrl.play_phoneme_timeline(
                    phoneme_tl,
                    expression=expression,
                    expression_weight=0.45,
                    blocking=False,
                )

            def _on_finish():
                self.wake_engine.set_charlie_speaking(False)
                self.current_state = VoiceState.SLEEPING
                self.conversation.update_activity()
                # Reset rig to neutral after speech finishes
                if self.facial_ctrl:
                    self.facial_ctrl.set_expression(expression, 0.0, smooth=True, duration=0.4)

            # Adapt silence timeout for subsequent turn based on input text
            self.vad.adapt_timeout(resolved_command)

            self.tts_manager.speak(speech_text, on_complete=_on_finish, emotion=expression)
        else:
            self.current_state = VoiceState.SLEEPING
            self.conversation.update_activity()
            self.vad.adapt_timeout(resolved_command)


        result["voice_state"] = self.current_state.value
        result["resolved_command"] = resolved_command
        return result

    def simulate_audio_turn(self, audio_data: np.ndarray) -> Dict[str, Any]:
        """Convenience test & runtime method: pushes audio through STT and processes output."""
        transcript = self.stt_manager.transcribe_audio(audio_data)
        return self.process_spoken_transcript(transcript.raw_transcript)
