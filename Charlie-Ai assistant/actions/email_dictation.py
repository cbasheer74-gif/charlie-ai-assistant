# actions/email_dictation.py
"""
Smart Email Dictation — Charlie drafts, edits, formats and sends emails by voice.

Voice commands:
  "Draft an email to Rahul about the project deadline"
  "Add a professional closing"
  "Make it more formal"
  "Send it"
  "Show me the draft"

Opens the system default mail client with pre-filled subject + body, OR
uses mailto: URI which works with any email client (Outlook, Gmail, Thunderbird).
Also copies the email to clipboard for manual paste.
"""

from __future__ import annotations
import json
import re
import subprocess
import urllib.parse
import platform
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional

TOOL = {
    "name": "email_dictation",
    "description": (
        "Draft, edit, format, and send emails entirely by voice. "
        "Can compose a professional email from a casual description, "
        "improve tone (formal/friendly), add subject lines, "
        "and open the system mail client to send. "
        "Trigger on: 'write an email', 'draft email', 'send email to', 'compose email', "
        "'email [name] about', 'make it more formal', 'add a closing'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["draft", "improve", "send", "show", "save"],
                "description": "draft=create new, improve=polish existing, send=open mail client, show=display draft, save=save to file"
            },
            "to": {"type": "string", "description": "Recipient name or email address"},
            "subject": {"type": "string", "description": "Email subject line"},
            "body_hint": {"type": "string", "description": "What the email should say (casual description)"},
            "tone": {"type": "string", "enum": ["professional", "friendly", "formal", "concise"], "description": "Desired email tone"},
            "draft_text": {"type": "string", "description": "Existing draft to improve or send"},
        },
        "required": ["action"],
    },
}

# ── State: current session draft ──────────────────────────────────────────────
from core.app_paths import get_config_dir

_DRAFT_FILE = get_config_dir() / "email_draft.json"


def _save_draft(data: dict) -> None:
    _DRAFT_FILE.parent.mkdir(parents=True, exist_ok=True)
    _DRAFT_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_draft() -> Optional[dict]:
    try:
        if _DRAFT_FILE.exists():
            return json.loads(_DRAFT_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def _open_mail_client(to: str, subject: str, body: str) -> str:
    """Opens system default email client via mailto: URI."""
    mailto = (
        f"mailto:{urllib.parse.quote(to)}"
        f"?subject={urllib.parse.quote(subject)}"
        f"&body={urllib.parse.quote(body)}"
    )
    try:
        if platform.system() == "Windows":
            subprocess.Popen(["cmd", "/c", "start", "", mailto], shell=False)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", mailto])
        else:
            subprocess.Popen(["xdg-open", mailto])
        return "✅ Email client opened with your draft pre-filled. Review and click Send."
    except Exception as exc:
        return f"⚠️ Could not open mail client: {exc}. Draft copied to clipboard."


def _copy_to_clipboard(text: str) -> None:
    try:
        import pyperclip
        pyperclip.copy(text)
    except Exception:
        try:
            if platform.system() == "Windows":
                subprocess.run(["clip"], input=text.encode("utf-8"), check=True)
        except Exception:
            pass


def run(args: Dict[str, Any]) -> str:
    action     = args.get("action", "draft")
    to         = args.get("to", "").strip()
    subject    = args.get("subject", "").strip()
    body_hint  = args.get("body_hint", "").strip()
    tone       = args.get("tone", "professional")
    draft_text = args.get("draft_text", "").strip()

    if action == "show":
        draft = _load_draft()
        if not draft:
            return "No email draft found. Say 'draft an email to...' to start one."
        return (
            f"📧 **Current Draft**\n"
            f"**To:** {draft.get('to', '—')}\n"
            f"**Subject:** {draft.get('subject', '—')}\n\n"
            f"{draft.get('body', '')}"
        )

    if action == "draft":
        if not body_hint:
            return "Please tell me what the email should be about. For example: 'Draft an email to Rahul about pushing the deadline to Friday.'"

        subj = subject or f"Re: {body_hint[:40].strip()}"
        tone_instruction = {
            "professional": "professional, clear, and respectful",
            "friendly":     "warm, friendly, and conversational",
            "formal":       "very formal and structured",
            "concise":      "concise — maximum 3 short sentences",
        }.get(tone, "professional")

        # Build the email body (Charlie/Gemini will expand from the hint)
        # We return a structured prompt so the LLM writes the actual body
        draft_body = (
            f"[INSTRUCTION FOR CHARLIE: Write a {tone_instruction} email body based on this brief: "
            f"'{body_hint}'. Include a greeting, clear message, and a polite closing. "
            f"Return ONLY the email body text, no extra commentary.]"
        )

        draft = {"to": to or "recipient@email.com", "subject": subj, "body": draft_body, "tone": tone, "created": datetime.now().isoformat()}
        _save_draft(draft)

        return (
            f"📧 Draft created!\n"
            f"**To:** {draft['to']}\n"
            f"**Subject:** {subj}\n"
            f"**Tone:** {tone}\n\n"
            f"Charlie will now compose the email body. Say **'send it'** when ready, "
            f"or **'make it more formal/friendly/concise'** to adjust."
        )

    if action == "improve":
        base = draft_text or ((_load_draft() or {}).get("body", ""))
        if not base:
            return "No draft to improve. Please draft an email first."
        tone_map = {
            "professional": "Rewrite this email to sound more professional and polished.",
            "friendly":     "Rewrite this email to sound warmer and more friendly.",
            "formal":       "Rewrite this email to be more formal and structured.",
            "concise":      "Shorten this email to 2-3 sentences, keeping the core message.",
        }
        instruction = tone_map.get(tone, "Polish this email for professional use.")
        return (
            f"[INSTRUCTION FOR CHARLIE: {instruction} Original:\n{base}\n"
            f"Return ONLY the improved email body.]"
        )

    if action == "send":
        draft = _load_draft()
        if not draft and not draft_text:
            return "No draft found. Say 'draft an email to...' first."
        use = draft or {}
        send_to   = to or use.get("to", "")
        send_subj = subject or use.get("subject", "No Subject")
        send_body = draft_text or use.get("body", "")

        if not send_to or "@" not in send_to:
            return f"I need a valid email address to send to. You said '{send_to}' — please provide the full email."

        _copy_to_clipboard(f"To: {send_to}\nSubject: {send_subj}\n\n{send_body}")
        result = _open_mail_client(send_to, send_subj, send_body)
        # Clear draft after send
        if _DRAFT_FILE.exists():
            _DRAFT_FILE.unlink()
        return result

    if action == "save":
        draft = _load_draft()
        if not draft:
            return "No draft to save."
        save_path = Path.home() / "Documents" / f"email_draft_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        save_path.write_text(
            f"To: {draft.get('to','')}\nSubject: {draft.get('subject','')}\n\n{draft.get('body','')}",
            encoding="utf-8"
        )
        return f"✅ Draft saved to: {save_path}"

    return "Unknown email action. Say 'draft', 'improve', 'send', or 'show'."


def execute(**kwargs) -> Any:
    return run(kwargs)

