# actions/pro_tasks.py — Pro Brain task management action for Charlie
"""
Handles user voice/text commands that target the Pro Brain engine.

Supported voice commands:
  - "Do X and Y at the same time" -> submits 2 tasks in parallel
  - "What are you working on?" / "Task status" -> status_report
  - "Cancel task <id>" -> cancel
  - "What can you do?" -> lists all 30+ workflows
  - "Run <workflow>" -> direct workflow submission
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from engine.pro_brain import (
    WORKFLOW_TEMPLATES,
    TaskPriority,
    detect_workflow,
    get_pro_brain,
)


def _priority_from_text(text: str) -> TaskPriority:
    low = text.lower()
    if any(w in low for w in ("urgent", "critical", "asap", "emergency", "right now")):
        return TaskPriority.CRITICAL
    if any(w in low for w in ("high priority", "important", "quickly")):
        return TaskPriority.HIGH
    if any(w in low for w in ("background", "whenever", "no rush", "spare time")):
        return TaskPriority.BACKGROUND
    return TaskPriority.NORMAL


def _split_multi_goals(text: str) -> list[str]:
    """
    Splits 'do X and Y at the same time' / 'do X then do Y' into separate goals.
    Returns a list of 1+ goal strings.
    """
    # Remove leading interjections
    text = re.sub(r"^(charlie[,\s]+|hey charlie[,\s]+|please[,\s]+)", "", text, flags=re.I).strip()

    # Parallel patterns: "X and Y at the same time", "X while also doing Y"
    parallel_patterns = [
        r"\bat the same time\b",
        r"\bsimultaneously\b",
        r"\bat once\b",
        r"\bwhile (also\s+)?(doing|you're doing|you are doing)\b",
        r"\bparallel\b",
    ]
    for pat in parallel_patterns:
        if re.search(pat, text, re.I):
            # Split on "and" / "," after removing the trigger phrase
            cleaned = re.sub(pat, "", text, flags=re.I)
            parts = re.split(r"\band\b|,", cleaned, flags=re.I)
            goals = [p.strip() for p in parts if p.strip() and len(p.strip()) > 3]
            if len(goals) >= 2:
                return goals

    # Sequential patterns: "do X and then do Y"
    seq_patterns = [r"\band then\b", r"\bthen\b", r"\bafterward\b", r"\bnext\b"]
    for pat in seq_patterns:
        if re.search(pat, text, re.I):
            parts = re.split(pat, text, flags=re.I)
            goals = [p.strip() for p in parts if p.strip() and len(p.strip()) > 3]
            if len(goals) >= 2:
                return goals

    return [text.strip()]


def pro_tasks(
    parameters: Dict[str, Any],
    response=None,
    player=None,
    session_memory=None,
    speak=None,
) -> str:
    params = parameters or {}
    action = params.get("action", "submit").lower().strip()
    text   = params.get("text", params.get("goal", "")).strip()

    # Resolve plan tier from session memory / licensing
    plan_tier = "starter"
    if session_memory and hasattr(session_memory, "get"):
        plan_tier = session_memory.get("plan_tier", "starter") or "starter"

    brain = get_pro_brain(plan_tier=plan_tier, speak=speak)

    # ── STATUS ────────────────────────────────────────────────────────────────
    if action in ("status", "what are you doing", "task status", "progress"):
        return brain.status_report(verbose=True)

    # ── CANCEL ────────────────────────────────────────────────────────────────
    if action == "cancel":
        task_id = params.get("task_id", "").strip()
        if not task_id:
            # Try to parse from text: "cancel task abc123"
            m = re.search(r"cancel\s+(?:task\s+)?([a-f0-9]{8,10})", text, re.I)
            if m:
                task_id = m.group(1)
        if not task_id:
            return "Please tell me which task ID to cancel, sir."
        return brain.cancel(task_id)

    # ── TIER INFO ─────────────────────────────────────────────────────────────
    if action in ("tier", "plan info", "what plan"):
        return brain.get_tier_info()

    # ── LIST CAPABILITIES ─────────────────────────────────────────────────────
    if action in ("list", "capabilities", "what can you do", "what workflows"):
        wf_names = sorted(WORKFLOW_TEMPLATES.keys())
        lines = [
            f"Here are the {len(wf_names)} automated workflows I can run for you, sir:",
            "",
        ]
        categories = {
            "Video & Content":          ["youtube_upload", "youtube_script_to_short", "instagram_post", "social_media_repurpose", "video_edit_fast"],
            "Documents & Reports":      ["excel_full_report", "pdf_extract_and_summarize", "report_from_data", "presentation_builder", "email_batch_draft"],
            "Research & Intelligence":  ["deep_research", "competitor_analysis", "news_digest", "market_research"],
            "Coding & Development":     ["code_debug_fix", "code_review", "api_integration", "deploy_app"],
            "File & System":            ["folder_organise", "bulk_rename", "disk_cleanup", "backup_to_cloud"],
            "Communication":            ["meeting_prep", "email_triage", "task_planning"],
            "Business & Finance":       ["invoice_generate", "expense_report", "sales_analysis"],
            "Learning & Personal":      ["study_plan", "resume_enhance"],
        }
        for cat, wfs in categories.items():
            lines.append(f"  {cat}:")
            for wf in wfs:
                steps = WORKFLOW_TEMPLATES.get(wf, [])
                lines.append(f"    - {wf.replace('_', ' ').title()} ({len(steps)} steps)")
            lines.append("")

        lines.append("Just tell me what you want done and I'll pick the right workflow, sir.")
        return "\n".join(lines)

    # ── SUBMIT (default) ──────────────────────────────────────────────────────
    # This handles "submit", "run", or any other unrecognised action value
    if not text:
        text = action   # treat the whole action string as the goal

    if not text:
        return "Please tell me what task you'd like me to run, sir."

    priority = _priority_from_text(text)
    goals    = _split_multi_goals(text)

    if player:
        player.write_log(f"[ProBrain] Submitting {len(goals)} goal(s): {goals}")

    if len(goals) == 1:
        task_id, msg = brain.submit(goals[0], priority=priority)
        if speak and task_id:
            wf = detect_workflow(goals[0])
            steps = WORKFLOW_TEMPLATES.get(wf, [])
            speak(
                f"Starting '{wf.replace('_', ' ')}' workflow for you, sir. "
                f"I'll walk through {len(steps)} steps and let you know when done."
            )
        return msg

    # Multi-task parallel submission
    task_ids = []
    messages = []
    first_id: Optional[str] = None
    for i, goal in enumerate(goals):
        # Chain: second task depends on first only if they look sequential
        deps = []
        task_id, msg = brain.submit(
            goal,
            priority=priority,
            depends_on=deps,
        )
        task_ids.append(task_id)
        messages.append(f"  Task {i+1}: {msg}")
        if i == 0:
            first_id = task_id

    if speak:
        speak(
            f"I've queued {len(goals)} tasks for you, sir. "
            f"Running them in parallel on your {plan_tier.upper()} plan. "
            f"I'll tell you as each one completes."
        )

    return "\n".join([
        f"Queued {len(goals)} parallel tasks:",
        *messages,
        "",
        brain.status_report(),
    ])


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "pro_tasks",
    "description": (
        "Charlie's Pro Brain — submit, monitor, and cancel multi-step automated tasks. "
        "Use for: running parallel workflows, asking what Charlie is working on, "
        "cancelling a running task, listing all available automation workflows, "
        "or checking the current plan tier. "
        "Supports 30+ workflows: YouTube upload, Instagram post, Excel reports, "
        "deep research, code debug/fix, folder organisation, meeting prep, "
        "invoice generation, sales analysis, competitor analysis, and more."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "submit | status | cancel | list | tier (default: submit). "
                    "'submit' queues a new task. "
                    "'status' shows what's running. "
                    "'cancel' stops a task by ID. "
                    "'list' shows all available workflows."
                ),
            },
            "goal": {
                "type": "STRING",
                "description": (
                    "Natural language description of the task to perform. "
                    "Can contain multiple goals separated by 'and' or 'then'. "
                    "Example: 'research top 5 AI tools and build an Excel report at the same time'"
                ),
            },
            "text": {
                "type": "STRING",
                "description": "Alias for 'goal'. Used when goal is inferred from full user utterance.",
            },
            "task_id": {
                "type": "STRING",
                "description": "Task ID to cancel (cancel action only).",
            },
            "priority": {
                "type": "STRING",
                "description": "urgent | high | normal | low | background (default: normal)",
            },
        },
        "required": [],
    },
    "handler": pro_tasks,
}
