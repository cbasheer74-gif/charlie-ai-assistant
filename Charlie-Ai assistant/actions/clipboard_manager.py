# actions/clipboard_manager.py
"""
Smart Clipboard Manager — remembers last 50 copied items, recall by voice.

Commands:
  "Show clipboard history"
  "Paste item number 3"
  "Copy this to clipboard: [text]"
  "Clear clipboard history"
  "Save clipboard as note"
  "Search clipboard for 'email'"

Monitors Windows clipboard every 1 second in a background thread.
"""

from __future__ import annotations
import json
import os
import platform
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

TOOL = {
    "name": "clipboard_manager",
    "description": (
        "Smart clipboard with 50-item history. Remembers everything you've copied. "
        "Recall, search, and paste by voice. "
        "Trigger on: 'clipboard history', 'what did I copy', 'paste number', "
        "'copy to clipboard', 'search clipboard', 'clear clipboard history'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["show", "paste", "copy", "search", "clear", "save_note"],
                "description": "show=history, paste=put item back, copy=add text, search=find in history, clear=wipe history, save_note=save item to notes"
            },
            "item_number": {"type": "integer", "description": "1-based index of clipboard history item to recall"},
            "text": {"type": "string", "description": "Text to add to clipboard or search query"},
            "count": {"type": "integer", "description": "How many recent items to show (default 10)"},
        },
        "required": ["action"],
    },
}

from core.app_paths import get_cache_dir, get_config_dir

def _get_history_file() -> Path:
    return get_cache_dir() / "clipboard_history.json"


class _DynamicHistoryFileProxy:
    @property
    def _path(self) -> Path:
        return _get_history_file()
    def __getattr__(self, item):
        return getattr(self._path, item)
    def __fspath__(self):
        return str(self._path)
    def __str__(self):
        return str(self._path)
    def __repr__(self):
        return repr(self._path)
    def __truediv__(self, other):
        return self._path / other
    def __eq__(self, other):
        return self._path == other or str(self._path) == str(other)
    def __hash__(self):
        return hash(self._path)

_HISTORY_FILE = _DynamicHistoryFileProxy()
_LEGACY_HISTORY_FILE = Path(__file__).parent.parent / "config" / "clipboard_history.json"
_MAX_ITEMS    = 50
_HISTORY_LOCK = threading.Lock()


def _load_history() -> List[dict]:
    hf = _get_history_file()
    try:
        if not hf.exists() and _LEGACY_HISTORY_FILE.exists():
            try:
                import shutil
                shutil.copy2(_LEGACY_HISTORY_FILE, hf)
            except Exception:
                pass
        if hf.exists():
            data = json.loads(hf.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def _save_history(items: List[dict]) -> None:
    hf = _get_history_file()
    hf.parent.mkdir(parents=True, exist_ok=True)
    hf.write_text(json.dumps(items[-_MAX_ITEMS:], indent=2, ensure_ascii=False), encoding="utf-8")


def _get_clipboard_text() -> str:
    try:
        import pyperclip
        return pyperclip.paste() or ""
    except Exception:
        if platform.system() == "Windows":
            try:
                result = subprocess.run(
                    ["powershell", "-Command", "Get-Clipboard"],
                    capture_output=True, text=True, timeout=2
                )
                return result.stdout.strip()
            except Exception:
                pass
    return ""


def _set_clipboard_text(text: str) -> None:
    try:
        import pyperclip
        pyperclip.copy(text)
        return
    except Exception:
        pass
    if platform.system() == "Windows":
        try:
            subprocess.run(["clip"], input=text.encode("utf-16"), check=True)
        except Exception:
            pass


def _add_to_history(text: str) -> None:
    """Add text to history if it's new and not empty."""
    if not text or len(text.strip()) < 2:
        return
    with _HISTORY_LOCK:
        items = _load_history()
        # Avoid duplicate consecutive entries
        if items and items[-1].get("text") == text:
            return
        items.append({
            "text":    text,
            "preview": text[:80].replace("\n", " "),
            "length":  len(text),
            "time":    datetime.now().strftime("%H:%M:%S"),
            "date":    datetime.now().strftime("%Y-%m-%d"),
        })
        _save_history(items)


# ── Background clipboard watcher ──────────────────────────────────────────────
_last_seen: str = ""
_watcher_started: bool = False


def _watch_clipboard() -> None:
    global _last_seen
    while _watcher_started:
        try:
            current = _get_clipboard_text()
            if current and current != _last_seen:
                _last_seen = current
                _add_to_history(current)
        except Exception:
            pass
        time.sleep(1.0)


def start_clipboard_watcher() -> None:
    """Start background clipboard monitoring thread (idempotent)."""
    global _watcher_started
    if _watcher_started:
        return
    _watcher_started = True
    t = threading.Thread(target=_watch_clipboard, daemon=True)
    t.start()


def stop_clipboard_watcher() -> None:
    """Stop background clipboard monitoring thread."""
    global _watcher_started
    _watcher_started = False


# Start watcher on module import only outside tests
if not any(mod in sys.modules for mod in ("unittest", "pytest")) and not os.environ.get("CHARLIE_DATA_DIR") and not os.environ.get("CHARLIE_TESTING"):
    start_clipboard_watcher()


def run(args: Dict[str, Any]) -> str:
    action      = args.get("action", "show")
    item_number = args.get("item_number")
    text        = args.get("text", "").strip()
    count       = min(int(args.get("count", 10)), _MAX_ITEMS)

    if action == "show":
        items = _load_history()
        if not items:
            return "Clipboard history is empty. Start copying text and I'll remember everything!"
        recent = items[-count:][::-1]  # most recent first
        lines  = []
        for i, item in enumerate(recent, 1):
            preview = item.get("preview", "")[:60]
            t       = item.get("time", "")
            length  = item.get("length", 0)
            lines.append(f"**{i}.** [{t}] {preview}{'…' if length > 60 else ''} ({length} chars)")
        return f"📋 **Clipboard History** (last {len(recent)}):\n\n" + "\n".join(lines) + \
               f"\n\nSay **'paste item 3'** to restore any item."

    if action == "paste":
        items = _load_history()
        if not items:
            return "No clipboard history found."
        recent = items[::-1]  # most recent first
        if not item_number or item_number < 1 or item_number > len(recent):
            return f"Please specify a number between 1 and {len(recent)}."
        item = recent[item_number - 1]
        _set_clipboard_text(item["text"])
        return (
            f"✅ Item #{item_number} copied to clipboard:\n"
            f"**{item['preview'][:80]}{'…' if item['length'] > 80 else ''}**\n\n"
            f"Press **Ctrl+V** to paste it."
        )

    if action == "copy":
        if not text:
            return "What text should I add to the clipboard?"
        _set_clipboard_text(text)
        _add_to_history(text)
        return f"✅ Copied to clipboard: **{text[:80]}**"

    if action == "search":
        if not text:
            return "What should I search for in your clipboard history?"
        items = _load_history()
        matches = [
            (i + 1, item)
            for i, item in enumerate(reversed(items))
            if text.lower() in item.get("text", "").lower()
        ]
        if not matches:
            return f"No clipboard items found containing **'{text}'**."
        lines = [f"**{i}.** {item['preview'][:80]}…" for i, item in matches[:10]]
        return f"🔍 **Found {len(matches)} matches for '{text}':**\n\n" + "\n".join(lines)

    if action == "clear":
        _HISTORY_FILE.unlink(missing_ok=True)
        return "✅ Clipboard history cleared."

    if action == "save_note":
        items = _load_history()
        if not items:
            return "No clipboard items to save."
        item = items[-1] if not item_number else list(reversed(items))[item_number - 1]
        notes_dir = get_config_dir() / "notes"
        notes_dir.mkdir(parents=True, exist_ok=True)
        note_file = notes_dir / f"clip_note_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        note_file.write_text(item["text"], encoding="utf-8")
        return f"✅ Saved to note: {note_file.name}"

    return "Unknown clipboard action."


def execute(**kwargs) -> Any:
    return run(kwargs)

