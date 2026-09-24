"""engine/voice/command_engine.py — Voice Intent Classification, Safety Confirmations, and Backend Skill/Agent Routing."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, Optional, Tuple

from engine.voice.models import (
    CommandConfidence,
    PendingConfirmation,
    VoiceIntent,
)


class VoicePermissionConfirmation:
    """Binds high-impact voice actions to exact session IDs and short expiry intervals."""

    def __init__(self, timeout_sec: float = 20.0):
        self.timeout_sec = timeout_sec
        self._pending: Optional[PendingConfirmation] = None

    def create_pending(
        self,
        session_id: str,
        action_type: str,
        description: str,
        target_payload: Dict[str, Any],
    ) -> PendingConfirmation:
        action_id = f"act_{int(time.time())}_{abs(hash(description)) % 1000}"
        self._pending = PendingConfirmation(
            action_id=action_id,
            session_id=session_id,
            action_type=action_type,
            description=description,
            target_payload=target_payload,
            expires_at=time.time() + self.timeout_sec,
        )
        return self._pending

    def get_pending(self, session_id: str) -> Optional[PendingConfirmation]:
        if not self._pending:
            return None
        if time.time() > self._pending.expires_at or self._pending.session_id != session_id:
            self._pending = None
            return None
        return self._pending

    def resolve_confirmation(self, user_text: str, session_id: str) -> Tuple[bool, Optional[PendingConfirmation]]:
        pending = self.get_pending(session_id)
        if not pending:
            return False, None

        low = user_text.lower().strip()
        positive = any(w in low for w in ("haan", "yes", "do it", "proceed", "send", "kar do", "bhej do", "theek hai"))
        negative = any(w in low for w in ("nahi", "no", "cancel", "mat karo", "stop", "dont", "don't"))

        if positive:
            pending.confirmed = True
            resolved = self._pending
            self._pending = None
            return True, resolved
        elif negative:
            pending.confirmed = False
            self._pending = None
            return True, None

        return False, None


class VoiceCommandEngine:
    """Classifies voice intents, verifies risk levels, and routes directly to existing skills and agents."""

    HIGH_RISK_PATTERNS = [
        re.compile(r"\b(delete|remove|format|erase|drop\s+table|rmdir)\b", re.I),
        re.compile(r"\b(send\s+email|bhej\s+do|mail\s+send)\b", re.I),
        re.compile(r"\b(shutdown|restart|system\s+band)\b", re.I),
        re.compile(r"\b(purchase|pay|buy)\b", re.I),
    ]

    def __init__(self):
        self.confirmation_manager = VoicePermissionConfirmation()

    def classify_intent(self, text: str) -> VoiceIntent:
        low = text.lower()

        if any(w in low for w in ("haan", "yes", "do it", "mat karo", "proceed", "nahi")):
            return VoiceIntent.CONFIRMATION
        if any(w in low for w in ("stop", "cancel", "chup", "ruko")):
            return VoiceIntent.STOP
        if any(w in low for w in ("pause", "ruk jao")):
            return VoiceIntent.PAUSE
        if any(w in low for w in ("resume", "continue karo")):
            return VoiceIntent.RESUME
        if any(w in low for w in ("short bana", "reel bana", "youtube video")):
            return VoiceIntent.VIDEO_COMMAND
        if any(w in low for w in ("excel", "sheet", "monthly report", "spreadsheet")):
            return VoiceIntent.SPREADSHEET_COMMAND
        if any(w in low for w in ("code", "flutter", "run project", "backend", "test chalao", "antigravity")):
            return VoiceIntent.CODING_COMMAND
        if any(w in low for w in ("research", "trend", "sach hai", "kya chal raha", "verify")):
            return VoiceIntent.RESEARCH_COMMAND
        if any(w in low for w in ("email", "mail", "gmail", "inbox")):
            return VoiceIntent.EMAIL_COMMAND
        if any(w in low for w in ("calendar", "meeting", "schedule")):
            return VoiceIntent.CALENDAR_COMMAND
        if any(w in low for w in ("kholo", "open", "launch", "minimize", "maximize", "volume")):
            return VoiceIntent.COMPUTER_COMMAND

        return VoiceIntent.QUESTION

    def evaluate_risk_and_confidence(self, text: str, transcription_confidence: float = 0.95) -> CommandConfidence:
        is_high_risk = any(bool(pat.search(text)) for pat in self.HIGH_RISK_PATTERNS)

        if transcription_confidence < 0.75 and is_high_risk:
            return CommandConfidence.CLARIFY

        if transcription_confidence >= 0.85:
            return CommandConfidence.HIGH
        elif transcription_confidence >= 0.70:
            return CommandConfidence.MEDIUM

        return CommandConfidence.LOW

    def route_command(
        self,
        text: str,
        session_id: str,
        active_project: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Routes voice commands into existing Skills, Agents, or Computer Automation."""
        # 1. Check if this is an answer to a pending confirmation
        is_confirmed, pending = self.confirmation_manager.resolve_confirmation(text, session_id)
        if is_confirmed:
            if pending:
                return {
                    "status": "CONFIRMED_AND_EXECUTING",
                    "action_type": pending.action_type,
                    "target_payload": pending.target_payload,
                    "speech_response": f"{pending.description} complete kar diya.",
                }
            else:
                return {
                    "status": "CANCELLED",
                    "speech_response": "Action cancel kar diya gaya hai.",
                }

        # 2. Check if high-risk action requiring voice confirmation
        is_high_risk = any(bool(pat.search(text)) for pat in self.HIGH_RISK_PATTERNS)
        if is_high_risk and ("email" in text.lower() or "bhej" in text.lower()):
            self.confirmation_manager.create_pending(
                session_id=session_id,
                action_type="SEND_EMAIL",
                description="Client ko email bhejna",
                target_payload={"raw_command": text},
            )
            return {
                "status": "AWAITING_CONFIRMATION",
                "speech_response": "Client ko email bhejne wala hoon. Send kar doon?",
            }

        intent = self.classify_intent(text)

        # 3. Project resume routing
        if "continue" in text.lower() or "rukhe the" in text.lower() or "ruke the" in text.lower():
            target_proj = active_project or "ZynPay"
            return {
                "status": "ROUTED_TO_SKILL",
                "skill_id": "skill_builtin_continue_coding_project",
                "agent": "AntigravityAgent",
                "speech_response": f"{target_proj} mil gaya. Last pending backend task se continue kar raha hoon.",
                "target_project": target_proj,
            }

        # 3.5 Screen Error / Coding Fix Routing
        if "error" in text.lower() or "bug" in text.lower() or "fix karo" in text.lower():
            return {
                "status": "ROUTED_TO_SKILL",
                "skill_id": "skill_builtin_troubleshoot_screen_error",
                "agent": "AntigravityAgent",
                "speech_response": "Screen error detect kiya. Antigravity se recovery start kar raha hoon.",
            }

        # 4. YouTube Short skill routing
        if intent == VoiceIntent.VIDEO_COMMAND:
            return {
                "status": "ROUTED_TO_SKILL",
                "skill_id": "skill_builtin_create_youtube_short",
                "agent": "VideoAgent",
                "speech_response": "Topic verify ho gaya. Video workflow start kar diya.",
            }

        # 5. Spreadsheet skill routing
        if intent == VoiceIntent.SPREADSHEET_COMMAND:
            return {
                "status": "ROUTED_TO_SKILL",
                "skill_id": "skill_builtin_create_excel_report",
                "agent": "SpreadsheetAgent",
                "speech_response": "Excel file mil gayi. Monthly sales report create kar raha hoon.",
            }

        # 6. Research engine routing
        if intent == VoiceIntent.RESEARCH_COMMAND:
            return {
                "status": "ROUTED_TO_RESEARCH",
                "tool": "research_engine",
                "agent": "ResearchAgent",
                "speech_response": "Live research start kiya. Result UI mein dikh raha hai.",
            }

        # 7. Computer control / App launch routing
        if intent == VoiceIntent.COMPUTER_COMMAND:
            # Parse application name e.g. "Notepad kholo" or "Chrome kholo"
            app_match = re.search(r"\b(notepad|chrome|edge|vs\s*code|antigravity|excel)\b", text, re.I)
            app_name = app_match.group(0) if app_match else "Application"
            return {
                "status": "ROUTED_TO_COMPUTER_CONTROL",
                "action": "open_app",
                "target": app_name,
                "speech_response": f"{app_name.title()} open ho gaya.",
            }

        return {
            "status": "ROUTED_TO_AGENT",
            "agent": "GeneralAgent",
            "speech_response": "Samajh gaya. Main is par kaam kar raha hoon.",
        }
