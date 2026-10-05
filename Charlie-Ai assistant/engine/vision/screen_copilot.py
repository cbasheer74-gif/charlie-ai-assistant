"""engine/vision/screen_copilot.py — Real-Time Screen Vision Co-pilot for CHARLIE.

Features:
- Active window & application foreground tracking (Win32 / ctypes).
- Frame differential hashing: low-CPU passive screen state tracking.
- Visual OCR & error anomaly detection (Tracebacks, compiler errors, dialog boxes).
- Live context generation for system prompt injection.
- Passive background monitor thread with callback hooks.
"""

from __future__ import annotations

import ctypes
import hashlib
import io
import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("charlie.screen_copilot")


@dataclass
class ScreenInsight:
    active_window: str = ""
    process_name: str = ""
    detected_errors: List[str] = field(default_factory=list)
    has_code_error: bool = False
    screen_changed: bool = False
    ocr_text_snippet: str = ""
    timestamp: float = 0.0


class ScreenVisionCopilot:
    """Intelligent live screen monitor that provides ambient vision context to CHARLIE."""

    # Common code error / diagnostic patterns
    ERROR_PATTERNS = [
        re.compile(r"(Traceback\s*\(most\s*recent\s*call\s*last\):[\s\S]*?(?:Error|Exception):.*)", re.MULTILINE),
        re.compile(r"(SyntaxError|TypeError|ValueError|IndexError|KeyError|AttributeError|ImportError|ZeroDivisionError):.*"),
        re.compile(r"(error\s+TS\d+:.*)", re.I),
        re.compile(r"(FAILED\s+tests/.*)", re.I),
        re.compile(r"(Build\s+failed|Compilation\s+error|Uncaught\s+exception):?.*", re.I),
        re.compile(r"(\b404\s+Not\s+Found\b|\b500\s+Internal\s+Server\s+Error\b)", re.I),
    ]

    def __init__(self, check_interval: float = 2.5):
        self.check_interval = check_interval
        self._last_frame_hash: str = ""
        self._last_insight = ScreenInsight()
        self._is_running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._listeners: List[Callable[[ScreenInsight], None]] = []

    def get_active_window_title(self) -> str:
        """Retrieves title of current foreground window via Win32 ctypes."""
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return "Unknown"
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return "Desktop"
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            return buff.value
        except Exception:
            return "Windows Desktop"

    def capture_screen_pil(self, region: Optional[Tuple[int, int, int, int]] = None) -> Any:
        """Captures screen using engine.vision_ocr or Pillow ImageGrab."""
        try:
            from engine.vision_ocr import capture_screen_image
            return capture_screen_image(region=region)
        except Exception:
            try:
                from PIL import ImageGrab
                return ImageGrab.grab()
            except Exception:
                return None

    def compute_frame_hash(self, pil_image: Any) -> str:
        """Generates thumbnail perceptual hash for fast change detection."""
        if pil_image is None:
            return ""
        try:
            thumb = pil_image.resize((32, 32)).convert("L")
            return hashlib.md5(thumb.tobytes()).hexdigest()
        except Exception:
            return ""

    def inspect_screen_now(self, force_ocr: bool = False) -> ScreenInsight:
        """Performs immediate full screen inspection."""
        now = time.time()
        win_title = self.get_active_window_title()

        img = self.capture_screen_pil()
        curr_hash = self.compute_frame_hash(img)
        changed = (curr_hash != self._last_frame_hash)
        self._last_frame_hash = curr_hash

        detected_errors: List[str] = []
        ocr_text = ""

        # Extract text if frame changed or forced
        if img is not None and (changed or force_ocr):
            try:
                import pytesseract
                ocr_text = pytesseract.image_to_string(img)
            except Exception:
                try:
                    from engine.vision_ocr import extract_screen_text
                    res = extract_screen_text()
                    ocr_text = res.get("text", "")
                except Exception:
                    pass
                # Fallback: check window title for error hints
                if any(err in win_title.lower() for err in ["error", "fail", "crash", "bug"]):
                    detected_errors.append(f"Window title indicates issue: {win_title}")

        if ocr_text:
            for pat in self.ERROR_PATTERNS:
                for match in pat.finditer(ocr_text):
                    detected_errors.append(match.group(0).strip())

        insight = ScreenInsight(
            active_window=win_title,
            detected_errors=detected_errors[:5],
            has_code_error=len(detected_errors) > 0,
            screen_changed=changed,
            ocr_text_snippet=ocr_text[:300].strip(),
            timestamp=now,
        )

        with self._lock:
            self._last_insight = insight

        return insight

    def get_live_context_for_prompt(self) -> str:
        """Formats current screen state for immediate LLM prompt injection."""
        with self._lock:
            insight = self._last_insight

        if not insight.active_window and insight.timestamp == 0.0:
            insight = self.inspect_screen_now(force_ocr=False)

        lines = [f"[Current Screen Context: Active Window '{insight.active_window}']"]
        if insight.has_code_error:
            lines.append("Detected Visible Screen Errors:")
            for err in insight.detected_errors:
                lines.append(f"  - {err}")
        return "\n".join(lines)

    def add_listener(self, cb: Callable[[ScreenInsight], None]) -> None:
        self._listeners.append(cb)

    def start_passive_copilot(self) -> bool:
        """Starts background passive screen analysis loop."""
        if self._is_running:
            return True
        self._is_running = True

        def _loop():
            while self._is_running:
                try:
                    insight = self.inspect_screen_now(force_ocr=False)
                    for listener in self._listeners:
                        try:
                            listener(insight)
                        except Exception:
                            pass
                except Exception as e:
                    logger.debug("Screen copilot loop tick failed: %s", e)
                time.sleep(self.check_interval)

        self._worker_thread = threading.Thread(target=_loop, daemon=True, name="ScreenCopilotThread")
        self._worker_thread.start()
        return True

    def stop_passive_copilot(self) -> None:
        self._is_running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)


# Singleton accessor
_copilot_instance: Optional[ScreenVisionCopilot] = None
_copilot_lock = threading.Lock()


def get_screen_copilot() -> ScreenVisionCopilot:
    global _copilot_instance
    with _copilot_lock:
        if _copilot_instance is None:
            _copilot_instance = ScreenVisionCopilot()
        return _copilot_instance
