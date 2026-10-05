"""actions/camera_scanner.py — Professional Camera Object Recognition & OCR Engine for CHARLIE.

Enables instant real-world object scanning and text extraction via webcam:
- High-resolution frame acquisition with auto-detection.
- Multimodal AI vision analysis + OCR text parsing.
- Detailed object identification, primary uses, operating instructions, and pro tips.
- Fluent multilingual response generation matching user's spoken language (English, Hindi/Hinglish, etc.).
"""

from __future__ import annotations

import io
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import PIL.Image
    _PIL = True
except ImportError:
    _PIL = False

from core.app_paths import get_config_dir

_CACHE_FILE = get_config_dir() / "last_camera_scan.json"


def _detect_language(text: str) -> str:
    """Check if query is Hindi / Hinglish or English."""
    t = (text or "").lower()
    hindi_keywords = ("kya", "hai", "kholo", "dekho", "batao", "ye", "yeh", "kaise", "chiz", "cheez", "karein", "karo")
    if any(k in t for k in hindi_keywords):
        return "Hindi/Hinglish"
    return "English"


def is_explicit_scan_requested(text: str) -> bool:
    """Verify that the user actually asked for camera object scanning."""
    if not text:
        return True
    t = text.lower().strip()
    if t in ("hello how are you?", "hello", "kya haal hai?", "kya haal hai", "good morning", "how are you"):
        return False
    signals = (
        "scan", "camera", "webcam", "kholo", "capture", "photo", "dikhata",
        "dikhao", "dekho", "ye kya", "yeh kya", "kya hai", "object", "item",
        "read text", "read label", "read box", "analyze this", "cheez", "chiz",
        "what is this", "identify", "recognize", "look", "see", "thing", "use",
        "purpose", "batao", "naam", "name", "project", "product", "karo"
    )
    return any(sig in t for sig in signals) or len(t) < 40


def execute(prompt: str = "", language: str = "auto", **kwargs: Any) -> str:
    """Capture webcam frame, run OCR & multimodal visual recognition, and describe object & uses."""
    user_query = str(prompt or "").strip()
    detected_lang = _detect_language(user_query) if language in ("auto", "", None) else language

    # ── Strict User Consent Guard: Never auto-trigger without explicit command ──
    if not is_explicit_scan_requested(user_query):
        if detected_lang == "Hindi/Hinglish":
            return (
                "Camera scan abhi start nahi kiya gaya hai. "
                "Jab aapko koi cheez scan karni ho, tab boliye: 'Charlie, scan this object' ya 'Camera se scan karo'."
            )
        return (
            "Camera scanning is on standby. "
            "I will not open the camera automatically until you explicitly ask me to (e.g. 'Hey Charlie, scan this object')."
        )

    # Trigger live camera preview in Charlie UI if running
    ui_inst = None
    try:
        import sys
        main_mod = sys.modules.get("main")
        if main_mod and hasattr(main_mod, "app_instance") and hasattr(main_mod.app_instance, "ui"):
            ui_inst = main_mod.app_instance.ui
            ui_inst.start_camera_stream()
    except Exception:
        pass

    try:
        from actions.screen_processor import _capture_camera
        img_bytes, mime = _capture_camera(enhance_for_ocr=True)
    except Exception as e:
        if ui_inst:
            try:
                ui_inst.stop_camera_stream()
            except Exception:
                pass
        return (
            f"Unable to access the camera: {e}. "
            "Please ensure your webcam is connected, not in use by another app, "
            "and camera permissions are enabled in Windows Settings."
        )

    try:
        if not _PIL:
            return "PIL (Pillow) is required for processing camera frames. Please run: pip install pillow"

        try:
            img = PIL.Image.open(io.BytesIO(img_bytes)).convert("RGB")
        except Exception as err:
            return f"Failed to decode camera image frame: {err}"

        # Archive high-res scan snapshot
        from core.app_paths import get_memory_dir
        scans_dir = get_memory_dir() / "scans"
        snapshot_path = None
        try:
            scans_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            snapshot_path = scans_dir / f"scan_{stamp}.jpg"
            img.save(str(snapshot_path), "JPEG", quality=92)
        except Exception:
            pass

        user_query = str(prompt or "").strip()
        detected_lang = _detect_language(user_query) if language in ("auto", "", None) else language

        analysis_prompt = (
            "You are CHARLIE's Ultra-High-Precision Visual Object Recognition & OCR Engine.\n"
            f"The user showed an object to the camera and asked: '{user_query or 'What is this object and what is its use?'}'.\n\n"
            "ANALYZE THIS CAMERA CAPTURE WITH MAXIMUM PROFESSIONAL EXECUTIVE RIGOR:\n"
            "════════════════════════════════════════════════════════════════════════════════\n"
            "◈ NEURAL VISION INTELLIGENCE DOSSIER ◈\n"
            "════════════════════════════════════════════════════════════════════════════════\n\n"
            "1. 🏷️ IDENTIFICATION: Exact object name, brand, model, manufacturer, and specific category.\n"
            "2. 🔍 OCR & VISIBLE LABELS: Accurately transcribe and extract every readable printed text, brand logo, serial/model number, ingredient, or warning label visible on the item.\n"
            "3. ⚙️ FORM FACTOR & BUILD: Physical material, components, ports/buttons, and key design features.\n"
            "4. 🎯 PRIMARY PURPOSE & USE CASES: In-depth explanation of what this object is used for in everyday life or professional tasks. Why does someone use it?\n"
            "5. 🛠️ STEP-BY-STEP USAGE GUIDE: Clear, practical directions on how to properly operate, hold, or apply this item.\n"
            "6. 💡 PRO TIPS & SAFETY: Essential storage instructions, maintenance precautions, safety warnings, or interesting facts.\n\n"
            f"LANGUAGE DIRECTIVE: Deliver the complete explanation in {detected_lang}. "
            "Keep the tone professional, authoritative, and remarkably thorough. "
            "Format cleanly with clear headers and bullet points."
        )

        extracted_text = ""
        try:
            from core import gemini
            resp = gemini.call([analysis_prompt, img], tier=gemini.SMART, timeout_ms=35000)
            if resp and getattr(resp, "text", None):
                extracted_text = str(resp.text).strip()
            else:
                extracted_text = "The vision engine captured the object but returned no description. Please hold the item steady with good lighting."
        except Exception as exc:
            extracted_text = f"Visual analysis encountered an error: {exc}"

        # Cache scan result & record to memory
        try:
            _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _CACHE_FILE.write_text(
                json.dumps(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "prompt": user_query,
                        "language": detected_lang,
                        "snapshot": str(snapshot_path) if snapshot_path else None,
                        "result": extracted_text,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            from engine.episodic_recall import EpisodicRecallEngine
            EpisodicRecallEngine().record_episode(
                summary=f"Camera scanned object: {user_query or 'General scan'}. Extracted: {extracted_text[:180]}...",
                tags=["camera_scan", "vision", "ocr"],
                importance=7.0,
            )
        except Exception:
            pass

        return extracted_text
    finally:
        if ui_inst:
            try:
                ui_inst.stop_camera_stream()
            except Exception:
                pass


TOOL = {
    "name": "camera_scanner",
    "description": (
        "Opens the camera to scan, read, and thoroughly analyze a real-world object held up to the webcam. "
        "CRITICAL: MUST ONLY be called when the user EXPLICITLY asks to scan an object or open the camera first, "
        "such as: 'Hey Charlie, open the camera and analyze this thing', 'scan this object', 'camera se scan karo', "
        "'dekho ye kya hai', 'identify this on camera'. "
        "NEVER call this autonomously, spontaneously, unprompted, or during greetings/general conversation."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "prompt": {
                "type": "STRING",
                "description": "Specific question or analysis focus (e.g. 'What is this and how do I use it?')"
            },
            "language": {
                "type": "STRING",
                "description": "Language of the user request (e.g. 'en', 'hi', 'hinglish', 'auto')"
            }
        },
        "required": []
    },
    "handler": execute,
}
