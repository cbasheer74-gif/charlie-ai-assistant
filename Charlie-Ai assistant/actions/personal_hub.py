"""Voice-facing personal companion, planning, coaching and family profiles."""

from __future__ import annotations

import json

from memory import personal_hub as hub
from memory.profile_manager import create_profile, list_profiles, switch_profile


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _listing(items: list[dict], empty: str) -> str:
    return _json(items) if items else empty


def personal_hub(parameters: dict, player=None, session_memory=None) -> str:
    action = str(parameters.get("action") or "status").strip().lower()

    try:
        if action == "status":
            return hub.prompt_context()

        if action == "companion_mode":
            settings = hub.set_companion(parameters.get("mode"), parameters.get("check_in"))
            if player:
                player.write_log(
                    f"COMPANION: {settings['mode'].title()} mode; check-ins {settings['check_in']}.")
            return (
                f"Companion mode is now {settings['mode']}; check-ins are {settings['check_in']}. "
                "Follow that interaction style immediately."
            )

        if action == "companion_checkin":
            return (
                hub.prompt_context()
                + "\nAsk one warm, specific follow-up based on the user's active goals or tasks. "
                  "Do not use a generic 'How can I help?' question."
            )

        if action == "speech_set":
            settings = hub.set_speech_preferences(
                parameters.get("speech_style"), parameters.get("pace"),
                parameters.get("language"), parameters.get("address"))
            if player:
                player.write_log(
                    f"VOICE: {settings['style'].title()} style, {settings['pace']} pace, "
                    f"{settings['language']} language.")
            return (
                f"Natural speech preferences updated: {_json(settings)}\n"
                "Use these preferences immediately and confirm in one natural sentence."
            )

        if action == "speech_status":
            return _json(hub.load_hub().get("speech", {}))

        if action == "goal_add":
            goal = hub.add_goal(parameters.get("title", ""), parameters.get("due", ""),
                                parameters.get("next_step", ""))
            return f"Goal added for this profile: {_json(goal)}"

        if action == "goal_update":
            progress = parameters.get("progress")
            goal = hub.update_goal(parameters.get("id_or_name", ""), parameters.get("status", ""),
                                   int(progress) if progress is not None else None,
                                   parameters.get("next_step", ""))
            return f"Goal updated: {_json(goal)}"

        if action == "goal_list":
            goals = hub.load_hub()["goals"]
            return _listing(goals, "No goals have been saved for this profile.")

        if action == "task_add":
            date = str(parameters.get("date") or "").strip()
            time = str(parameters.get("time") or "").strip()
            due = " ".join(part for part in (date, time) if part)
            task = hub.add_task(parameters.get("title", ""), due, parameters.get("priority", "normal"))
            reminder_result = ""
            if date and time and parameters.get("set_reminder", True):
                from actions.reminder import reminder
                reminder_result = reminder(
                    {"date": date, "time": time, "message": task["title"]}, player=player)
            return f"Task added: {_json(task)}" + (f"\n{reminder_result}" if reminder_result else "")

        if action == "task_complete":
            task = hub.complete_task(parameters.get("id_or_name", ""))
            return f"Task completed: {task['title']}"

        if action == "task_list":
            tasks = hub.load_hub()["tasks"]
            return _listing(tasks, "No tasks have been saved for this profile.")

        if action == "event_add":
            date = str(parameters.get("date") or "").strip()
            time = str(parameters.get("time") or "").strip()
            starts_at = " ".join(part for part in (date, time) if part)
            event = hub.add_event(parameters.get("title", ""), starts_at,
                                  parameters.get("location", ""), parameters.get("note", ""))
            reminder_result = ""
            if date and time and parameters.get("set_reminder", True):
                from actions.reminder import reminder
                reminder_result = reminder(
                    {"date": date, "time": time, "message": event["title"]}, player=player)
            return f"Calendar event added: {_json(event)}" + (
                f"\n{reminder_result}" if reminder_result else "")

        if action == "event_list":
            return _listing(hub.daily_plan()["events"], "No upcoming calendar events saved.")

        if action == "daily_plan":
            plan = hub.daily_plan()
            return (
                "Build a concise, realistic plan for today from this profile-only data. "
                "Prioritize overdue/high-priority tasks, one goal step, and one learning block:\n"
                + _json(plan)
            )

        if action == "learning_start":
            track = hub.start_learning(parameters.get("subject", ""),
                                       parameters.get("objective", ""),
                                       parameters.get("language", ""))
            return f"Learning track created: {_json(track)}"

        if action == "learning_session":
            tracks = hub.load_hub()["learning"]
            wanted = parameters.get("id_or_name", "")
            selected = next((t for t in reversed(tracks)
                             if str(wanted).casefold() in {
                                 str(t.get('id', '')).casefold(), str(t.get('subject', '')).casefold()
                             }), None)
            if not selected:
                return f"No learning track named '{wanted}'. Create it first."
            return (
                "Run a short interactive lesson now. Explain one concept, give one example, then ask "
                "one question and wait for the user's answer. Correct gently and adapt to their language.\n"
                + _json(selected)
            )

        if action == "learning_update":
            progress = parameters.get("progress")
            track = hub.update_learning(parameters.get("id_or_name", ""),
                                        int(progress) if progress is not None else None,
                                        parameters.get("note", ""))
            return f"Learning progress updated: {_json(track)}"

        if action == "learning_list":
            return _listing(hub.load_hub()["learning"], "No learning tracks saved.")

        if action == "meeting_start":
            meeting = hub.start_meeting(parameters.get("title", "Meeting"))
            if player:
                player.write_log(f"MEETING: Recording notes for {meeting['title']}.")
            return (
                f"Meeting capture started: {meeting['title']}. Tell the user that the visible/live "
                "conversation transcript will be saved locally until they say stop meeting."
            )

        if action == "meeting_status":
            meeting = hub.active_meeting()
            if not meeting:
                return "No meeting capture is active."
            return _json({"id": meeting["id"], "title": meeting["title"],
                          "status": meeting["status"],
                          "captured_turns": len(meeting.get("transcript", []))})

        if action == "meeting_stop":
            meeting = hub.stop_meeting()
            transcript = "\n".join(
                f"{row.get('speaker', 'Unknown')}: {row.get('text', '')}"
                for row in meeting.get("transcript", [])
            )[-16000:]
            return (
                f"Meeting ID: {meeting['id']}\nTitle: {meeting['title']}\n"
                "Summarize the decisions and action items from this transcript. Then call "
                "personal_hub with action=meeting_finalize, this meeting ID, the summary, "
                "and action_items so they are saved.\nTRANSCRIPT:\n" + transcript
            )

        if action == "meeting_finalize":
            meeting = hub.finalize_meeting(parameters.get("id_or_name", ""),
                                           parameters.get("summary", ""),
                                           parameters.get("action_items", []))
            if player:
                player.write_log(f"MEETING: Summary saved — {meeting['title']}.")
            compact = {k: meeting.get(k) for k in
                       ("id", "title", "status", "summary", "action_items")}
            return f"Meeting summary saved locally: {_json(compact)}"

        if action == "meeting_list":
            meetings = hub.load_hub()["meetings"]
            compact = [{k: m.get(k) for k in ("id", "title", "status", "started_at", "summary", "action_items")}
                       for m in meetings[-10:]]
            return _listing(compact, "No meetings saved for this profile.")

        if action == "profile_create":
            profile = create_profile(parameters.get("profile", ""))
            return f"Profile created: {_json(profile)}. It is private and empty until switched to."

        if action == "profile_switch":
            profile = switch_profile(parameters.get("profile", ""))
            if player:
                player.write_log(f"PROFILE: Switched to {profile['name']}.")
            return (
                f"Switched to {profile['name']}. A fresh voice session is starting so this user's "
                "private memory and plans are loaded."
            )

        if action == "profile_list":
            return _listing(list_profiles(), "No profiles available.")

        if action == "privacy_summary":
            return (
                "Personal memory, goals, tasks, learning progress, meeting transcripts, and recent "
                "conversation are stored locally in separate folders for each profile. Profile data "
                "is never shown to another active profile."
            )

        return f"Unknown personal_hub action: {action}"
    except (ValueError, TypeError) as exc:
        return str(exc)


TOOL = {
    "name": "personal_hub",
    "description": (
        "Manages CHARLIE personal companion behavior, goals, calendar events, daily tasks/plans, learning coaching, "
        "meeting capture/summaries, and private family profiles. Use it whenever the user asks Charlie "
        "to listen or advise in a specific style; change speaking style, pace, language, or form of "
        "address (for example: speak slower, sound warmer, use Hinglish, or do not call me sir); "
        "remember/track a goal; plan the day; add or complete "
        "a task or calendar event; teach, quiz, or practise a language; start/stop a meeting; or create/switch profiles."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": (
                "status | companion_mode | companion_checkin | speech_set | speech_status | "
                "goal_add | goal_update | goal_list | "
                "task_add | task_complete | task_list | event_add | event_list | daily_plan | learning_start | learning_session | "
                "learning_update | learning_list | meeting_start | meeting_status | meeting_stop | "
                "meeting_finalize | meeting_list | profile_create | profile_switch | profile_list | privacy_summary")},
            "mode": {"type": "STRING", "description": "Companion mode: listen, advice, or act."},
            "check_in": {"type": "STRING", "description": "Check-in frequency: manual, daily, weekly, or off."},
            "speech_style": {"type": "STRING", "description":
                             "Voice delivery: warm, friendly, calm, professional, energetic, or companion."},
            "pace": {"type": "STRING", "description": "Speaking pace: slow, natural, or fast."},
            "address": {"type": "STRING", "description":
                        "How to address the user: occasional, name, casual, or none."},
            "title": {"type": "STRING", "description": "Goal, task, or meeting title."},
            "id_or_name": {"type": "STRING", "description": "Existing goal/task/learning/meeting ID or name."},
            "status": {"type": "STRING", "description": "Goal status: active, paused, or completed."},
            "progress": {"type": "INTEGER", "description": "Progress percentage from 0 to 100."},
            "due": {"type": "STRING", "description": "Optional due date or natural short due label."},
            "next_step": {"type": "STRING", "description": "Concrete next action for a goal."},
            "date": {"type": "STRING", "description": "Task/reminder date as YYYY-MM-DD."},
            "time": {"type": "STRING", "description": "Task/reminder time as HH:MM in local time."},
            "priority": {"type": "STRING", "description": "Task priority: low, normal, or high."},
            "location": {"type": "STRING", "description": "Optional calendar event location."},
            "set_reminder": {"type": "BOOLEAN", "description": "Schedule an OS reminder when task date/time are present."},
            "subject": {"type": "STRING", "description": "Learning subject or language."},
            "objective": {"type": "STRING", "description": "What the user wants to achieve."},
            "language": {"type": "STRING", "description": "Preferred teaching/explanation language."},
            "note": {"type": "STRING", "description": "Learning session note."},
            "summary": {"type": "STRING", "description": "Meeting summary for meeting_finalize."},
            "action_items": {"type": "ARRAY", "items": {"type": "STRING"},
                             "description": "Meeting action items."},
            "profile": {"type": "STRING", "description": "Family profile name or ID."},
        },
        "required": ["action"],
    },
    "handler": personal_hub,
}
