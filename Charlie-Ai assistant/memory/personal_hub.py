"""Persistent companion, planning, learning and meeting state per profile."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from threading import RLock
from uuid import uuid4

from memory.profile_manager import active_profile, notify_context_change, profile_hub_path

_lock = RLock()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _empty() -> dict:
    return {
        "version": 1,
        "companion": {"mode": "advice", "check_in": "manual"},
        "speech": {
            "style": "warm",
            "pace": "natural",
            "language": "auto",
            "address": "occasional",
            "voice_gender": "female",
        },
        "goals": [],
        "tasks": [],
        "events": [],
        "learning": [],
        "meetings": [],
        "recent_conversation": [],
    }


def load_hub() -> dict:
    path = profile_hub_path()
    with _lock:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    base = _empty()
                    for key, value in base.items():
                        data.setdefault(key, value)
                    return data
            except Exception:
                pass
        return _empty()


def save_hub(data: dict) -> None:
    path = profile_hub_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    with _lock:
        temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)


def set_companion(mode: str | None = None, check_in: str | None = None) -> dict:
    data = load_hub()
    if mode:
        mode = mode.strip().lower()
        if mode not in {"listen", "advice", "act"}:
            raise ValueError("Companion mode must be listen, advice, or act.")
        data["companion"]["mode"] = mode
    if check_in:
        check_in = check_in.strip().lower()
        if check_in not in {"manual", "daily", "weekly", "off"}:
            raise ValueError("Check-in must be manual, daily, weekly, or off.")
        data["companion"]["check_in"] = check_in
    save_hub(data)
    notify_context_change()
    return dict(data["companion"])


def set_speech_preferences(style: str | None = None, pace: str | None = None,
                           language: str | None = None,
                           address: str | None = None,
                           voice_gender: str | None = None) -> dict:
    """Persist natural speech direction for only the active family profile."""
    try:
        from core.languages import get_all_language_keys
        valid_languages = get_all_language_keys()
    except Exception:
        valid_languages = {"auto", "english", "hindi", "hinglish"}
    allowed = {
        "style": {"warm", "friendly", "calm", "professional", "energetic", "companion"},
        "pace": {"slow", "natural", "fast"},
        "language": valid_languages,
        "address": {"occasional", "name", "casual", "none"},
        "voice_gender": {"female", "male"},
    }
    incoming = {"style": style, "pace": pace, "language": language,
                "address": address, "voice_gender": voice_gender}
    data = load_hub()
    speech = data.setdefault("speech", _empty()["speech"])
    for key, value in incoming.items():
        if value is None or str(value).strip() == "":
            continue
        normalized = str(value).strip().lower()
        if normalized not in allowed[key]:
            raise ValueError(f"Speech {key} must be a valid supported option.")
        speech[key] = normalized
    save_hub(data)
    notify_context_change()
    return dict(speech)


def checkin_due() -> bool:
    companion = load_hub().get("companion", {})
    frequency = companion.get("check_in", "manual")
    if frequency not in {"daily", "weekly"}:
        return False
    try:
        last = datetime.fromisoformat(companion.get("last_check_in", ""))
    except (TypeError, ValueError):
        return True
    gap = timedelta(days=1 if frequency == "daily" else 7)
    return datetime.now() - last >= gap


def mark_checkin() -> None:
    data = load_hub()
    data["companion"]["last_check_in"] = _now()
    save_hub(data)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


def add_goal(title: str, due: str = "", next_step: str = "") -> dict:
    if not title.strip():
        raise ValueError("Goal title is required.")
    data = load_hub()
    goal = {"id": _new_id("goal"), "title": title.strip()[:180], "status": "active",
            "progress": 0, "due": due.strip()[:30], "next_step": next_step.strip()[:220],
            "created_at": _now(), "updated_at": _now()}
    data["goals"].append(goal)
    save_hub(data)
    return goal


def update_goal(identifier: str, status: str = "", progress: int | None = None,
                next_step: str = "") -> dict:
    data = load_hub()
    goal = _find(data["goals"], identifier)
    if not goal:
        raise ValueError(f"Goal '{identifier}' was not found.")
    if status:
        status = status.lower()
        if status not in {"active", "paused", "completed"}:
            raise ValueError("Goal status must be active, paused, or completed.")
        goal["status"] = status
    if progress is not None:
        goal["progress"] = max(0, min(100, int(progress)))
    if next_step:
        goal["next_step"] = next_step.strip()[:220]
    goal["updated_at"] = _now()
    save_hub(data)
    return goal


def add_task(title: str, due: str = "", priority: str = "normal") -> dict:
    if not title.strip():
        raise ValueError("Task title is required.")
    priority = priority.lower()
    if priority not in {"low", "normal", "high"}:
        priority = "normal"
    data = load_hub()
    task = {"id": _new_id("task"), "title": title.strip()[:180], "due": due.strip()[:30],
            "priority": priority, "completed": False, "created_at": _now()}
    data["tasks"].append(task)
    save_hub(data)
    return task


def complete_task(identifier: str) -> dict:
    data = load_hub()
    task = _find(data["tasks"], identifier)
    if not task:
        raise ValueError(f"Task '{identifier}' was not found.")
    task["completed"] = True
    task["completed_at"] = _now()
    save_hub(data)
    return task


def add_event(title: str, starts_at: str, location: str = "", notes: str = "") -> dict:
    if not title.strip() or not starts_at.strip():
        raise ValueError("Calendar events need both a title and start date/time.")
    data = load_hub()
    event = {"id": _new_id("event"), "title": title.strip()[:180],
             "starts_at": starts_at.strip()[:40], "location": location.strip()[:180],
             "notes": notes.strip()[:500], "created_at": _now()}
    data["events"].append(event)
    save_hub(data)
    return event


def start_learning(subject: str, objective: str = "", language: str = "") -> dict:
    if not subject.strip():
        raise ValueError("Learning subject is required.")
    data = load_hub()
    track = {"id": _new_id("learn"), "subject": subject.strip()[:100],
             "objective": objective.strip()[:220], "language": language.strip()[:40],
             "progress": 0, "sessions": 0, "last_note": "", "created_at": _now()}
    data["learning"].append(track)
    save_hub(data)
    return track


def update_learning(identifier: str, progress: int | None = None, note: str = "") -> dict:
    data = load_hub()
    track = _find(data["learning"], identifier)
    if not track:
        raise ValueError(f"Learning track '{identifier}' was not found.")
    if progress is not None:
        track["progress"] = max(0, min(100, int(progress)))
    track["sessions"] = int(track.get("sessions", 0)) + 1
    if note:
        track["last_note"] = note.strip()[:260]
    track["updated_at"] = _now()
    save_hub(data)
    return track


def start_meeting(title: str = "Meeting") -> dict:
    data = load_hub()
    for meeting in data["meetings"]:
        if meeting.get("status") == "recording":
            raise ValueError(f"'{meeting['title']}' is already being recorded.")
    meeting = {"id": _new_id("meeting"), "title": (title or "Meeting").strip()[:160],
               "status": "recording", "started_at": _now(), "transcript": [],
               "summary": "", "action_items": []}
    data["meetings"].append(meeting)
    save_hub(data)
    return meeting


def active_meeting() -> dict | None:
    for meeting in reversed(load_hub()["meetings"]):
        if meeting.get("status") == "recording":
            return meeting
    return None


def record_conversation_turn(speaker: str, text: str) -> None:
    text = " ".join(str(text or "").split())
    if not text:
        return
    data = load_hub()
    entry = {"speaker": speaker, "text": text[:1200], "at": _now()}
    data["recent_conversation"].append(entry)
    data["recent_conversation"] = data["recent_conversation"][-40:]
    for meeting in reversed(data["meetings"]):
        if meeting.get("status") == "recording":
            meeting["transcript"].append(entry)
            meeting["transcript"] = meeting["transcript"][-500:]
            break
    save_hub(data)
    if str(speaker).casefold() == "user":
        try:
            from memory.learning_brain import observe_user_turn
            observe_user_turn(text)
        except Exception:
            pass


def stop_meeting() -> dict:
    data = load_hub()
    meeting = next((m for m in reversed(data["meetings"]) if m.get("status") == "recording"), None)
    if not meeting:
        raise ValueError("No meeting recording is active.")
    meeting["status"] = "awaiting_summary"
    meeting["ended_at"] = _now()
    save_hub(data)
    return meeting


def finalize_meeting(identifier: str, summary: str, action_items: list | str | None = None) -> dict:
    data = load_hub()
    meeting = _find(data["meetings"], identifier)
    if not meeting:
        raise ValueError(f"Meeting '{identifier}' was not found.")
    if isinstance(action_items, str):
        action_items = [line.strip(" -") for line in action_items.splitlines() if line.strip(" -")]
    meeting["summary"] = str(summary or "").strip()[:3000]
    meeting["action_items"] = [str(item)[:300] for item in (action_items or [])][:30]
    meeting["status"] = "completed"
    save_hub(data)
    return meeting


def _find(items: list[dict], identifier: str) -> dict | None:
    wanted = str(identifier or "").strip().casefold()
    if not wanted:
        return None
    for item in reversed(items):
        names = {str(item.get("id", "")).casefold(), str(item.get("title", "")).casefold(),
                 str(item.get("subject", "")).casefold()}
        if wanted in names or any(wanted and wanted in name for name in names):
            return item
    return None


def daily_plan() -> dict:
    data = load_hub()
    today = date.today().isoformat()
    tasks = [t for t in data["tasks"] if not t.get("completed")]
    tasks.sort(key=lambda t: (t.get("due") not in {today, ""},
                              {"high": 0, "normal": 1, "low": 2}.get(t.get("priority"), 1),
                              t.get("due") or "9999"))
    goals = [g for g in data["goals"] if g.get("status") == "active"]
    learning = [x for x in data["learning"] if int(x.get("progress", 0)) < 100]
    events = [e for e in data["events"] if str(e.get("starts_at", "")) >= today]
    if not events and data.get("events"):
        events = list(data["events"])
    events.sort(key=lambda e: e.get("starts_at", "9999"))
    return {"date": today, "events": events[:10], "tasks": tasks[:10],
            "goals": goals[:5], "learning": learning[:3]}


def prompt_context() -> str:
    profile = active_profile()
    data = load_hub()
    plan = daily_plan()
    mode = data["companion"].get("mode", "advice")
    mode_rule = {
        "listen": "Listen supportively. Do not give advice or take action unless explicitly asked.",
        "advice": "Offer concise, practical advice after acknowledging the user's feelings or context.",
        "act": "Prefer helping the user take a concrete next step, using tools when appropriate.",
    }[mode]
    speech = data.get("speech", _empty()["speech"])
    style = speech.get("style", "warm")
    pace = speech.get("pace", "natural")
    language = speech.get("language", "auto")
    address = speech.get("address", "occasional")
    style_rule = {
        "warm": "Sound warm, reassuring, and quietly confident.",
        "friendly": "Sound friendly and relaxed, like a capable long-time companion.",
        "calm": "Use an unhurried, grounded tone with gentle emphasis.",
        "professional": "Sound polished, clear, and concise without becoming stiff.",
        "energetic": "Sound lively and encouraging without exaggeration.",
        "companion": "Sound present, caring, curious, and emotionally attentive.",
    }.get(style, "Sound warm and natural.")
    pace_rule = {
        "slow": "Speak a little slower and leave comfortable pauses between ideas.",
        "natural": "Use a natural conversational rhythm with varied sentence length.",
        "fast": "Speak briskly while keeping every word clear.",
    }.get(pace, "Use a natural conversational rhythm.")
    try:
        from core.languages import get_language_prompt_rule
        language_rule = get_language_prompt_rule(language)
    except Exception:
        language_rule = f"Reply in natural conversational {language} or mirror the user's current language."
    address_rule = {
        "occasional": "Use the user's name or respectful address only occasionally, not in every reply.",
        "name": "Prefer the user's name, but do not repeat it mechanically.",
        "casual": "Use a casual direct address and do not call the user sir.",
        "none": "Do not use names, honorifics, sir, or other forms of address.",
    }.get(address, "Do not repeat forms of address mechanically.")
    lines = ["[PERSONAL HUB]", f"Active user profile: {profile['name']}",
             f"Companion mode: {mode}. {mode_rule}",
             "[NATURAL SPEECH DIRECTOR]",
             f"Style: {style}. {style_rule}",
             f"Pace: {pace}. {pace_rule}",
             f"Language: {language}. {language_rule}",
             address_rule,
             "Speak for listening, not for reading: use contractions where natural, vary rhythm, "
             "and acknowledge the user's meaning before advice. Avoid headings, numbered reports, "
             "repeated catchphrases, fake laughter, and filler words. Use brief human acknowledgements "
             "only when they fit. Do not announce that you are being natural or following a style.",
             "VOICE CONSISTENCY: Use exactly one speaker identity and the configured voice for the "
             "entire reply. Never imitate or switch to a second speaker for quotes, characters, tools, "
             "or another language; describe them naturally in your own single voice."]
    if plan["goals"]:
        lines.append("Active goals: " + "; ".join(
            f"{g['title']} ({g.get('progress', 0)}%, next: {g.get('next_step') or 'not set'})"
            for g in plan["goals"][:4]))
    if plan["tasks"]:
        lines.append("Open tasks: " + "; ".join(
            f"{t['title']} (due {t.get('due') or 'unscheduled'}, {t.get('priority', 'normal')})"
            for t in plan["tasks"][:6]))
    if plan["events"]:
        lines.append("Upcoming calendar: " + "; ".join(
            f"{e['title']} ({e.get('starts_at')})" for e in plan["events"][:5]))
    if plan["learning"]:
        lines.append("Learning tracks: " + "; ".join(
            f"{x['subject']} ({x.get('progress', 0)}%)" for x in plan["learning"][:3]))
    recent = data.get("recent_conversation", [])[-6:]
    if recent:
        recap = " | ".join(f"{row.get('speaker')}: {row.get('text', '')}" for row in recent)
        lines.append("Recent conversation continuity: " + recap[-1200:])
    try:
        from memory.learning_brain import prompt_context as learning_context
        lines.append(learning_context())
    except Exception:
        pass
    lines.append("Never mix this profile's personal information with another profile.")
    return "\n".join(lines)


def generate_daily_briefing() -> str:
    """Generate an executive, human-style daily briefing of tasks, events, and focus."""
    hub = load_hub()
    profile = active_profile()
    name = profile.get("name", "there")
    now_dt = datetime.now()
    date_str = now_dt.strftime("%A, %B %d")

    parts = [f"Good day, {name}. Here is your executive briefing for {date_str}."]

    # Events
    events = hub.get("events", [])
    if events:
        evt_strs = [f"- {e['title']} at {e.get('starts_at', 'scheduled time')}" for e in events[:4]]
        parts.append("[SCHEDULE]\n" + "\n".join(evt_strs))
    else:
        parts.append("[SCHEDULE] No calendar events logged for today.")

    # Urgent tasks
    tasks = hub.get("tasks", [])
    if tasks:
        task_strs = [f"- {t['title']} (Due: {t.get('due') or 'Today'}, Priority: {t.get('priority', 'normal')})" for t in tasks[:5]]
        parts.append("[PRIORITY TASKS]\n" + "\n".join(task_strs))
    else:
        parts.append("[TASKS] All task queues are currently clear.")

    # Goals & Learning
    goals = hub.get("goals", [])
    learning = hub.get("learning", [])
    highlights = []
    if goals:
        top_goal = goals[0]
        highlights.append(f"Primary Goal: {top_goal['title']} ({top_goal.get('progress', 0)}% completed)")
    if learning:
        top_learn = learning[0]
        highlights.append(f"Learning Track: {top_learn['subject']} ({top_learn.get('progress', 0)}% mastery)")
    if highlights:
        parts.append("[ACTIVE FOCUS]\n" + "\n".join(f"- {h}" for h in highlights))

    parts.append("Charlie is standing by whenever you are ready.")
    return "\n\n".join(parts)


