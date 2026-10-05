"""actions/screen_ocr.py — Auto-discovered action for screen OCR and visual inspection.

Enables CHARLIE voice and text agents to:
1. Extract and read all text currently visible on screen or in a specific region.
2. Diagnose error dialogs, traceback messages, or warning banners on screen.
3. Describe what is currently on screen.
4. Capture and save high-resolution screenshots.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from engine import vision_ocr as vision


def _parse_region(raw: Any) -> Optional[Tuple[int, int, int, int]]:
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        try:
            return (int(raw[0]), int(raw[1]), int(raw[2]), int(raw[3]))
        except (ValueError, TypeError):
            return None
    return None


def screen_ocr(parameters: Dict[str, Any], **kwargs) -> str:
    params = parameters or {}
    action = str(params.get("action") or "read").strip().lower()
    region = _parse_region(params.get("region"))

    if action in ("read", "ocr", "extract"):
        instruction = params.get("instruction")
        res = vision.extract_screen_text(region=region, instruction=instruction)
        loc = f" region {region}" if region else " full screen"
        return f"[Screen OCR ({res['width']}x{res['height']}{loc})]:\n{res['text']}"

    if action in ("diagnose", "error", "inspect_error"):
        res = vision.diagnose_screen_error()
        return f"[Screen Error Diagnosis]:\n{res['text']}"

    if action in ("describe", "overview"):
        res = vision.describe_screen()
        return f"[Screen Description]:\n{res['text']}"

    if action in ("capture", "screenshot", "save"):
        saved_path = vision.save_screenshot(region=region)
        return f"[Screenshot Captured]: Saved to {saved_path}"

    return "Unknown action. Choose from: ocr, diagnose, describe, or capture."


TOOL = {
    "name": "screen_ocr",
    "description": (
        "Read and extract text from the computer screen using Vision OCR, "
        "diagnose visible error messages/dialogs on screen, describe active window contents, "
        "or capture screenshots."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "ocr (read text) | diagnose (find and fix on-screen errors) | describe (overview) | capture (save image)",
            },
            "region": {
                "type": "ARRAY",
                "items": {"type": "INTEGER"},
                "description": "Optional bounding box coordinates [x, y, width, height]",
            },
            "instruction": {
                "type": "STRING",
                "description": "Optional specific focus or prompt for text extraction",
            },
        },
        "required": ["action"],
    },
    "handler": screen_ocr,
}
