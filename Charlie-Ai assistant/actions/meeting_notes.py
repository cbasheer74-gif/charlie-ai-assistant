# actions/meeting_notes.py
"""
Meeting Notes Taker — Charlie listens to a meeting, transcribes, extracts action items,
assigns owners, and saves a professional summary.

Commands:
  "Start meeting notes"
  "This is a meeting with Rahul and Anees about Q4 targets"
  "Stop meeting notes"
  "What are the action items?"
  "Save meeting notes"
  "Email meeting summary to the team"
"""

from __future__ import annotations
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

TOOL = {
    "name": "meeting_notes",
    "description": (
        "Professional meeting transcription, action item extraction, and summary generation. "
        "Records what was said, identifies tasks/decisions, assigns owners, sets deadlines. "
        "Trigger on: 'start meeting', 'meeting notes', 'take notes', 'action items', "
        "'who said what', 'meeting summary', 'decisions made', 'save meeting notes'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["start", "add_note", "stop", "action_items", "summary", "save", "clear"],
                "description": "start=begin session, add_note=add a point, stop=end session, action_items=extract tasks, summary=full summary, save=save to file"
            },
            "note": {"type": "string", "description": "A discussion point, decision, or action item to record"},
            "participants": {"type": "string", "description": "Who is in the meeting (comma-separated names)"},
            "meeting_title": {"type": "string", "description": "Title or topic of the meeting"},
            "format": {"type": "string", "enum": ["markdown", "plain", "bullets"], "description": "Output format for summary"},
        },
        "required": ["action"],
    },
}

from core.app_paths import get_config_dir

_NOTES_DIR  = get_config_dir() / "meetings"
_SESSION_FILE = _NOTES_DIR / "current_session.json"


def _load_session() -> Optional[dict]:
    try:
        if _SESSION_FILE.exists():
            return json.loads(_SESSION_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def _save_session(data: dict) -> None:
    _NOTES_DIR.mkdir(parents=True, exist_ok=True)
    _SESSION_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _extract_action_items(notes: List[str]) -> List[str]:
    """Simple heuristic extraction of action items from notes."""
    action_keywords = re.compile(
        r"\b(will|shall|to do|needs to|must|should|by|deadline|assigned|responsible|follow up|send|submit|prepare|review|complete|finish|check|confirm|schedule)\b",
        re.I
    )
    return [n for n in notes if action_keywords.search(n)]


def run(args: Dict[str, Any]) -> str:
    action       = args.get("action", "summary")
    note         = args.get("note", "").strip()
    participants = args.get("participants", "").strip()
    title        = (args.get("meeting_title") or args.get("title", "")).strip()
    fmt          = args.get("format", "markdown")

    if action == "start":
        session = {
            "title":        title or f"Meeting — {datetime.now().strftime('%A %d %B %Y')}",
            "participants": [p.strip() for p in participants.split(",") if p.strip()] if participants else [],
            "started":      datetime.now().isoformat(),
            "notes":        [],
            "decisions":    [],
            "active":       True,
        }
        _save_session(session)
        ppl = ", ".join(session["participants"]) if session["participants"] else "participants not specified"
        return (
            f"✅ Meeting notes started!\n"
            f"**Meeting:** {session['title']}\n"
            f"**Participants:** {ppl}\n"
            f"**Time:** {datetime.now().strftime('%I:%M %p')}\n\n"
            f"Just talk — I'll capture everything. Say **'stop meeting'** when done."
        )

    session = _load_session()

    if action == "add_note":
        if not session:
            return "No active meeting session. Say 'start meeting notes' first."
        if not note:
            return "What should I add to the notes?"
        timestamp = datetime.now().strftime("%H:%M")
        entry = f"[{timestamp}] {note}"
        session["notes"].append(entry)
        _save_session(session)
        # Auto-detect decisions and action items
        if any(kw in note.lower() for kw in ["decided", "agreed", "confirmed", "resolved"]):
            session["decisions"].append(entry)
        return f"📝 Noted: {note}"

    if action == "stop":
        if not session:
            return "No active meeting to stop."
        session["active"] = False
        session["ended"] = datetime.now().isoformat()
        _save_session(session)
        n_notes    = len(session["notes"])
        n_actions  = len(_extract_action_items(session["notes"]))
        return (
            f"⏹ Meeting ended.\n"
            f"**Notes captured:** {n_notes}\n"
            f"**Action items detected:** {n_actions}\n\n"
            f"Say **'meeting summary'** to see the full notes, or **'save meeting notes'** to export."
        )

    if action == "action_items":
        if not session or not session.get("notes"):
            return "No meeting notes found. Start a meeting first."
        items = _extract_action_items(session["notes"])
        if not items:
            return "No explicit action items found. Try adding notes with words like 'will', 'must', 'by [date]', 'needs to'."
        numbered = "\n".join(f"{i+1}. {item}" for i, item in enumerate(items))
        return f"✅ **Action Items ({len(items)} found):**\n\n{numbered}"

    if action == "summary":
        if not session or not session.get("notes"):
            return "No meeting notes to summarize."
        started = session.get("started", "")
        ended   = session.get("ended", "")
        try:
            start_dt = datetime.fromisoformat(started).strftime("%I:%M %p")
            end_dt   = datetime.fromisoformat(ended).strftime("%I:%M %p") if ended else "ongoing"
            duration = ""
            if ended:
                delta = datetime.fromisoformat(ended) - datetime.fromisoformat(started)
                mins  = int(delta.total_seconds() / 60)
                duration = f" ({mins} min)"
        except Exception:
            start_dt = end_dt = duration = ""

        notes_block    = "\n".join(f"• {n}" for n in session["notes"])
        decisions_block = "\n".join(f"✓ {d}" for d in session.get("decisions", [])) or "None explicitly recorded"
        action_items   = _extract_action_items(session["notes"])
        actions_block  = "\n".join(f"→ {a}" for a in action_items) or "None detected"
        participants   = ", ".join(session.get("participants", [])) or "—"

        if fmt == "markdown":
            return (
                f"# 📋 {session['title']}\n\n"
                f"**Date:** {datetime.now().strftime('%A, %d %B %Y')}\n"
                f"**Time:** {start_dt} — {end_dt}{duration}\n"
                f"**Participants:** {participants}\n\n"
                f"## Discussion Notes\n{notes_block}\n\n"
                f"## Decisions Made\n{decisions_block}\n\n"
                f"## Action Items\n{actions_block}"
            )
        # Plain / bullets
        return (
            f"MEETING: {session['title']}\n"
            f"Date: {datetime.now().strftime('%d %B %Y')} | Participants: {participants}\n\n"
            f"NOTES:\n{notes_block}\n\n"
            f"DECISIONS:\n{decisions_block}\n\n"
            f"ACTION ITEMS:\n{actions_block}"
        )

    if action == "save":
        if not session or not session.get("notes"):
            return "No meeting notes to save."
        _NOTES_DIR.mkdir(parents=True, exist_ok=True)
        safe_title = re.sub(r"[^\w\s-]", "", session["title"])[:40].strip().replace(" ", "_")
        filename   = _NOTES_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M')}_{safe_title}.md"
        # Generate summary to save
        args_copy = dict(args)
        args_copy["action"] = "summary"
        args_copy["format"] = "markdown"
        content = run(args_copy)
        filename.write_text(content, encoding="utf-8")
        # Clear session
        _SESSION_FILE.unlink(missing_ok=True)
        return f"✅ Meeting notes saved to:\n{filename}"

    if action == "clear":
        _SESSION_FILE.unlink(missing_ok=True)
        return "Meeting notes cleared."

    return "Unknown meeting action."


def execute(**kwargs) -> Any:
    return run(kwargs)

