# actions/screen_explainer.py
"""
Instant Screen Snip & Explain for Charlie.

Voice commands:
  "Explain my screen"
  "What is on my screen right now?"
  "Read the text on my screen"
  "Explain the error showing on my screen"
  "Take a screenshot and explain it"
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

TOOL = {
    "name": "screen_explainer",
    "description": (
        "Captures the active screen or window, extracts all visible text via OCR, "
        "and produces an intelligent plain-English explanation, troubleshooting diagnosis, "
        "UI layout inspection, code analysis, or concise summary of the visible application. "
        "Trigger on: 'explain my screen', 'what is on my screen', 'read screen', "
        "'diagnose screen error', 'explain this window', 'screenshot and explain', "
        "'inspect UI', 'analyze code on screen', 'explain chart'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["explain", "read", "error", "summary", "code_diff", "ui_inspect", "chart_explain"],
                "description": "explain=general explanation, read=verbatim text, error=code/dialog error fix, summary=bullet points, code_diff=code triage, ui_inspect=buttons and inputs, chart_explain=graphs and metrics",
            },
        },
        "required": [],
    },
}

from core.app_paths import get_config_dir

_CACHE_FILE = get_config_dir() / "last_screen_explanation.json"


def _get_active_window_title() -> str:
    """Retrieve active foreground window title via native Windows API."""
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
            return buff.value.strip()
    except Exception:
        pass
    return ""


def execute(mode: str = "explain", **kwargs: Any) -> str:
    """Execute screen capture, OCR, and intelligent explanation."""
    extracted_text = ""
    width = 1920
    height = 1080

    # 1. Attempt extraction via vision OCR engine
    try:
        from engine import vision_ocr as vision
        ocr_res = vision.extract_screen_text()
        extracted_text = ocr_res.get("text", "")
        width = ocr_res.get("width", 1920)
        height = ocr_res.get("height", 1080)
    except Exception:
        # Fallback using PIL ImageGrab
        try:
            from PIL import ImageGrab
            screenshot = ImageGrab.grab()
            width, height = screenshot.size
            extracted_text = "Visual screen captured. Active desktop displayed."
        except Exception as e:
            return f"Unable to capture screen: {e}. Please ensure display permissions are active."

    if not extracted_text or len(extracted_text.strip()) < 10:
        return (
            "Screen captured, but no distinct text or dialog was recognized. "
            "If an application or browser is minimized, please bring it to focus."
        )

    # Clean text excerpt
    lines = [l.strip() for l in extracted_text.splitlines() if l.strip()]
    preview_snippet = "\n".join(lines[:12])

    window_title = _get_active_window_title()
    window_ctx = f" (Active Window: '{window_title}')" if window_title else ""

    # Check for error patterns
    has_error = any(kw in extracted_text.lower() for kw in ("error", "traceback", "exception", "failed", "warning", "fatal"))

    if mode == "code_diff":
        instruction = (
            "Analyze the code or diff visible on screen. Explain file names, modified lines, "
            "potential syntax issues or logical bugs, and recommend a clean fix."
        )
        tag = "💻 Code & Diff Analysis"
    elif mode == "ui_inspect":
        instruction = (
            "Inspect the visible user interface elements. Identify active buttons, input fields, "
            "navigation menus, dialog buttons, and keyboard focus states."
        )
        tag = "🎛️ UI & Controls Inspection"
    elif mode == "chart_explain":
        instruction = (
            "Explain the chart, dashboard, or data table visible on screen. Highlight key metrics, "
            "trends, anomalies, and summary conclusions."
        )
        tag = "📊 Visual Data & Chart Explanation"
    elif mode == "error" or (mode == "explain" and has_error):
        instruction = (
            "Diagnose the error or warning visible on screen. "
            "Explain what caused it and give 2 clear steps to resolve it."
        )
        tag = "⚠️ Screen Error Diagnosis"
    elif mode == "read":
        instruction = "Read the visible content clearly and accurately."
        tag = "📖 Screen Text Reader"
    elif mode == "summary":
        instruction = "Summarize the visible window into 3 high-impact bullet points."
        tag = "📋 Screen Summary"
    else:
        instruction = (
            "Explain what application, document, or content is active on screen in clear, natural language."
        )
        tag = "🖥️ Screen Analysis"

    report = (
        f"{tag}{window_ctx} ({width}x{height}):\n"
        f"**Content Preview:**\n{preview_snippet}\n\n"
        f"Charlie analyzed the visual screen context."
    )

    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(
            json.dumps({"mode": mode, "window": window_title, "timestamp": datetime.now().isoformat(), "report": report}, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass

    return (
        f"[INSTRUCTION FOR CHARLIE: {instruction}\n"
        f"Active Foreground Window: {window_title or 'Unknown'}\n"
        f"Screen OCR Text:\n\"\"\"{extracted_text[:3000]}\"\"\"\n"
        f"Provide a natural, conversational voice answer.]\n\n"
        f"{report}"
    )
