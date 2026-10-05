"""
CHARLIE v1.3.0 — Pre-launch Health Check
Run this BEFORE starting the app to diagnose import errors, missing packages,
bad API keys, and audio device issues.

Usage:
    python check_health.py
"""
import sys
import os
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
PASS = "OK "
FAIL = "ERR"
WARN = "WRN"
INFO = "   "

results = []

def check(label, ok, detail="", fix=""):
    sym = PASS if ok else FAIL
    msg = f"  [{sym}] {label}" + (f": {detail}" if detail else "")
    if fix and not ok:
        msg += f"\n        --> FIX: {fix}"
    results.append((ok, msg))

def section(title):
    results.append((True, f"\n{'='*55}\n  {title}\n{'='*55}"))

# ──────────────────────────────────────────────────────────────
section("Python version")
v = sys.version_info
check("Python >= 3.10", v >= (3, 10), f"{v.major}.{v.minor}.{v.micro}",
      "Install Python 3.11 from https://python.org")

# ──────────────────────────────────────────────────────────────
section("Core packages (required)")

CORE_PKGS = [
    ("PyQt6",             "PyQt6"),
    ("sounddevice",       "sounddevice"),
    ("numpy",             "numpy"),
    ("google.genai",      "google-genai"),
    ("requests",          "requests"),
    ("bs4",               "beautifulsoup4"),
    ("playwright",        "playwright"),
    ("pyautogui",         "pyautogui"),
    ("pyperclip",         "pyperclip"),
    ("PIL",               "pillow"),
    ("cv2",               "opencv-python"),
    ("mss",               "mss"),
    ("psutil",            "psutil"),
    ("fastapi",           "fastapi"),
    ("uvicorn",           "uvicorn[standard]"),
    ("cryptography",      "cryptography"),
    ("qrcode",            "qrcode[pil]"),
    ("googleapiclient",   "google-api-python-client"),
    ("tinytuya",          "tinytuya"),
    ("ddgs",              "ddgs"),
    ("pdfplumber",        "pdfplumber"),
    ("docx",              "python-docx"),
    ("pptx",              "python-pptx"),
    ("openpyxl",          "openpyxl"),
]

for import_name, pkg_name in CORE_PKGS:
    try:
        __import__(import_name)
        check(pkg_name, True)
    except ImportError as e:
        check(pkg_name, False, str(e), f"pip install {pkg_name}")

if sys.platform == "win32":
    WIN_PKGS = [
        ("comtypes",  "comtypes",   True),   # True = required
        ("pycaw",     "pycaw",      True),
        ("win10toast","win10toast", False),  # False = optional (pop-up notifications only)
        ("pywinauto", "pywinauto",  True),
        ("win32api",  "pywin32",    True),
        ("wmi",       "wmi",        True),
    ]
    for import_name, pkg_name, required in WIN_PKGS:
        try:
            __import__(import_name)
            check(f"{pkg_name} (Windows)", True)
        except ImportError:
            if required:
                check(f"{pkg_name} (Windows)", False, "missing",
                      f"pip install {pkg_name}")
            else:
                results.append((True, f"  [{WARN}] {pkg_name} (Windows) not importable — desktop notifications disabled\n"
                                      f"        Fix: python -m pip install setuptools --upgrade"))
        except Exception as e:
            if required:
                check(f"{pkg_name} (Windows)", False, str(e),
                      f"python -m pip install {pkg_name} --upgrade")
            else:
                results.append((True, f"  [{WARN}] {pkg_name} (Windows) import error (optional): {e}"))


# ──────────────────────────────────────────────────────────────
section("Optional packages (feature-gated)")

OPT_PKGS = [
    ("faster_whisper", "faster-whisper", "offline STT / local Whisper"),
    ("vosk",           "vosk",           "offline STT / Vosk fallback"),
    ("openwakeword",   "openwakeword",   "Hey Charlie wake word"),
    ("pandas",         "pandas",         "file_processor spreadsheets"),
    ("pydub",          "pydub",          "file_processor audio"),
    ("mediapipe",      "mediapipe",      "pushup_counter"),
    ("pynvml",         "pynvml",         "GPU metrics in HUD"),
    ("send2trash",     "send2trash",     "safe file deletion"),
    ("youtube_transcript_api", "youtube-transcript-api", "YouTube captions"),
]

for import_name, pkg_name, feature in OPT_PKGS:
    try:
        __import__(import_name)
        results.append((True, f"  [{PASS}] {pkg_name} ({feature})"))
    except ImportError:
        results.append((True, f"  [{WARN}] {pkg_name} not installed — {feature} disabled\n"
                              f"        Install: pip install {pkg_name}"))

# ──────────────────────────────────────────────────────────────
section("Config files")

CFG_DIR = BASE / "config"
API_KEY_FILE = CFG_DIR / "api_keys.json"

check("config/ directory exists", CFG_DIR.is_dir(), fix="Create it: mkdir config")

if API_KEY_FILE.exists():
    try:
        data = json.loads(API_KEY_FILE.read_text(encoding="utf-8"))
        key = data.get("gemini_api_key", "")
        ok = bool(key and len(key) > 10)
        check("api_keys.json -- gemini_api_key present", ok,
              f"key length {len(key)}" if ok else "missing or empty",
              "Open the app and enter your Gemini API key in the setup screen")
        asst = data.get("assistant_name", "Charlie")
        results.append((True, f"  [{INFO}] assistant_name = '{asst}'"))
    except json.JSONDecodeError as e:
        check("api_keys.json -- valid JSON", False, str(e),
              "Fix JSON syntax in config/api_keys.json")
else:
    check("api_keys.json exists", False,
          "File not found",
          "Launch the app -- it will prompt you to enter your API key")

PROMPT_FILE = BASE / "core" / "prompt.txt"
check("core/prompt.txt exists", PROMPT_FILE.exists(),
      fix="Restore from backup: copy core/prompt.txt.bak core/prompt.txt")

# ──────────────────────────────────────────────────────────────
section("Audio devices")

try:
    import sounddevice as sd
    devs = sd.query_devices()
    inputs  = [d for d in devs if d["max_input_channels"] > 0]
    outputs = [d for d in devs if d["max_output_channels"] > 0]
    check("Microphone(s) available", bool(inputs), f"{len(inputs)} found",
          "Connect a microphone and re-run")
    check("Speaker(s) available",    bool(outputs), f"{len(outputs)} found",
          "Connect speakers or headphones and re-run")
    default_in  = sd.query_devices(kind="input")
    default_out = sd.query_devices(kind="output")
    results.append((True, f"  [{INFO}] Default mic:     {default_in['name']}"))
    results.append((True, f"  [{INFO}] Default speaker: {default_out['name']}"))
except Exception as e:
    check("Audio device query", False, str(e),
          "pip install sounddevice")

# ──────────────────────────────────────────────────────────────
section("Network")

try:
    import socket
    socket.setdefaulttimeout(5)
    socket.create_connection(("generativelanguage.googleapis.com", 443)).close()
    check("Gemini API reachable", True)
except Exception as e:
    check("Gemini API reachable", False, str(e),
          "Check internet. VPN may be needed in some regions.")

try:
    import socket
    socket.create_connection(("8.8.8.8", 53)).close()
    check("Internet connectivity", True)
except Exception as e:
    check("Internet connectivity", False, str(e), "Check network connection")

# ──────────────────────────────────────────────────────────────
section("Stale lock files")

try:
    import psutil
    _psutil_ok = True
except ImportError:
    _psutil_ok = False

LOCK = BASE / "config" / "charlie.lock"
if LOCK.exists():
    try:
        pid = int(LOCK.read_text().strip())
        alive = psutil.pid_exists(pid) if _psutil_ok else True
        if alive:
            check("Lock file", True, f"Charlie already running (PID {pid})")
        else:
            LOCK.unlink()
            check("Stale lock file cleaned", True, f"PID {pid} dead -- removed")
    except Exception:
        try:
            LOCK.unlink()
            results.append((True, f"  [{WARN}] Stale lock removed: {LOCK}"))
        except Exception as e:
            check("Remove stale lock", False, str(e), f"Delete manually: {LOCK}")
else:
    check("No stale lock file", True)

# ──────────────────────────────────────────────────────────────
section("Key source files")

KEY_FILES = [
    BASE / "main.py",
    BASE / "ui.py",
    BASE / "core" / "stt.py",
    BASE / "core" / "echo.py",
    BASE / "core" / "tts.py",
    BASE / "core" / "wake_word.py",
    BASE / "engine" / "deployment" / "runtime.py",
]
for f in KEY_FILES:
    check(str(f.relative_to(BASE)), f.exists(),
          fix=f"Restore from git: {f.name}")

# ──────────────────────────────────────────────────────────────
section("Summary")

failed = sum(1 for ok, _ in results if ok is False)

print()
for _, line in results:
    print(line)

print(f"\n{'='*55}")
if failed == 0:
    print("  [OK ] All checks passed -- Charlie is ready to run!")
else:
    print(f"  [ERR] {failed} issue(s) found. Fix them before launching.")
print(f"{'='*55}\n")
sys.exit(0 if failed == 0 else 1)
