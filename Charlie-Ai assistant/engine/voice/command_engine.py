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

        # 2. Check Cultural & Regional Greetings
        try:
            from engine.voice.cultural_greetings import detect_greeting, get_reply
            detected_cult = detect_greeting(text)
            if detected_cult:
                reply = get_reply(detected_cult)
                rel = detected_cult[0] if isinstance(detected_cult, (tuple, list)) else detected_cult.get("religion", "general")
                return {
                    "status": "CULTURAL_GREETING",
                    "culture": rel,
                    "speech_response": reply,
                }
        except Exception:
            pass

        # 3. Disambiguate vague / elliptic voice commands
        try:
            from engine.intelligence.intent_disambiguator import get_intent_disambiguator
            disambiguator = get_intent_disambiguator()
            d_res = disambiguator.disambiguate(text)
            if d_res.is_ambiguous and d_res.confidence >= 0.75 and d_res.resolved_tool:
                # Dispatch resolved tool directly
                tool_name = d_res.resolved_tool
                try:
                    tool_mod = __import__(f"actions.{tool_name}", fromlist=[tool_name])
                    exec_fn = getattr(tool_mod, "execute", None)
                    if exec_fn:
                        exec_res = exec_fn(**d_res.resolved_args)
                        # Record episode
                        try:
                            from engine.intelligence.episodic_memory import get_episodic_memory
                            get_episodic_memory().record_episode(
                                summary=f"Executed {tool_name}: {d_res.resolved_intent}",
                                tags=[tool_name, "disambiguated"],
                                importance=6,
                            )
                        except Exception:
                            pass
                        return {
                            "status": "EXECUTED_DISAMBIGUATED_TOOL",
                            "tool": tool_name,
                            "speech_response": str(exec_res).split("\n")[0][:120],
                            "output": exec_res,
                        }
                except Exception:
                    pass
        except Exception:
            pass

        # 4. Check high-risk actions requiring voice confirmation
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

        # 5. Routine Briefing & Daily Agenda
        if any(w in text.lower() for w in ("good morning", "morning brief", "start my day", "today's briefing", "aaj ka plan")):
            try:
                import actions.routine_briefing as rb
                out = rb.execute(action="morning")
                return {"status": "ROUTINE_BRIEFING", "tool": "routine_briefing", "speech_response": out.split("\n")[0], "output": out}
            except Exception:
                pass
        if any(w in text.lower() for w in ("evening wrap", "end of day", "aaj ka wrap up")):
            try:
                import actions.routine_briefing as rb
                out = rb.execute(action="evening")
                return {"status": "ROUTINE_BRIEFING", "tool": "routine_briefing", "speech_response": out.split("\n")[0], "output": out}
            except Exception:
                pass

        # 6. Focus Timer / Pomodoro
        if any(w in text.lower() for w in ("focus mode", "pomodoro", "start timer", "take a break", "end focus")):
            try:
                import actions.focus_timer as ft
                action = "break" if "break" in text.lower() else ("stop" if "end" in text.lower() else "start")
                out = ft.execute(action=action)
                return {"status": "FOCUS_TIMER", "tool": "focus_timer", "speech_response": str(out).split("\n")[0], "output": out}
            except Exception:
                pass

        # 7. File Organizer (Desktop & Downloads)
        if any(w in text.lower() for w in ("clean desktop", "clean up my desktop", "organize downloads", "tidy files", "sort files")):
            try:
                import actions.file_organizer as fo
                action = "organize" if any(w in text.lower() for w in ("clean", "organize", "tidy", "sort")) else "preview"
                target = "downloads" if "downloads" in text.lower() else "desktop"
                out = fo.execute(action=action, target=target)
                return {"status": "FILE_ORGANIZER", "tool": "file_organizer", "speech_response": str(out).split("\n")[0], "output": out}
            except Exception:
                pass

        # 8. Workflow Runner (Macro Presets)
        if any(w in text.lower() for w in ("start coding mode", "prepare for meeting", "deep work mode", "wrap up day")):
            try:
                import actions.workflow_runner as wr
                preset = "coding" if "coding" in text.lower() else ("meeting" if "meeting" in text.lower() else ("deep_work" if "deep" in text.lower() else "wrap_up"))
                out = wr.execute(preset=preset)
                return {"status": "WORKFLOW_MACRO", "tool": "workflow_runner", "speech_response": str(out).split("\n")[0], "output": out}
            except Exception:
                pass

        # 9. Writing Polish
        if any(w in text.lower() for w in ("polish this", "fix grammar", "make it professional", "shorten this", "executive tone")):
            try:
                import actions.writing_polish as wp
                tone = "executive" if "executive" in text.lower() else ("casual" if "casual" in text.lower() else "professional")
                act = "grammar" if "grammar" in text.lower() else ("shorten" if "shorten" in text.lower() else "polish")
                out = wp.execute(action=act, tone=tone)
                return {"status": "WRITING_POLISHED", "tool": "writing_polish", "speech_response": "Polished text ready on your clipboard.", "output": out}
            except Exception:
                pass

        # 10. Page & Document Summarizer
        if any(w in text.lower() for w in ("summarize this", "summarize page", "summarize article", "key takeaways")):
            try:
                import actions.page_summarizer as ps
                out = ps.execute(action="from_clipboard")
                return {"status": "PAGE_SUMMARIZED", "tool": "page_summarizer", "speech_response": str(out).split("\n")[0], "output": out}
            except Exception:
                pass

        # 11. Smart Email Dictation
        if any(w in text.lower() for w in ("draft an email", "draft email", "compose email")):
            try:
                import actions.email_dictation as ed
                out = ed.execute(action="draft", body_hint=text)
                return {"status": "EMAIL_DICTATION", "tool": "email_dictation", "speech_response": "Drafting your email now.", "output": out}
            except Exception:
                pass

        # 12. Smart Clipboard Manager
        if any(w in text.lower() for w in ("clipboard history", "what did i copy", "show clipboard")):
            try:
                import actions.clipboard_manager as cm
                out = cm.execute(action="show", count=5)
                return {"status": "CLIPBOARD_MANAGER", "tool": "clipboard_manager", "speech_response": "Showing your recent clipboard history.", "output": out}
            except Exception:
                pass

        # 13. Meeting Notes
        if any(w in text.lower() for w in ("start meeting notes", "stop meeting notes", "meeting summary")):
            try:
                import actions.meeting_notes as mn
                act = "stop" if "stop" in text.lower() else "start"
                out = mn.execute(action=act)
                return {"status": "MEETING_NOTES", "tool": "meeting_notes", "speech_response": str(out).split("\n")[0], "output": out}
            except Exception:
                pass

        # 13a. Media & Volume Control
        if any(w in text.lower() for w in ("play music", "pause music", "mute", "unmute", "volume up", "volume down", "next song", "skip song", "previous song", "louder", "quieter")):
            try:
                import actions.media_control as mc
                if "volume up" in text.lower() or "louder" in text.lower():
                    act = "volume_up"
                elif "volume down" in text.lower() or "quieter" in text.lower() or "softer" in text.lower():
                    act = "volume_down"
                elif "mute" in text.lower() or "unmute" in text.lower():
                    act = "mute"
                elif "next" in text.lower() or "skip" in text.lower():
                    act = "next"
                elif "prev" in text.lower() or "back" in text.lower():
                    act = "previous"
                else:
                    act = "play_pause"
                out = mc.execute(action=act)
                return {"status": "MEDIA_CONTROL", "tool": "media_control", "speech_response": str(out), "output": out}
            except Exception:
                pass

        # 13b. Quick Math, Currency & Unit Converter
        if any(w in text.lower() for w in ("calculate", "percent of", "% of", " divided by ", " times ", " usd to ", " inr to ", " eur to ", " miles to ", " km to ", " f to c", " c to f", " kg to ")):
            try:
                import actions.quick_calc as qc
                out = qc.execute(query=text)
                return {"status": "QUICK_CALC", "tool": "quick_calc", "speech_response": str(out), "output": out}
            except Exception:
                pass

        # 13c. Screen Snip & Explain
        if any(w in text.lower() for w in ("explain my screen", "what is on my screen", "read screen", "explain this window", "screenshot and explain", "screen error")):
            try:
                import actions.screen_explainer as se
                mode = "error" if "error" in text.lower() else ("read" if "read" in text.lower() else "explain")
                out = se.execute(mode=mode)
                return {"status": "SCREEN_EXPLAINER", "tool": "screen_explainer", "speech_response": str(out).split("\n")[0], "output": out}
            except Exception:
                pass

        # 13d. Voice Speed & Tone Customizer
        if any(w in text.lower() for w in ("speak faster", "talk faster", "speak slower", "slow down", "talk normally", "reset voice speed", "quiet mode")):
            try:
                import actions.voice_speed as vs
                if "faster" in text.lower() or "speed up" in text.lower():
                    act = "faster"
                elif "slower" in text.lower() or "slow down" in text.lower():
                    act = "slower"
                elif "quiet" in text.lower():
                    act = "toggle_quiet"
                else:
                    act = "reset"
                out = vs.execute(action=act)
                return {"status": "VOICE_SPEED", "tool": "voice_speed", "speech_response": str(out), "output": out}
            except Exception:
                pass

        # 13e. Screen Vision Co-pilot
        if any(w in text.lower() for w in ("screen copilot", "analyze screen", "what's on my screen", "check screen", "screen error")):
            try:
                from engine.vision.screen_copilot import get_screen_copilot
                copilot = get_screen_copilot()
                insight = copilot.inspect_screen_now(force_ocr=True)
                msg = f"Active window: {insight.active_window}."
                if insight.has_code_error:
                    msg += f" Detected {len(insight.detected_errors)} errors on screen."
                return {"status": "SCREEN_COPILOT", "tool": "screen_copilot", "speech_response": msg, "output": insight}
            except Exception:
                pass

        # 13f. Mobile Companion Bridge
        if any(w in text.lower() for w in ("pair phone", "mobile bridge", "connect mobile", "start companion", "phone companion")):
            try:
                from engine.bridge.mobile_companion import get_mobile_bridge
                bridge = get_mobile_bridge()
                bridge.start()
                url = bridge.get_pairing_url()
                return {"status": "MOBILE_BRIDGE", "tool": "mobile_bridge", "speech_response": f"Mobile companion bridge active at {url}", "output": url}
            except Exception:
                pass

        # 13g. Lifelong User Memory Graph
        if any(w in text.lower() for w in ("what do you know about me", "my profile", "memory graph", "remembered facts")):
            try:
                from engine.memory.knowledge_graph import get_memory_graph
                facts = get_memory_graph().get_user_facts()
                if facts:
                    top_facts = ", ".join(f"{f['relation']} {f['entity']}" for f in facts[:3])
                    msg = f"I remember you {top_facts}."
                else:
                    msg = "I am observing your preferences and projects continuously."
                return {"status": "MEMORY_GRAPH", "tool": "memory_graph", "speech_response": msg, "output": facts}
            except Exception:
                pass

        intent = self.classify_intent(text)


        # 14. Project resume routing
        if "continue" in text.lower() or "rukhe the" in text.lower() or "ruke the" in text.lower():
            target_proj = active_project or "ZynPay"
            return {
                "status": "ROUTED_TO_SKILL",
                "skill_id": "skill_builtin_continue_coding_project",
                "agent": "AntigravityAgent",
                "speech_response": f"{target_proj} mil gaya. Last pending backend task se continue kar raha hoon.",
                "target_project": target_proj,
            }

        # 15. Screen Error / Coding Fix Routing
        if "error" in text.lower() or "bug" in text.lower() or "fix karo" in text.lower():
            return {
                "status": "ROUTED_TO_SKILL",
                "skill_id": "skill_builtin_troubleshoot_screen_error",
                "agent": "AntigravityAgent",
                "speech_response": "Screen error detect kiya. Antigravity se recovery start kar raha hoon.",
            }

        # 16. YouTube Short skill routing
        if intent == VoiceIntent.VIDEO_COMMAND:
            return {
                "status": "ROUTED_TO_SKILL",
                "skill_id": "skill_builtin_create_youtube_short",
                "agent": "VideoAgent",
                "speech_response": "Topic verify ho gaya. Video workflow start kar diya.",
            }

        # 17. Spreadsheet skill routing
        if intent == VoiceIntent.SPREADSHEET_COMMAND:
            return {
                "status": "ROUTED_TO_SKILL",
                "skill_id": "skill_builtin_create_excel_report",
                "agent": "SpreadsheetAgent",
                "speech_response": "Excel file mil gayi. Monthly sales report create kar raha hoon.",
            }

        # 18. Research engine routing
        if intent == VoiceIntent.RESEARCH_COMMAND:
            return {
                "status": "ROUTED_TO_RESEARCH",
                "tool": "research_engine",
                "agent": "ResearchAgent",
                "speech_response": "Live research start kiya. Result UI mein dikh raha hai.",
            }

        # 19. Offline Knowledge Graph Check
        try:
            from engine.intelligence.offline_knowledge import get_offline_knowledge
            kg = get_offline_knowledge()
            hits = kg.query(text, top_k=1)
            if hits and hits[0].get("relevance", 0) >= 3.0:
                hit = hits[0]
                return {
                    "status": "OFFLINE_KNOWLEDGE_HIT",
                    "speech_response": f"{hit['title']}: {hit['summary']}",
                    "details": hit['details'],
                }
        except Exception:
            pass

        # 20. Computer control / App launch routing
        if intent == VoiceIntent.COMPUTER_COMMAND:
            app_match = re.search(r"\b(notepad|chrome|edge|vs\s*code|antigravity|excel)\b", text, re.I)
            app_name = app_match.group(0) if app_match else "Application"
            return {
                "status": "ROUTED_TO_COMPUTER_CONTROL",
                "action": "open_app",
                "target": app_name,
                "speech_response": f"{app_name.title()} open ho gaya.",
            }

        # Record generic episode
        try:
            from engine.intelligence.episodic_memory import get_episodic_memory
            get_episodic_memory().record_episode(
                summary=f"User requested: {text}",
                tags=["general_query"],
                importance=3,
            )
        except Exception:
            pass

        return {
            "status": "ROUTED_TO_AGENT",
            "agent": "GeneralAgent",
            "speech_response": "Samajh gaya. Main is par kaam kar raha hoon.",
        }
