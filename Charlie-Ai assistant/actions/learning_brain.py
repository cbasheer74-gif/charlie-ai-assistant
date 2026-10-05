"""Voice-facing router for CHARLIE's ten adaptive learning capabilities."""

from __future__ import annotations

import json

from memory import learning_brain as brain


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def learning_brain(parameters: dict, player=None, action_registry=None, **_unused) -> str:
    params = parameters or {}
    action = str(params.get("action") or "status").strip().lower()
    try:
        # 1. Learn from corrections
        if action == "correction_add":
            from actions.remember_correction import remember_correction
            return remember_correction(params, player=player)
        if action == "correction_list":
            from memory.memory_manager import load_memory
            values = load_memory().get("corrections", {})
            return _json(values) if values else "No explicit corrections saved for this profile."

        # 2. Teach by demonstration (reuses the proven recorder/compiler)
        if action.startswith("demonstration_"):
            from actions.manage_skills import manage_skills
            mapped = {
                "demonstration_start": "start_teach", "demonstration_status": "teach_status",
                "demonstration_stop": "stop_teach", "demonstration_cancel": "cancel_teach",
                "demonstration_list": "list", "demonstration_run": "execute",
            }.get(action)
            if not mapped:
                raise ValueError("Unknown demonstration action.")
            return manage_skills({**params, "action": mapped}, player=player,
                                 action_registry=action_registry)

        # 3. Routine and habit learning
        if action == "routine_scan":
            routines = brain.discover_routines(int(params.get("minimum_repeats", 3)))
            if not routines:
                return "No repeated routine is strong enough to suggest yet."
            return ("These are suggestions only. Ask before automating any of them:\n" +
                    _json(routines))
        if action == "routine_decide":
            result = brain.decide_routine(params.get("signature", ""),
                                          params.get("decision", ""),
                                          params.get("name", ""))
            return "Routine preference saved. No action was run.\n" + _json(result)

        # 4. Emotional intelligence controls
        if action == "emotion_support":
            settings = brain.update_settings(emotion_support=params.get("enabled"))
            return f"Emotional conversation support is {'on' if settings['emotion_support'] else 'off'}."
        if action == "emotion_status":
            data = brain.load_brain()
            return _json({"enabled": data["settings"]["emotion_support"],
                          "recent_cues": data["moods"][-5:]})

        # 5. Personal knowledge vault
        if action == "knowledge_add":
            result = brain.add_knowledge(params.get("file_path", ""), params.get("title", ""))
            return "Added to this profile's private local knowledge vault:\n" + _json(result)
        if action == "knowledge_list":
            docs = brain.load_brain()["knowledge"]
            compact = [{k: row.get(k) for k in ("id", "title", "file_name", "characters", "added_at")}
                       for row in docs]
            return _json(compact) if compact else "This profile's knowledge vault is empty."
        if action == "knowledge_query":
            results = brain.search_knowledge(params.get("query", ""), int(params.get("limit", 5)))
            return ("Answer using only these private-vault excerpts and identify the document title. "
                    "Say when the excerpts are insufficient:\n" + _json(results)) if results else (
                    "No relevant passage was found in this profile's knowledge vault.")
        if action == "knowledge_remove":
            removed = brain.remove_knowledge(params.get("id_or_name", ""))
            return "Knowledge document removed." if removed else "Knowledge document not found."

        # 6. Relationship memory
        if action == "relationship_add":
            result = brain.remember_relationship(
                params.get("name", ""), params.get("relation", ""), params.get("details", ""),
                params.get("important_date", ""), params.get("follow_up", ""))
            return "Relationship memory updated for this profile:\n" + _json(result)
        if action == "relationship_list":
            values = brain.list_relationships()
            return _json(values) if values else "No relationship memories saved for this profile."

        # 7. Privacy-aware Vision Copilot
        if action == "vision_mode":
            settings = brain.update_settings(vision_copilot=params.get("mode", "ask"))
            return f"Vision Copilot privacy mode is now {settings['vision_copilot']}."
        if action == "vision_help":
            mode = brain.load_brain()["settings"]["vision_copilot"]
            if mode == "off":
                return "Vision Copilot is off. Ask the user to enable it before capturing the screen."
            return ("Call screen_process once with angle=screen and the user's exact question. "
                    "Analyze only that captured frame; do not claim continuous monitoring.")

        # 8. Conversation activities
        if action == "activity_start":
            instruction = brain.start_activity(params.get("activity", ""), params.get("topic", ""))
            return instruction + " Start now, keep it conversational, and wait after one question or choice."

        # 9. Optional local voice identification
        if action == "voice_enroll":
            result = brain.enroll_recent_voice(bool(params.get("consent", False)))
            return "Local voice sample enrolled.\n" + _json(result)
        if action == "voice_identify":
            result = brain.identify_recent_voice()
            if result.get("matched") and params.get("switch_profile", True):
                from memory.profile_manager import active_profile_id, switch_profile
                if result["profile_id"] != active_profile_id():
                    switch_profile(result["profile_id"])
                    result["switched"] = True
            return _json(result)
        if action == "voice_identity_mode":
            settings = brain.update_settings(voice_identification=params.get("enabled"))
            return ("Local convenience voice matching is now "
                    f"{'on' if settings['voice_identification'] else 'off'}. "
                    "It never authorizes sensitive actions.")
        if action == "voice_delete":
            brain.delete_voiceprint()
            return "This profile's local voiceprint was deleted and voice matching was disabled."

        # 10. Personal daily intelligence
        if action == "daily_intelligence":
            snapshot = brain.daily_intelligence(params.get("review", "morning"))
            return ("Create a useful spoken briefing from this profile-only snapshot. Prioritize, do "
                    "not dump every field, and finish with one realistic next action:\n" + _json(snapshot))
        if action == "daily_intelligence_mode":
            settings = brain.update_settings(daily_intelligence=params.get("enabled"))
            return f"Personal daily intelligence is {'on' if settings['daily_intelligence'] else 'off'}."

        if action == "status":
            data = brain.load_brain()
            return _json({
                "settings": data["settings"],
                "knowledge_documents": len(data["knowledge"]),
                "relationships": len(data["relationships"]),
                "voice_samples": len(data["voiceprint"].get("samples", [])),
                "recent_moods": data["moods"][-3:],
            })

        return f"Unknown learning_brain action: {action}"
    except (ValueError, TypeError, OSError) as exc:
        return str(exc)


TOOL = {
    "name": "learning_brain",
    "description": (
        "CHARLIE adaptive learning brain. Use for explicit corrections; recording/replaying a task "
        "demonstration; detecting repeated routines (suggest only, never auto-run); emotional support "
        "preferences; adding/querying a private knowledge file; remembering people and follow-ups; "
        "privacy-aware screen help; stories, quizzes, debates, interviews, language role-play, meditation, "
        "motivation or games; opt-in local voice-profile matching; and morning/evening personal intelligence."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": (
                "status | correction_add | correction_list | demonstration_start | demonstration_status | "
                "demonstration_stop | demonstration_cancel | demonstration_list | demonstration_run | "
                "routine_scan | routine_decide | emotion_support | emotion_status | knowledge_add | "
                "knowledge_list | knowledge_query | knowledge_remove | relationship_add | relationship_list | "
                "vision_mode | vision_help | activity_start | voice_enroll | voice_identify | "
                "voice_identity_mode | voice_delete | daily_intelligence | daily_intelligence_mode")},
            "correction": {"type": "STRING", "description": "Explicit correction to remember."},
            "context": {"type": "STRING", "description": "Optional correction context."},
            "name": {"type": "STRING", "description": "Workflow, routine, or person's name."},
            "workflow": {"type": "STRING", "description": "Demonstration purpose or intent."},
            "inputs": {"type": "OBJECT", "description": "Inputs for a learned workflow replay."},
            "minimum_repeats": {"type": "INTEGER", "description": "Routine repetitions required; default 3."},
            "signature": {"type": "STRING", "description": "Exact routine signature returned by routine_scan."},
            "decision": {"type": "STRING", "description": "approved or dismissed."},
            "enabled": {"type": "BOOLEAN", "description": "Enable/disable the selected learning feature."},
            "file_path": {"type": "STRING", "description": "Local document path for knowledge_add."},
            "title": {"type": "STRING", "description": "Optional knowledge document title."},
            "query": {"type": "STRING", "description": "Private knowledge question/search terms."},
            "limit": {"type": "INTEGER", "description": "Maximum knowledge excerpts."},
            "id_or_name": {"type": "STRING", "description": "Saved document ID, title, or file name."},
            "relation": {"type": "STRING", "description": "Person's relationship to the user."},
            "details": {"type": "STRING", "description": "Useful non-secret relationship context."},
            "important_date": {"type": "STRING", "description": "Birthday or other important date."},
            "follow_up": {"type": "STRING", "description": "Something CHARLIE should ask about later."},
            "mode": {"type": "STRING", "description": "Vision mode: off, ask, or on."},
            "activity": {"type": "STRING", "description":
                         "story, quiz, debate, interview, language, meditation, motivation, game, or surprise."},
            "topic": {"type": "STRING", "description": "Conversation activity topic."},
            "consent": {"type": "BOOLEAN", "description":
                        "True only after explicit user consent to store a local voice embedding."},
            "switch_profile": {"type": "BOOLEAN", "description":
                               "Switch to a confidently matched profile; default true."},
            "review": {"type": "STRING", "description": "morning or evening."},
        },
        "required": ["action"],
    },
    "handler": learning_brain,
}
