# actions/page_summarizer.py
"""
Web Page & Document Summarizer for Charlie.

Voice commands:
  "Summarize this page"
  "Summarize this link: https://..."
  "Give me key takeaways from what I copied"
  "What are the main action items from this document?"
  "Quick 3-bullet summary of this website"
"""

from __future__ import annotations

import json
import platform
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

TOOL = {
    "name": "page_summarizer",
    "description": (
        "Summarizes web pages, online articles, documentation, or pasted text. "
        "Extracts 3-5 key takeaways, executive summary, action items, and reading time. "
        "Can fetch live URLs or read articles directly from system clipboard. "
        "Trigger on: 'summarize this page', 'summarize article', 'what is this link about', "
        "'give me key points', 'summarize document', 'read this page for me'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["summarize", "key_takeaways", "action_items", "from_clipboard", "from_url"],
                "description": "summarize=full structured summary, key_takeaways=bullet highlights, action_items=todo extraction, from_clipboard=summarize copied text, from_url=fetch and summarize link",
            },
            "url": {
                "type": "string",
                "description": "Website or article URL to fetch and summarize",
            },
            "text": {
                "type": "string",
                "description": "Raw article or document text to summarize",
            },
            "max_bullets": {
                "type": "integer",
                "description": "Number of key takeaways (default 3, max 7)",
            },
            "copy_to_clipboard": {
                "type": "boolean",
                "description": "Copy summary to clipboard (default true)",
            },
        },
        "required": ["action"],
    },
}

from core.app_paths import get_config_dir

_CACHE_FILE = get_config_dir() / "last_page_summary.json"


def _get_clipboard_text() -> str:
    try:
        import pyperclip  # type: ignore
        text = pyperclip.paste()
        if text:
            return text.strip()
    except Exception:
        pass

    if platform.system() == "Windows":
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            return res.stdout.strip()
        except Exception:
            pass
    return ""


def _set_clipboard_text(text: str) -> None:
    try:
        import pyperclip  # type: ignore
        pyperclip.copy(text)
        return
    except Exception:
        pass

    if platform.system() == "Windows":
        try:
            subprocess.run(["clip"], input=text.encode("utf-16"), check=True)
        except Exception:
            pass


def _extract_url_from_text(text: str) -> Optional[str]:
    match = re.search(r"https?://[^\s\"'<>]+", text)
    return match.group(0) if match else None


def _fetch_page_content(url: str, max_chars: int = 15000) -> Dict[str, str]:
    """Fetch and parse clean text from a web URL."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=8) as response:
        raw_html = response.read().decode("utf-8", errors="replace")

    title = ""
    clean_text = ""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(raw_html, "html.parser")
        for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "svg"]):
            tag.decompose()

        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all(["p", "h1", "h2", "h3", "li"])]
        clean_text = "\n\n".join(p for p in paragraphs if len(p) > 20)
    except Exception:
        clean_text = re.sub(r"<[^>]+>", " ", raw_html)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()

    if not clean_text:
        clean_text = raw_html[:max_chars]
    else:
        clean_text = clean_text[:max_chars]

    return {"title": title or url, "text": clean_text}


def _heuristic_summary(text: str, max_bullets: int = 3) -> Dict[str, Any]:
    """Offline heuristic extractor for quick takeaways and reading time."""
    words = text.split()
    word_count = len(words)
    reading_time_min = max(1, round(word_count / 200))

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 35]
    # Pick top representative sentences
    key_points: List[str] = []
    seen = set()
    for s in sentences:
        clean_s = s.strip()
        if clean_s.lower() not in seen and len(clean_s) < 220:
            seen.add(clean_s.lower())
            key_points.append(clean_s)
            if len(key_points) >= max_bullets:
                break

    return {
        "word_count": word_count,
        "reading_time_min": reading_time_min,
        "bullets": key_points,
    }


def execute(
    action: str = "summarize",
    url: Optional[str] = None,
    text: Optional[str] = None,
    max_bullets: int = 3,
    copy_to_clipboard: bool = True,
    **kwargs: Any,
) -> str:
    """Execute page summarizer action."""
    target_url = url or ""
    source_text = (text or "").strip()

    # If action is from clipboard or nothing passed, check clipboard
    if not source_text and not target_url:
        clip = _get_clipboard_text()
        found_url = _extract_url_from_text(clip)
        if found_url:
            target_url = found_url
        elif clip:
            source_text = clip

    title = ""
    if target_url:
        try:
            fetched = _fetch_page_content(target_url)
            title = fetched.get("title", target_url)
            source_text = fetched.get("text", "")
        except Exception as e:
            return f"Could not fetch URL '{target_url}': {e}. Try copying the text into your clipboard and say 'summarize this'."

    if not source_text:
        return (
            "No content found to summarize. "
            "Please provide a URL or copy the article/document text to your clipboard first."
        )

    # Heuristic analysis
    analysis = _heuristic_summary(source_text, max_bullets=max_bullets)
    word_count = analysis["word_count"]
    read_time = analysis["reading_time_min"]
    bullets = analysis["bullets"]

    bullet_lines = "\n".join(f"• {b}" for b in bullets) if bullets else "• Key content summarized above."

    summary_preview = (
        f"📄 **{title or 'Document Summary'}**\n"
        f"⏱️ Length: ~{word_count} words ({read_time} min read)\n\n"
        f"**Key Takeaways:**\n"
        f"{bullet_lines}"
    )

    if copy_to_clipboard:
        _set_clipboard_text(summary_preview)

    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(
            json.dumps({"url": target_url, "title": title, "summary": summary_preview}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass

    prompt_instruction = (
        f"Summarize this document in {max_bullets} sharp, high-impact bullet points and a 2-sentence executive summary. "
        f"Include actionable takeaways."
    )

    return (
        f"[INSTRUCTION FOR CHARLIE: {prompt_instruction}\n"
        f"Source: {title or target_url or 'User Text'}\n"
        f"Content excerpt:\n{source_text[:3500]}\n"
        f"Present a clean, professional summary with bullet points.]\n\n"
        f"{summary_preview}"
    )
