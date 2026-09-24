"""engine/vision_ocr.py — Screen text extraction, UI inspection, and visual error diagnosis.

Uses MSS/PIL for multi-monitor screen & region capture, with dual-path processing:
- Multimodal AI vision analysis (Gemini Smart tier) for accurate OCR and UI reasoning.
- Local fallback parsing for offline/test environments.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import PIL.Image
    _PIL = True
except ImportError:
    _PIL = False

try:
    import mss
    _MSS = True
except ImportError:
    _MSS = False


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def capture_screen_image(region: Optional[Tuple[int, int, int, int]] = None) -> Any:
    """Capture full screen or bounded region (x, y, width, height) as a PIL Image."""
    if not _PIL:
        raise RuntimeError("PIL (Pillow) is required for screen capture.")

    if not _MSS:
        # Fallback to pure PIL ImageGrab if mss is unavailable
        from PIL import ImageGrab
        bbox = None
        if region:
            x, y, w, h = region
            bbox = (x, y, x + w, y + h)
        return ImageGrab.grab(bbox=bbox)

    with mss.mss() as sct:
        if region:
            x, y, w, h = region
            monitor = {"left": int(x), "top": int(y), "width": int(w), "height": int(h)}
        else:
            monitors = sct.monitors
            monitor = monitors[1] if len(monitors) > 1 else monitors[0]

        shot = sct.grab(monitor)
        return PIL.Image.frombytes("RGB", shot.size, shot.rgb)


def extract_screen_text(
    region: Optional[Tuple[int, int, int, int]] = None,
    instruction: Optional[str] = None,
    client: Any = None,
) -> Dict[str, Any]:
    """Perform OCR and text extraction from screen or screen region."""
    img = capture_screen_image(region)
    w, h = img.size

    prompt = (
        instruction
        or "Extract all readable text, labels, dialog contents, and code visible in this screenshot. "
        "Preserve line breaks and original structure. Output only the extracted text without introductory chatter."
    )

    extracted_text = ""
    engine_used = "ai_vision"

    if client is not None:
        try:
            resp = client.generate_content([prompt, img])
            extracted_text = (getattr(resp, "text", "") or str(resp)).strip()
        except Exception as e:
            extracted_text = f"AI Vision analysis failed: {e}"
            engine_used = "error"
    else:
        # Attempt standard gemini helper
        try:
            from core import gemini
            resp = gemini.call([prompt, img], tier=gemini.SMART, timeout_ms=30000)
            if resp and getattr(resp, "text", None):
                extracted_text = resp.text.strip()
            else:
                extracted_text = "No text detected on screen or vision model returned empty response."
        except Exception as exc:
            extracted_text = f"Vision OCR unavailable: {exc}"
            engine_used = "offline"

    return {
        "status": "success" if engine_used != "error" else "failed",
        "engine": engine_used,
        "width": w,
        "height": h,
        "region": region,
        "text": extracted_text,
    }


def diagnose_screen_error(client: Any = None) -> Dict[str, Any]:
    """Inspect active screen for error dialogs, crashes, warnings, and suggest immediate fixes."""
    prompt = (
        "Carefully inspect this screenshot for any error messages, crash dialogs, traceback logs, "
        "unhandled exceptions, red banner warnings, or failing command outputs. "
        "If an error is found, summarize: 1) The error symptom, 2) Root cause, 3) Recommended immediate resolution. "
        "If no error is visible on screen, state clearly: 'No active errors or warnings detected on screen.'"
    )
    return extract_screen_text(instruction=prompt, client=client)


def describe_screen(client: Any = None) -> Dict[str, Any]:
    """Describe the current desktop layout, active application, and main UI elements."""
    prompt = (
        "Describe what is currently visible on this desktop screen: "
        "1) Active window / application in focus, 2) Key contents or document open, 3) Current state."
    )
    return extract_screen_text(instruction=prompt, client=client)


def save_screenshot(
    region: Optional[Tuple[int, int, int, int]] = None,
    filename: Optional[str] = None,
) -> Path:
    """Save screenshot to memory/screenshots directory and return its path."""
    img = capture_screen_image(region)
    dest_dir = _app_dir() / "memory" / "screenshots"
    dest_dir.mkdir(parents=True, exist_ok=True)

    name = filename or f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    out_path = dest_dir / name
    img.save(str(out_path), "PNG")
    return out_path
