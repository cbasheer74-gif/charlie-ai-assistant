import platform as _platform
import subprocess as _subprocess

# ── Nuclear: force CREATE_NO_WINDOW on EVERY subprocess call on Windows ───────
# This patches Popen itself, so no per-file flag is needed anywhere.
if _platform.system() == "Windows":
    _OrigPopen = _subprocess.Popen

    class _Popen(_OrigPopen):
        def __init__(self, args, **kw):
            kw["creationflags"] = kw.get("creationflags", 0) | _subprocess.CREATE_NO_WINDOW
            kw.pop("startupinfo", None)   # drop any stale/shared STARTUPINFO
            super().__init__(args, **                       kw)

    _subprocess.Popen = _Popen


# ── Console must survive non-UTF-8 code pages ────────────────────────────────
# Every status line in this file carries an emoji, and on a legacy Windows
# console the active code page is the system one — cp1254 in Turkey, cp1251 in
# Russia, cp932 in Japan. Printing an emoji there raises UnicodeEncodeError, and
# because most of these prints sit inside the receive loop it takes the session
# down on startup. Reconfiguring to UTF-8 with a replacement fallback costs
# nothing and makes the app launch the same way in every locale.
import sys as _sys

for _stream in ("stdout", "stderr"):
    try:
        _s = getattr(_sys, _stream, None)
        if _s is not None and hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass          # pythonw / redirected pipes / anything exotic — never fatal

# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import queue as _queue
import re
import threading
import time
import json
import sys
import traceback
from collections import deque
from datetime import datetime
from pathlib import Path

import sounddevice as sd
import numpy as np
from google import genai
from google.genai import types
from ui import CharlieUI, JarvisUI
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
    save_session_summary, pop_last_session,
    search_memory, set_trim_notifier,
)
from memory.personal_hub import prompt_context as personal_prompt_context
from memory.personal_hub import checkin_due, load_hub, mark_checkin, record_conversation_turn
from memory.profile_manager import active_profile, set_change_notifier as set_profile_change_notifier

# The file-backed tools (open_app, web_search, browser_control, …) are no longer
# imported or declared here — they self-describe via a TOOL dict in their own
# actions/*.py file and are auto-discovered by core.action_loader at startup.
# Only tools that are tied to live-session state stay inline in this file
# (screen_process, close_camera, save_memory, manage_monitor, shutdown_charlie,
# system_status).
from actions.screen_processor  import _capture_camera, _capture_screen
from actions.system_monitor    import SystemMonitor, get_system_status
from actions.proactive         import ProactiveEngine
from actions.background_monitor import (
    add_monitor, remove_monitor, list_monitors, check_all as monitor_check_all,
)
from actions.web_search        import _news as _fetch_news_sync
from memory.config_manager     import (
    get_brief_enabled, get_media_resolution, get_proactive_audio_enabled,
    get_push_to_talk_enabled, get_turn_tuning, get_voice,
    get_wake_word_enabled, save_wake_word_enabled,    get_input_device, get_output_device,
    ensure_sweet_voice_profiles, get_assistant_grammar_instruction, get_assistant_name,
)
from core.plugin_loader        import discover_plugins
from core                      import undo as undo_stack
from core                      import confirm as confirm_gate
from core                      import audio_devices
from core.task_history         import record as record_task_history
from core.action_loader        import discover_actions
from core.echo                 import EchoGuard
from core.chat_dictation      import ChatDictationService
from core.viseme               import VisemeStream
from core.wake_word            import (
    WakeWordDetector, is_ready as wake_is_ready, install_and_download as wake_install,
)
from engine.pro_chat           import ProChatAssistant
from engine.voice.user_greeter_clean import (
    build_session_greeting,
    build_language_confirm,
    SessionLanguageManager,
)
from engine.voice.voice_profile import get_voice_profile_manager
from engine.voice.cultural_greetings import (
    get_cultural_greeting_manager,
    reset_cultural_greeting_manager,
    CulturalGreetingManager,
)
from engine.voice.noise_classifier import (
    get_noise_classifier,
    reset_noise_classifier,
    children_noise_message,
    crowd_noise_message,
    low_voice_message,
    NoiseClassifier,
)

# How long the assistant stays awake with no user speech before it auto-sleeps
# again (wake-word mode only).
WAKE_SLEEP_TIMEOUT = 120.0   # seconds (2 minutes)

def get_base_dir():
    """Writable application directory: beside the EXE when packaged."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

def get_resource_dir():
    """Read-only shipped assets directory.

    PyInstaller stores bundled support files under ``_MEIPASS`` while user
    configuration belongs beside the executable. Keeping those locations
    separate prevents a packaged CHARLIE from losing its prompt or action tools
    simply because its runtime layout differs from the source tree.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent

BASE_DIR        = get_base_dir()
RESOURCE_DIR    = get_resource_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = RESOURCE_DIR / "core" / "prompt.txt"
LIVE_MODEL          = "models/gemini-3.8-live"
LIVE_MODEL_FALLBACKS = [
    "models/gemini-3.8-live",
    "models/gemini-3.1-flash-live-preview",
]
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000 
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024
# Gemini Live uses raw little-endian PCM. Including the capture rate is
# required metadata: without it the server can decode microphone bytes at the
# wrong rate (or reject them), which makes an otherwise-open mic appear silent.
INPUT_AUDIO_MIME    = f"audio/pcm;rate={SEND_SAMPLE_RATE}"

# RMS below which 16-bit PCM is treated as room silence; above _LEVEL_FULL it
# reads as a full-height waveform. Tuned so ordinary speech lands mid-range and
# the bars still move for a quiet talker — language- and device-independent.
_LEVEL_FLOOR = 60.0
_LEVEL_FULL  = 2600.0


def _pcm_level(samples) -> float:
    """Map a block of int16 PCM samples to a 0.0–1.0 loudness level for the HUD
    waveform. Returns 0.0 on empty/invalid input so it can never raise."""
    try:
        x = np.asarray(samples, dtype=np.float32)
        if x.size == 0:
            return 0.0
        rms = float(np.sqrt(np.mean(x * x)))
    except Exception:
        return 0.0
    if rms <= _LEVEL_FLOOR:
        return 0.0
    return min(1.0, (rms - _LEVEL_FLOOR) / (_LEVEL_FULL - _LEVEL_FLOOR))


# ── Viseme extraction ─────────────────────────────────────────────────────────
# The avatar's mouth used to be driven by one RMS value per ~200 ms write batch,
# which is five updates a second averaged over a fifth of a second — it could
# only ever flap. These read the *shape* of each 20 ms slice straight from the
# spectrum of the audio being played, so no transcript, no forced alignment and
# no language assumption: it works the same for Turkish and English.
#
# Two numbers come out. Openness tracks the first formant — F1 climbs as the jaw
# drops, so /a/ reads open and /i/ or /u/ read closed. Width tracks the second —
# F2 is high for spread vowels (/i/, /e/) and low for rounded ones (/u/, /o/).
# Extra time beyond the device's reported output latency before the microphone
# is trusted again: covers room decay and the speaker's own settling.
_TAIL_MARGIN = 0.35

_VIS_WIN = 1024        # ~43 ms analysis window at 24 kHz: enough for formants
_VIS_HOP = 480         # 20 ms between frames, i.e. 50 shapes a second

# Delay from handing the first bytes of a reply to an already-running output
# stream to hearing them: one callback period, plus whatever the DAC adds.
_FIRST_SOUND = CHUNK_SIZE / RECEIVE_SAMPLE_RATE      # ~43 ms
# How far past the device's own buffer the mouth's timeline may drift before it
# is re-anchored. The buffer is the hard limit on how much audio can be queued
# ahead, so anything beyond it plus a margin for clock error is impossible.
_CURSOR_SLACK = 0.15

# Erring early is the safe direction. A viewer tolerates a mouth that moves
# slightly before the sound far better than one that moves after it — the
# broadcast limits are about 45 ms of lag against 125 ms of lead — so where
# this is uncertain it is biased to lead.


def _pcm_visemes(samples, sr: int = 24000):
    """Slice a PCM block into (level, openness, width) frames, one per 20 ms.

    Returns [] on anything unexpected — the mouth falls back to loudness-only
    articulation rather than the caller having to handle an error.
    """
    try:
        x = np.asarray(samples, dtype=np.float32)
        if x.size < _VIS_WIN:
            return []
        win = np.hanning(_VIS_WIN).astype(np.float32)
        freqs = np.fft.rfftfreq(_VIS_WIN, 1.0 / sr)
        b_f1_lo = (freqs >= 150) & (freqs < 450)     # F1 of close vowels
        b_f1_hi = (freqs >= 450) & (freqs < 1100)    # F1 of open vowels
        b_f2_bk = (freqs >= 600) & (freqs < 1300)    # F2 of rounded vowels
        b_f2_fr = (freqs >= 1700) & (freqs < 3200)   # F2 of spread vowels
        b_hiss = (freqs >= 3800) & (freqs < 8000)    # fricatives

        # One frame per hop across the *whole* block. Stepping only while a full
        # window fits stopped 1024 - 480 samples short of the end, so a 200 ms
        # batch yielded 160 ms of schedule: the mouth ran out of frames before
        # the audio ran out of sound, and each batch no longer lined up with the
        # end of the one before it. Losing 20 % of every batch is most of why
        # the mouth did not track the words.
        out = []
        for start in range(0, x.size, _VIS_HOP):
            # The level gates closures, so it is measured over exactly this
            # 20 ms and never looks ahead. The spectrum needs a longer window
            # to resolve formants and may be short-filled at the very end.
            level = _pcm_level(x[start:start + _VIS_HOP])
            seg = x[start:start + _VIS_WIN]
            if seg.size < _VIS_WIN:
                seg = np.concatenate([seg, np.zeros(_VIS_WIN - seg.size,
                                                    dtype=np.float32)])
            if level <= 0.0:
                out.append((0.0, 0.0, 0.0))
                continue
            mag = np.abs(np.fft.rfft((seg - seg.mean()) * win))
            f1l, f1h = float(mag[b_f1_lo].sum()), float(mag[b_f1_hi].sum())
            f2b, f2f = float(mag[b_f2_bk].sum()), float(mag[b_f2_fr].sum())
            hiss = float(mag[b_hiss].sum())

            openness = f1h / (f1l + f1h + 1e-6)
            width = (f2f - f2b) / (f2f + f2b + 1e-6)
            # A wide-open jaw physically cannot purse, so openness damps width.
            # /a/ has a low enough F2 to read as "rounded" on the bands alone;
            # letting openness suppress the width term is what keeps an open
            # vowel from pursing.
            width *= (1.0 - openness) ** 0.8
            # Fricatives are formed with a nearly closed mouth.
            h = hiss / (f1l + f1h + f2b + f2f + hiss + 1e-6)
            openness *= 1.0 - 0.65 * min(1.0, h * 2.5)
            out.append((level,
                        float(min(1.0, max(0.0, openness))),
                        float(min(1.0, max(-1.0, width)))))
        return out
    except Exception:
        return []


def _describe_tools(declarations) -> str:
    """One line per capability, straight from the live tool declarations.

    Derived rather than written down: the action and plugin registries are
    discovered at startup, so whatever the user has installed is what the model
    is told it can do. Adding a plugin extends this by itself, and removing one
    stops the model from claiming an ability it no longer has.
    """
    lines = []
    for d in declarations or ():
        try:
            name = d.get("name") if isinstance(d, dict) else getattr(d, "name", None)
            desc = (d.get("description") if isinstance(d, dict)
                    else getattr(d, "description", "")) or ""
        except Exception:
            continue
        if not name:
            continue
        desc = " ".join(str(desc).split())
        lines.append(f"- {name}: {desc[:150]}" if desc else f"- {name}")
    return "\n".join(lines)


def _describe_limits(has_vision: bool, has_mic: bool) -> str:
    """The other half of self-knowledge: what is out of reach, and why.

    Derived from how the program is actually built, not from a list of refusals.
    A model that knows its boundaries stops improvising around them, and stating
    them as architecture rather than as rules keeps the answer honest in any
    language.
    """
    out = [
        "- Anything not listed above is outside your reach. Say so in one clause "
        "and offer the nearest thing you can actually do — never mime an action "
        "you cannot take, and never report a result you did not get.",
        "- You act on this machine only. You cannot reach the user's other "
        "devices, accounts or hardware except through the tools listed above.",
        "- You remember what is in the memory block and what has been said this "
        "session. Anything else you were told before is gone unless it was saved.",
    ]
    if has_vision:
        out.append(
            "- Your sight is not continuous. You see nothing until you call a "
            "vision tool, and then only that single frame at that moment — you "
            "cannot watch, monitor or notice something changing on screen.")
    else:
        out.append("- You have no sight at all in this build.")
    if has_mic:
        out.append(
            "- You hear nothing while the microphone is muted, and you cannot "
            "unmute it yourself.")
    return "\n".join(out)


def _render_prompt(template: str, values: dict) -> str:
    """Fill {tokens} in the prompt template.

    A plain replace rather than str.format: the file is meant to be edited by
    hand, and a stray brace in someone's own wording must never take the app
    down at startup.
    """
    out = template or ""
    for key, val in values.items():
        out = out.replace("{" + key + "}", str(val))
    return out


def _get_api_key() -> str:
    try:
        from core.gemini import api_key
        k = (api_key() or "").strip()
        if k:
            return k
    except Exception:
        pass
    try:
        from core.credential_vault import get_secret
        return (get_secret("gemini", "api_key", fallback_legacy=True) or "").strip()
    except Exception:
        return ""


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are CHARLIE, an autonomous personal AI computer assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

# Unauthorized foreign scripts (Chinese / Japanese / Korean / Cyrillic / Thai)
_UNAUTHORIZED_FOREIGN_RE = re.compile(
    r"[\u4e00-\u9fff"   # CJK unified ideographs (Chinese / Japanese Kanji)
    r"\u3400-\u4dbf"   # CJK unified ideographs extension A
    r"\u3040-\u30ff"   # Hiragana & Katakana (Japanese)
    r"\uac00-\ud7af"   # Hangul (Korean)
    r"\u0400-\u04ff"   # Cyrillic (Russian)
    r"\u0e00-\u0e7f"   # Thai
    r"]"
)

# User explicit command permitting foreign languages (e.g. "Charlie speak in Chinese")
_FOREIGN_LANG_REQ_RE = re.compile(
    r"\b(?:speak\s+in|talk\s+in|switch\s+to|translate\s+(?:in|to)?|mein\s+(?:baat\s+karo|bolo))\s+"
    r"(?:chinese|mandarin|japanese|nihongo|korean|russian|french|german|spanish|thai)\b"
    r"|\b(?:chinese|mandarin|japanese|nihongo|korean|russian|french|german|spanish)\s+"
    r"(?:mein\s+baat\s+karo|mein\s+bolo|please|language|me\s+bolo)\b",
    re.IGNORECASE,
)

HINDI_UNCLEAR_FALLBACK = "Mujhe aapki baat samajh nahi aayi barabar, aap phir se bol sakte ho taki mai apki madad kar saku?"

# Transcript chunks shorter than this may legitimately repeat ("evet, evet"),
# so only longer ones are treated as duplicates.
_REPEAT_MIN = 12


def _is_repeat_chunk(txt: str, buf: list) -> bool:
    """True if this transcript chunk has already been seen this turn.

    Guards against the API re-sending the tail of a response across the several
    turn_completes a tool-using turn produces.
    """
    if len(txt) < _REPEAT_MIN:
        return bool(buf) and txt == buf[-1]
    joined = " ".join(buf)
    return txt in joined

def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()

TOOL_DECLARATIONS = [
    # ── Inline tools ─────────────────────────────────────────────────────────
    # These stay here (rather than in an actions/*.py TOOL dict) because their
    # handling is woven into live-session state — vision capture/injection,
    # camera stream, memory writes, the monitor engine, and shutdown. All other
    # tools live in their own action file and are auto-discovered by
    # core.action_loader (see CharlieLive.__init__).
    {
        "name": "system_status",
        "description": (
            "Returns real-time system metrics: CPU usage, RAM, GPU load, CPU temperature, "
            "uptime, and process count. Use when the user asks about computer performance, "
            "temperature, memory, or resource usage."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures the screen or webcam image for analysis. "
            "Default angle='screen' captures current PC display when user asks about on-screen content. "
            "CRITICAL: angle='camera' MUST ONLY be called when the user EXPLICITLY commands to open camera or scan an object "
            "(e.g. 'Hey Charlie, open the camera and analyze this thing', 'scan this object', 'camera se scan karo', 'dekho ye kya hai'). "
            "NEVER call angle='camera' autonomously, unprompted, or during ordinary greetings/chat."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "close_camera",
        "description": (
            "Closes the live camera view shown on screen. "
            "Call when the user says (in ANY language): close camera, stop camera, "
            "turn off camera, that's creepy, etc."
        ),
        "parameters": {"type": "OBJECT", "properties": {}, "required": []}
    },
    {
        "name": "manage_monitor",
        "description": (
            "Add, remove, or list background monitoring topics. "
            "CHARLIE checks these topics once a day and alerts the user when there is a new development. "
            "Use 'add' when the user says 'monitor X', 'track X', 'follow X'. "
            "Use 'remove' when the user says 'stop monitoring X'. "
            "Use 'list' when the user asks what is being monitored. "
            "Do NOT add crypto, financial, or trading topics."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type":        "STRING",
                    "description": "add | remove | list",
                },
                "topic": {
                    "type":        "STRING",
                    "description": "Topic to monitor or stop monitoring (e.g. 'space exploration', 'AI news')",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "shutdown_charlie",
        "description": (
            "Shuts down the assistant application completely. "
            "Call this ONLY when the user explicitly commands to exit the application, "
            "terminate the program, or quit the app completely (e.g. 'exit app', 'quit charlie', 'band kar do app'). "
            "Do NOT call this for casual goodbyes, greetings, pauses, or 'stop speaking' (use sleep instead)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Anees, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
    {
        "name": "recall_memory",
        "description": (
            "Look up a fact you have stored about the user but which is NOT in "
            "the memory block of your system prompt. "
            "The prompt lists the keys it did not have room for under "
            "'[ALSO REMEMBERED]' — if the user asks about anything named there, "
            "call this FIRST. "
            "Also call it before saying you do not know something personal, and "
            "when the user asks what you remember about them (leave query empty "
            "for everything). "
            "This is a local file search: it is instant and costs nothing."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": (
                        "Keyword to search for — a name, a topic, a category "
                        "(e.g. 'ayse', 'coffee', 'projects'). "
                        "Leave empty to list everything stored."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "undo",
        "description": (
            "Reverse the last change YOU made to this computer — a file you "
            "moved, renamed, created or wrote, or a setting you changed such as "
            "volume, brightness, dark mode or WiFi. "
            "Call this whenever the user says undo, revert, take it back, put it "
            "back, cancel that, or tells you that you did the wrong thing, in ANY "
            "language. "
            "Use action='list' when they ask what can be undone. "
            "This only covers your own actions — it is not the Ctrl+Z of whatever "
            "application is on screen (that is computer_settings with action 'undo')."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "undo (default) — reverse the last change | list — show what can be undone",
                },
            },
            "required": [],
        },
    },
]

class _ReconnectSignal(Exception):
    """Raised inside the session TaskGroup to force a clean, voluntary reconnect
    (e.g. the user picked a new voice — the voice is fixed at connect time, so
    the session must be rebuilt).

    Carries `keep_context`: True for an ordinary rebuild, where the stored
    resumption handle is replayed and the conversation continues; False when the
    new session must genuinely start clean (see the voice-change note in
    _on_voice_change)."""

    def __init__(self, keep_context: bool = True):
        super().__init__()
        self.keep_context = keep_context


def _is_reconnect_signal(exc: BaseException) -> bool:
    """True if `exc` is a _ReconnectSignal, or a(n) (Base)ExceptionGroup that
    wraps one — TaskGroup bundles child exceptions into a group."""
    if isinstance(exc, _ReconnectSignal):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_is_reconnect_signal(sub) for sub in exc.exceptions)
    return False


def _keep_context_of(exc: BaseException) -> bool:
    """Read `keep_context` off a reconnect signal, unwrapping the group the
    TaskGroup put it in. Defaults to True: an unexpected shape must not silently
    wipe the conversation."""
    if isinstance(exc, _ReconnectSignal):
        return getattr(exc, "keep_context", True)
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            if _is_reconnect_signal(sub):
                return _keep_context_of(sub)
    return True


class CharlieLive:
    def __init__(self, ui: CharlieUI):
        self.ui             = ui
        self._asst_name     = "CHARLIE"   # updated each session from config
        self.session              = None
        self.audio_in_queue       = None
        self.out_queue            = None
        self._loop                     = None
        self._is_speaking         = False
        self._speaking_lock       = threading.Lock()
        # Real-time microphone buffer and dedicated DSP worker
        self._mic_raw_queue       = None
        self._mic_worker_thread   = None
        self._mic_worker_stop     = None
        self._mic_dropped_frames  = 0
        self._mic_last_drop_log   = 0.0
        self._playback_underruns  = 0
        # Fallback TTS serialization and immediate cancellation
        self._fallback_tts_queue: _queue.Queue = _queue.Queue()
        self._current_fallback_cancel: Optional[threading.Event] = None
        self._fallback_worker_thread = threading.Thread(
            target=self._fallback_tts_worker,
            daemon=True,
            name="charlie-fallback-tts",
        )
        self._fallback_worker_thread.start()
        self._phone_active        = False   # True while phone mic is streaming; pauses PC mic
        self._pending_vision       = None    # (img_bytes, mime_type, question, angle) to inject after tool response
        self._vision_cam_active    = False   # True if camera was opened for vision → auto-close after response
        self._vision_close_pending = False   # True after vision injected; next turn_complete closes camera
        self._vision_last_time     = 0.0     # monotonic time of last screen_process call (cooldown guard)
        self._vision_busy          = False   # True while a vision capture/inject cycle is in flight
        self._interrupted          = False   # True while draining audio after user interrupt
        self._barge_in_pending     = False   # local mic has yielded the current reply
        self._barge_in_buffer: list[bytes] = []  # short confirmed-speech pre-roll
        self._voice_audio = deque(maxlen=max(24, int(8 * SEND_SAMPLE_RATE / CHUNK_SIZE)))
        self._fallback_stt = None
        # While a tool is running, its progress notices stay in the activity
        # log. Starting extra Live turns here can overlap the final tool answer
        # and is what made one response sound like two different voices.
        self._tool_progress_active = False
        # Transcript-driven mouth shapes for the avatar. Fed from the receive
        # loop as words arrive, drained by the playback loop against the audio.
        self._visemes              = VisemeStream()
        self._last_out_logged      = ""      # de-dupes a re-sent transcript tail
        # Push-to-talk
        self._ptt_enabled          = False
        self._ptt_held             = False
        self._ptt                  = None    # core.hotkey.PushToTalk
        self._out_level            = 0.0     # level of the audio being played right now
        self._echo                 = EchoGuard()
        # `stream.write()` returns when the buffer accepts the audio, not when the
        # speaker has finished with it, so sound is still in the room after the
        # speaking flag drops. Streaming the microphone during that gap is how an
        # assistant ends up answering itself. Measured from the device rather than
        # guessed; see _play_audio.
        self._out_latency          = 0.20    # seconds, replaced with the real value
        self._tail_until           = 0.0     # monotonic time the echo tail expires
        # Wall-clock time at which the audio written next will begin to sound.
        # The mouth is scheduled against this, never against "now": batches are
        # handed to the device far faster than they play, so "now" ran the lips
        # ahead of the words and cut every schedule short. 0 = nothing playing.
        self._play_cursor          = 0.0
        self.ui.on_push_to_talk   = self.set_push_to_talk
        self.ui.ptt_hold          = self._on_ptt
        self.ui.on_text_command   = self._on_text_command
        self._chat_assistant      = ProChatAssistant()
        self._chat_dictation      = ChatDictationService()
        self.ui.on_chat_command   = self._on_chat_command
        self.ui.on_new_chat       = self._new_chat
        self.ui.on_chat_dictation = self._on_chat_dictation
        self.ui.on_remote_clicked = self._make_remote_key
        self.ui.on_interrupt      = self.interrupt
        self.ui.on_voice_change   = self._on_voice_change     # voice picker → rebuild session
        self.ui.on_listening_change = self._on_listening_change
        self.ui.on_audio_device_change = self._on_audio_device_change
        self.ui.on_reconnect_requested = self.trigger_reconnect
        self._retry_count = 0
        self._reconnect_event: asyncio.Event | None = None
        self._reconnect_keep = True   # False → next rebuild drops the resumption handle
        set_profile_change_notifier(self._on_profile_change)

        # Background brain, procedural playbooks, and memory enrichment
        try:
            from engine.brain_trainer import train_charlie_brain_and_memory
            threading.Thread(target=train_charlie_brain_and_memory, daemon=True, name="brain-trainer").start()
        except Exception:
            pass

        # ── Session resumption ─────────────────────────────────────────
        # The server issues a resumption handle every few seconds and reissues
        # it as the conversation moves on. Before this, session_resumption was
        # switched ON in the config and the update was never read, so the handle
        # was thrown away and EVERY reconnect — a dropped packet, a voice change,
        # switching microphone — started an empty session. "Unlimited sessions"
        # leaked through exactly this hole.
        #
        # Deliberately in RAM only, never written to disk. Persisting it would
        # make a fresh launch continue yesterday's conversation, which sounds
        # appealing but breaks the session-summary flow: _save_session_summary
        # runs at shutdown and the morning briefing pops it the next day. A
        # conversation that never ends never produces a summary, and the
        # "yesterday we talked about…" line silently disappears.
        self._resume_handle: str | None = None
        self._turn_done_event: asyncio.Event | None = None
        self._dashboard     = None
        self._briefing_sent    = False          # morning briefing fires once per process
        self._greeting_sent   = False          # personalised greeting fires once per process
        self._lang_mgr: SessionLanguageManager | None = None   # per-session language state
        self._awaiting_lang_pref = False       # True while waiting for user's language reply
        self._cultural_mgr: CulturalGreetingManager | None = None  # cultural greeting engine
        self._user_id  = "default_user"        # set during greeting from profile name
        self._user_name_display = ""           # display name for cultural replies
        self._voice_preview_pending = False     # speak once after a chosen voice reconnects
        self._sys_monitor      = SystemMonitor()  # persistent cooldown state
        self._proactive        = ProactiveEngine()
        self._last_user_speech = time.monotonic()  # updated on every user utterance
        self._speech_hangover  = 0                 # VAD hangover blocks
        self._noise_floor      = 25.0              # adaptive ambient noise floor
        self._session_log: list[str] = []          # conversation turns for end-of-session summary
        self._foreign_hallucination_blocked = False # guards against Chinese/Japanese foreign hallucinations

        self._enhanced_live = True  # proactive audio; auto-disabled if the server rejects it
        self._tuned_live    = True  # turn-taking / media / thinking knobs; same fallback
        self._conn_backoff  = 3     # reconnect delay in seconds; grows on network failures
        self._recognized_user: str | None = None  # set when voice profile matches a stored user

        _inline_names = {t["name"] for t in TOOL_DECLARATIONS}

        # File-backed tools: every actions/*.py with a TOOL dict, discovered the
        # same way plugins are. Reserved names = the inline tools above, so an
        # action can never shadow one.
        self._action_registry = discover_actions(
            actions_dir=RESOURCE_DIR / "actions",
            reserved_names=_inline_names,
            logger=lambda msg: print(f"[Actions] {msg}"),
        )

        # Plugins must not collide with either an inline tool or a discovered action.
        _core_names = _inline_names | self._action_registry.names()
        self._plugin_registry = discover_plugins(
            # Plugins are user-installed code, so unlike bundled actions they
            # live beside the executable and survive an app update.
            plugins_dir=BASE_DIR / "plugins",
            core_tool_names=_core_names,
            # Console gets the full boot transcript; the activity log gets only
            # what the user has to know about. Every plugin loading correctly is
            # the expected case and does not belong in their conversation.
            logger=lambda msg: print(f"[Plugins] {msg}"),
            notify=lambda msg: self.ui.write_log(f"SYS: {msg}"),
        )
        self._chat_assistant.set_registries(self._action_registry, self._plugin_registry)
        self._chat_assistant.set_player(self.ui)
        self.ui.get_plugins = self._plugin_registry.list_for_ui
        self.ui.get_plugin_settings = self._plugin_registry.settings_schemas  # ⚙ settings tab
        self.ui.rescan_plugins = lambda: self._plugin_registry.rescan(BASE_DIR / "plugins", _core_names)
        self.ui.request_say = self.plugin_say   # plugins: mid-task speech channel

        from core.tool_gateway import GatewayCircuitBreaker
        self._gateway_circuit_breaker = GatewayCircuitBreaker(max_failures=3)
        self._pilot_fallback_occurred = False

        # ── Wake word ────────────────────────────────────────────────────────
        # _awake gates the mic (see _listen_audio) and the background speakers.
        # It is True whenever wake word is OFF, so default behaviour is unchanged.
        self._wake_enabled     = get_wake_word_enabled()
        self._awake            = not self._wake_enabled
        self._wake_detector: WakeWordDetector | None = None
        self._wake_sleep_timeout = WAKE_SLEEP_TIMEOUT

        # Restore the saved push-to-talk preference. Doing it here rather than
        # in __init__ means the hotkey thread only exists once there is a
        # session to talk to.
        if get_push_to_talk_enabled():
            try:
                self.set_push_to_talk(True)
            except Exception as e:
                print(f"[CHARLIE] ⚠ Push-to-talk unavailable: {e}")
        # UI control surface for the Wake Word settings section.
        self.ui.wake_is_ready    = wake_is_ready          # () -> bool
        self.ui.wake_get_state   = self._wake_state       # () -> dict
        self.ui.on_wake_toggle   = self._ui_wake_toggle   # (enable: bool) -> str
        self.ui.on_wake_manual   = self._ui_wake_manual   # () -> toggle awake/asleep
        self.ui.on_wake_install  = self._ui_wake_install  # () -> (ok, msg)

        # Register active runtime in runtime_voice_control bridge
        try:
            from core.runtime_voice_control import register_voice_runtime
            register_voice_runtime(self)
        except Exception as e:
            print(f"[CHARLIE] ⚠️ Could not register voice runtime: {e}")

    def trigger_reconnect(self):
        """Thread-safe / slot-safe: reset retry counters and fire immediate reconnect."""
        self._retry_count = 0
        if hasattr(self, "_reconnect_event") and self._reconnect_event and self._loop:
            self._loop.call_soon_threadsafe(self._reconnect_event.set)

    # ── Wake word: state machine ─────────────────────────────────────────────

    def _wake_state(self) -> dict:
        # A loaded, running detector is definitively ready; otherwise fall back
        # to the cheap on-disk model-file check (no Model construction).
        ready = bool(self._wake_detector and self._wake_detector.ready) or wake_is_ready()
        return {"enabled": self._wake_enabled, "awake": self._awake, "ready": ready}

    def _ensure_wake_detector(self) -> bool:
        """Load the detector once (model loads on first start). Idempotent."""
        if self._wake_detector is None:
            self._wake_detector = WakeWordDetector(
                on_detect=self._on_wake_detected,
                logger=lambda m: print(f"[Wake] {m}"),
                notify=lambda m: self.ui.write_log(f"SYS: {m}"),
            )
        if not self._wake_detector.ready:
            return self._wake_detector.start()
        return True

    def _on_wake_detected(self) -> None:
        """Called from the detector thread when 'Hey Charlie' is heard."""
        self.wake(reason="wake word")

    def wake(self, reason: str = "wake word") -> None:
        if self._awake:
            return
        self._awake = True
        self._last_user_speech = time.monotonic()   # start the auto-sleep clock now
        if not self.ui.muted:
            self.ui.set_state("LISTENING")
        self.ui.write_log(f"SYS: Awake — {reason}.")

    def sleep(self, reason: str = "timeout") -> None:
        if not self._awake:
            return
        self._awake = False
        self.set_speaking(False)
        self.ui.set_state("SLEEPING")
        self.ui.write_log(f"SYS: Sleeping — {reason}. Say 'Hey Charlie' to wake me.")

    async def _run_sleep_watch(self) -> None:
        """Auto-sleep after the configured silence window (wake-word mode only)."""
        while True:
            await asyncio.sleep(5)
            if not self._wake_enabled or not self._awake:
                continue
            with self._speaking_lock:
                speaking = self._is_speaking
            if speaking:
                continue
            if (time.monotonic() - self._last_user_speech) > self._wake_sleep_timeout:
                self.sleep(reason="no speech for 2 minutes")

    # ── Wake word: UI callbacks (called from the Qt thread) ──────────────────

    def _ui_wake_toggle(self, enable: bool) -> str:
        """Enable/disable wake word from the settings UI. Returns a status token:
        'enabled' | 'disabled' | 'need_download'."""
        if enable:
            if not wake_is_ready():
                return "need_download"
            self._wake_enabled = True
            save_wake_word_enabled(True)
            self._ensure_wake_detector()
            self.sleep(reason="wake word enabled")
            return "enabled"
        else:
            self._wake_enabled = False
            save_wake_word_enabled(False)
            self.wake(reason="wake word disabled")
            return "disabled"

    def _ui_wake_manual(self) -> None:
        """Manual sleep/wake button in the UI."""
        if not self._wake_enabled:
            return
        if self._awake:
            self.sleep(reason="you tapped sleep")
        else:
            self.wake(reason="you tapped wake")

    def _ui_wake_install(self) -> tuple[bool, str]:
        """Download openwakeword + the model (runs in a UI worker thread)."""
        # Triggered by the user pressing the button, so its progress is exactly
        # what they are waiting to see.
        return wake_install(logger=lambda m: print(f"[Wake] {m}"),
                            notify=lambda m: self.ui.write_log(f"SYS: {m}"))

    def plugin_say(self, instruction: str) -> None:
        """
        Thread-safe speech channel for plugins: lets a plugin ask CHARLIE to
        say something short WHILE its run() is still executing (plugins block
        their executor thread, so they can't speak through the tool response
        until they finish). The instruction is injected into the Live session
        exactly like a proactive check-in; Gemini phrases it naturally in the
        user's language. Silently a no-op when no session is connected.
        """
        if self._tool_progress_active:
            self.ui.write_log(f"SYS: {str(instruction).strip()}")
            return
        loop = getattr(self, "_loop", None)
        if not loop or not self.session:
            self.ui.write_log("SYS: CHARLIE is still connecting. Please try again in a moment.")
            return

        async def _say():
            try:
                await self.session.send_client_content(
                    turns={"role": "user", "parts": [{"text": instruction}]},
                    turn_complete=True,
                )
            except Exception as e:
                print(f"[PluginSay] {e}")

        try:
            asyncio.run_coroutine_threadsafe(_say(), loop)
        except Exception as e:
            print(f"[PluginSay] {e}")

    def request_reconnect(self, keep_context: bool = True, reason: str = ""):
        """Thread-safe: ask the run loop to tear down and rebuild the Live
        session. Called from the Qt thread. No-op until the async loop and
        reconnect event exist.

        `keep_context=False` drops the resumption handle so the new session
        starts empty — only for changes the server cannot apply to a resumed
        session."""
        loop = getattr(self, "_loop", None)
        ev   = self._reconnect_event
        self._reconnect_keep   = keep_context
        self._reconnect_reason = reason
        if loop and ev is not None:
            loop.call_soon_threadsafe(ev.set)

    def _on_voice_change(self):
        """Voice picker applied.

        The voice is baked into the session at connect time, so a rebuild is
        required. It is rebuilt WITHOUT the resumption handle on purpose:
        resuming restores the server's own session state, and the safe reading
        is that it restores the voice with it — which would make the picker
        appear to do nothing. Losing context here is acceptable because changing
        voice is a deliberate, rare act; losing it on a dropped packet was not."""
        self._voice_preview_pending = True
        self.request_reconnect(keep_context=False, reason="new voice")

    def _on_audio_device_change(self):
        """Microphone or speaker changed. Both streams are opened inside the
        session TaskGroup, so they can only be re-opened by rebuilding it —
        but the conversation is kept, which is the whole reason resumption
        landed before this feature did."""
        self.request_reconnect(keep_context=True, reason="audio device")

    def _on_listening_change(self):
        """Turn endpoint timing changed; reconnect while retaining conversation."""
        self.request_reconnect(keep_context=True, reason="listening mode")

    def _on_profile_change(self, *_):
        """Reload profile-scoped memory and personal context in a clean session."""
        self.request_reconnect(keep_context=False, reason="user profile")

    async def _watch_reconnect(self):
        """Session-scoped task: when a voluntary reconnect is requested, raise a
        signal that unwinds the TaskGroup so the run loop rebuilds the session."""
        assert self._reconnect_event is not None
        await self._reconnect_event.wait()
        self._reconnect_event.clear()
        keep   = self._reconnect_keep
        reason = getattr(self, "_reconnect_reason", "") or "settings"
        self.ui.write_log(
            f"SYS: Applying {reason} — reconnecting"
            + ("..." if keep else " (starting a fresh conversation)...")
        )
        raise _ReconnectSignal(keep_context=keep)

    def _make_remote_key(self):
        """Called from Qt main thread when user presses Remote Control."""
        if self._dashboard is None or not getattr(self._dashboard, "is_running", False):
            self.ui.write_log(
                "SYS: Remote Control unavailable (dashboard port unavailable or disabled)."
            )
            return None
        key    = self._dashboard.new_key()
        url    = self._dashboard.get_url()
        manual = self._dashboard.get_manual_url()
        return url, key, f"{url}/auto-login?key={key}", manual

    def _on_text_command(self, text: str):
        if not text:
            return
        if not self._loop or not self.session:
            self._on_chat_command(text)
            return
        # Respect wake-word sleep: a typed command must not be answered while
        # asleep either (the sleep gate is not just for the mic). Wake first with
        # "Hey Charlie" or the WAKE NOW button.
        if self._wake_enabled and not self._awake:
            self.ui.write_log("SYS: I'm asleep — say 'Hey Charlie' or tap WAKE NOW first.")
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"role": "user", "parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def _on_chat_command(self, text: str) -> None:
        """Answer a typed message through the detailed text-only chat model."""
        self.ui.set_chat_busy(True)
        try:
            assistant_name = get_assistant_name()
            answer = self._chat_assistant.respond(
                text,
                attachment_path=self.ui.current_file,
            )
            self.ui.write_log(f"{assistant_name}: {answer}")
            self._session_log.append(f"User: {text}")
            self._session_log.append(f"{assistant_name}: {answer}")
            record_conversation_turn("User", text)
            record_conversation_turn(assistant_name, answer)
            # AI Chat is intentionally text-only. Voice mode owns spoken replies;
            # chat dictation only fills the composer and never starts TTS.
        except Exception as exc:
            self.ui.write_log(f"ERR: AI Chat — {exc}")
        finally:
            self.ui.set_chat_busy(False)

    def _new_chat(self) -> None:
        self._chat_assistant.new_chat()

    def _on_chat_dictation(self, enabled: bool) -> None:
        """Give AI Chat temporary, exclusive ownership of speech-to-text."""
        if not enabled:
            self._chat_dictation.stop()
            return
        if not self.ui.chat_mode:
            self.ui.set_chat_dictation_state(False, "Open AI Chat before using dictation.")
            return

        def result(text: str) -> None:
            if self.ui.chat_mode:
                self.ui.set_chat_dictation_text(text)

        def status(value: str) -> None:
            if value == "Idle" and self.ui.chat_dictating:
                self.ui.set_chat_dictation_state(False)

        def error(message: str) -> None:
            self.ui.set_chat_dictation_state(False, message)

        if not self._chat_dictation.start(result, status, error):
            self.ui.set_chat_dictation_state(False, "Dictation is already finishing. Try again in a moment.")

    def _tail_active(self) -> bool:
        """True while the speakers may still be finishing our last sentence."""
        return time.monotonic() < self._tail_until

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            was_speaking = self._is_speaking
            self._is_speaking = value
        # A new assistant response may be interrupted once. Do not clear this
        # on every playback chunk, or a sustained user utterance would schedule
        # repeated drains of the same response.
        if value and not was_speaking:
            self._barge_in_pending = False
            self._barge_in_buffer.clear()
        if value:
            self._tail_until = 0.0
        else:
            # Hold the guard open across the device's own output latency plus a
            # margin for the room. The microphone is NOT muted during it — the
            # guard still lets a genuine reply through, so answering instantly
            # still works. Only our own echo is dropped.
            self._tail_until = time.monotonic() + self._out_latency + _TAIL_MARGIN
        if not value:
            # The echo history is deliberately NOT cleared here: the tail above
            # still needs it to recognise our own voice. It is dropped when the
            # tail expires. What the guard learned about the room always stays.
            self._out_level = 0.0
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def set_push_to_talk(self, enabled: bool) -> str:
        """Turn hold-to-talk on or off. Returns the scope actually achieved."""
        from core.hotkey import PushToTalk

        self._ptt_enabled = bool(enabled)
        self._ptt_held = False
        if not enabled:
            if self._ptt is not None:
                self._ptt.stop()
                self._ptt = None
            return "off"

        if self._ptt is None:
            self._ptt = PushToTalk(self._on_ptt)
        scope = self._ptt.start()
        # A window-scoped chord is a real limitation, not a detail — say it once
        # in the log so nobody wonders why it does nothing while another app is
        # focused. Reporting it must never be able to undo the thing it reports.
        try:
            self.ui.write_log(
                f"SYS: Push-to-talk on — hold {self._ptt.label}"
                + ("." if scope == "global"
                   else " (works while this window is focused)."))
        except Exception:
            pass
        return scope

    def _on_ptt(self, held: bool) -> None:
        """Chord pressed or released — may arrive on the hotkey thread."""
        self._ptt_held = held
        if held:
            # Holding the key is also a way to wake it, so push-to-talk works
            # without having to say the wake word first.
            if self._wake_enabled and not self._awake:
                self._awake = True
                self._last_user_speech = time.monotonic()
        try:
            if held:
                state = "LISTENING"
            elif self._wake_enabled and not self._awake:
                state = "SLEEPING"
            else:
                with self._speaking_lock:
                    state = "SPEAKING" if self._is_speaking else "LISTENING"
            self.ui.set_state(state)
        except Exception:
            pass

    def interrupt(self) -> None:
        """Stop CHARLIE mid-speech: drain queued audio and open mic immediately."""
        self._interrupted = True

        # Stop currently playing fallback TTS speech and clear pending queue
        if getattr(self, "_current_fallback_cancel", None):
            self._current_fallback_cancel.set()
        if getattr(self, "_fallback_tts_queue", None):
            while True:
                try:
                    self._fallback_tts_queue.get_nowait()
                    self._fallback_tts_queue.task_done()
                except (_queue.Empty, Exception):
                    break

        q = self.audio_in_queue
        if q:
            drained = 0
            while True:
                try:
                    q.get_nowait()
                    drained += 1
                except Exception:
                    break
            if drained:
                print(f"[CHARLIE] ✋ Interrupted — {drained} audio chunks discarded")
        self.set_speaking(False)
        # The words we were about to mouth are never going to be spoken now.
        self._visemes.reset()
        self._play_cursor = 0.0     # next batch starts a fresh timeline
        if self._turn_done_event:
            self._turn_done_event.clear()
        self.ui.write_log("SYS: Interrupted — listening...")

    def _fallback_tts_worker(self) -> None:
        """Dedicated background worker to serialize fallback TTS and avoid overlapping speech."""
        while True:
            try:
                item = self._fallback_tts_queue.get()
                if item is None:
                    break
                clean_text, cancel_event = item
                if cancel_event.is_set():
                    self._fallback_tts_queue.task_done()
                    continue

                self.set_speaking(True)
                try:
                    from core.tts import EdgeTTSEngine, WindowsSAPITTSEngine
                    persona = (active_profile().get("persona") or "").lower()
                    voice = "en-US-JennyNeural" if "female" in persona else "en-US-GuyNeural"
                    self.ui.classify_and_set_emotion(clean_text)
                    try:
                        engine = EdgeTTSEngine(voice=voice)
                        engine.speak(clean_text, ui=self.ui, cancel_event=cancel_event)
                    except Exception as e:
                        if not cancel_event.is_set():
                            print(f"[CHARLIE] EdgeTTS error: {e} — falling back to SAPI5")
                            engine = WindowsSAPITTSEngine(voice=persona or "female")
                            engine.speak(clean_text, cancel_event=cancel_event)
                except Exception as e:
                    if not cancel_event.is_set():
                        print(f"[CHARLIE] Local TTS error: {e}")
                finally:
                    self.set_speaking(False)
                    self._fallback_tts_queue.task_done()
            except Exception:
                pass

    def _queue_realtime_audio(self, loop, data: bytes) -> None:
        """Safely hand one microphone block from an audio callback to asyncio."""
        queue = self.out_queue
        if queue is None:
            return
        def _safe_put():
            try:
                queue.put_nowait({"data": data, "mime_type": INPUT_AUDIO_MIME})
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    queue.put_nowait({"data": data, "mime_type": INPUT_AUDIO_MIME})
                except Exception:
                    pass
        try:
            loop.call_soon_threadsafe(_safe_put)
        except RuntimeError:
            # The session is reconnecting and its event loop is closing.
            pass

    def _request_interrupt_from_audio_thread(self) -> None:
        """Stop playback on the asyncio loop; sounddevice callbacks are threads."""
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        try:
            loop.call_soon_threadsafe(self.interrupt)
        except RuntimeError:
            pass

    def _is_foreign_language_permitted(self, text: str = "") -> bool:
        """True if user explicitly commanded Charlie to speak in Chinese, Japanese, or another foreign language."""
        if text and _FOREIGN_LANG_REQ_RE.search(text):
            return True
        if getattr(self, "_lang_mgr", None) and self._lang_mgr.lang in ("zh", "ja", "ko", "chinese", "japanese"):
            return True
        for entry in reversed(self._session_log[-6:]):
            if _FOREIGN_LANG_REQ_RE.search(entry):
                return True
        return False

    def _has_unauthorized_foreign(self, text: str) -> bool:
        """Checks if text contains foreign characters (Chinese/Japanese/etc.) without explicit user command."""
        if not text:
            return False
        if _UNAUTHORIZED_FOREIGN_RE.search(text):
            return not self._is_foreign_language_permitted(text)
        return False

    def speak(self, text: str):
        if not text or not str(text).strip():
            return
        clean_text = str(text).strip()
        if self._tool_progress_active:
            self.ui.write_log(f"SYS: {clean_text}")
            return

        # Cancel any active fallback speech immediately and clear pending queue
        if getattr(self, "_current_fallback_cancel", None):
            self._current_fallback_cancel.set()
        if getattr(self, "_fallback_tts_queue", None):
            while True:
                try:
                    self._fallback_tts_queue.get_nowait()
                    self._fallback_tts_queue.task_done()
                except (_queue.Empty, Exception):
                    break

        # Ensure worker thread is running
        if not getattr(self, "_fallback_worker_thread", None) or not self._fallback_worker_thread.is_alive():
            self._fallback_worker_thread = threading.Thread(
                target=self._fallback_tts_worker,
                daemon=True,
                name="charlie-fallback-tts",
            )
            self._fallback_worker_thread.start()

        cancel_event = threading.Event()
        self._current_fallback_cancel = cancel_event
        self._fallback_tts_queue.put((clean_text, cancel_event))

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        # Load customization from config
        try:
            _cfg = json.loads(open(API_CONFIG_PATH, encoding="utf-8").read())
            self._asst_name = (_cfg.get("assistant_name") or "CHARLIE").strip()
            _user_name = (active_profile().get("name") or _cfg.get("user_name") or "").strip()
        except Exception:
            self._asst_name = "CHARLIE"
            _user_name = ""

        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        # Addressing is a profile preference. Repeating a name or "sir" in every
        # reply is one of the strongest cues that a voice assistant is scripted.
        _address_pref = load_hub().get("speech", {}).get("address", "occasional")
        if _address_pref == "none":
            _addr = "ADDRESS: Do not use a name, honorific, sir, or another form of address."
        elif _address_pref == "casual":
            _addr = "ADDRESS: Speak directly and casually. Do not call the user sir."
        elif _address_pref == "name" and _user_name and _user_name != "Primary user":
            _addr = f"ADDRESS: The user's name is '{_user_name}'. Use it occasionally, never mechanically."
        elif _user_name and _user_name != "Primary user":
            _addr = f"ADDRESS: You may call the user '{_user_name}' occasionally, not in every reply."
        else:
            _addr = (
                "ADDRESS: Use a natural respectful form only when it adds warmth or clarity. "
                "Do not begin every reply with sir or repeat an honorific mechanically."
            )
        _multilingual_ctx = (
            "LANGUAGE & ACCURACY RULES (CRITICAL & ABSOLUTE):\n"
            "- PRIMARY LANGUAGE: Always start every session in English.\n"
            "- MULTILINGUAL ANNOUNCEMENT: You can speak in English, Hindi, Marathi, and all regional languages.\n"
            "- TRANSITION TO HINDI: When the user speaks to you in Hindi (or Hinglish), immediately transition into Hindi and KEEP speaking in Hindi for all future turns.\n"
            "- DO NOT CHANGE LANGUAGE IN BETWEEN: Once speaking in a language (English or Hindi), stay locked in that language. Never switch languages in between unless the user explicitly commands a switch.\n"
            "- STRICT PROHIBITION ON AUTOMATIC SWITCHING TO TAMIL OR TELUGU: Absolutely never switch to Tamil, Telugu, or any other regional language unless the user directly and explicitly asks for that specific language.\n"
            "- STRICT PROHIBITION ON UNREQUESTED FOREIGN LANGUAGES: Never speak in Chinese, Japanese, Korean, Arabic, Russian, French, German, Spanish, or any other language unless directly commanded.\n"
            "- UNCLEAR WORDS / AUDIO MISUNDERSTANDINGS: If user speech is unclear, inaudible, or quiet, ask politely in the currently active language. Never guess or switch language on noise.\n"
            "- STRICT SILENCE ON NOISE: If incoming audio is silent, background static, breathing, or keyboard clicks, NEVER hallucinate or speak."
        )
        identity_ctx = (
            f"[IDENTITY]\n"
            f"Your name is {self._asst_name}. "
            f"Always refer to yourself as {self._asst_name}.\n"
            f"{get_assistant_grammar_instruction()}\n"
            f"{_multilingual_ctx}\n"
            f"{_addr}\n\n"
        )

        # Everything the model is told about *itself* is derived here, not
        # written into prompt.txt: the name comes from config, the platform from
        # the host, the capability list from the registries that were just
        # discovered. Rename the assistant, add a plugin or move to another OS
        # and this follows without anyone editing a prompt.
        from core.tool_gateway import (
            is_full_mode_forced, is_discovery_enabled, validate_discovery_readiness,
            record_telemetry, DISCOVERY_TOOL_DECLARATION, INVOCATION_TOOL_DECLARATION
        )
        manual_override = is_full_mode_forced()
        fallback_occurred = getattr(self, "_pilot_fallback_occurred", False)

        if manual_override:
            record_telemetry("tool_mode_full_sessions")
            _all_decls = (TOOL_DECLARATIONS
                          + self._action_registry.get_tool_declarations()
                          + self._plugin_registry.get_tool_declarations())
            print(f"[ToolMode] Tool mode: FULL ({len(_all_decls)} tools) [manual override]")
        elif fallback_occurred:
            record_telemetry("tool_mode_full_sessions")
            _all_decls = (TOOL_DECLARATIONS
                          + self._action_registry.get_tool_declarations()
                          + self._plugin_registry.get_tool_declarations())
            print(f"[ToolMode] Tool mode: FULL ({len(_all_decls)} tools)")
        else:
            valid, reason = validate_discovery_readiness(self._action_registry, self._plugin_registry)
            if valid:
                from core.tool_groups import get_core_tools
                core_tool_names = get_core_tools()
                core_inline = [d for d in TOOL_DECLARATIONS if d.get("name") in core_tool_names]
                core_actions = self._action_registry.get_tool_declarations(allowed_tools=core_tool_names)
                _all_decls = core_inline + core_actions + [DISCOVERY_TOOL_DECLARATION, INVOCATION_TOOL_DECLARATION]
                record_telemetry("tool_mode_discovery_sessions")
                print(f"[ToolMode] Tool mode: DISCOVERY ({len(_all_decls)} tools)")
            else:
                self._pilot_fallback_occurred = True
                print(f"[ToolMode] Discovery validation failed; falling back to FULL (73 tools). ({reason})")
                record_telemetry("discovery_fallback_to_full")
                record_telemetry("tool_mode_full_sessions")
                _all_decls = (TOOL_DECLARATIONS
                              + self._action_registry.get_tool_declarations()
                              + self._plugin_registry.get_tool_declarations())
                print(f"[ToolMode] Tool mode: FULL ({len(_all_decls)} tools)")
        _names = {(d.get("name") if isinstance(d, dict) else getattr(d, "name", ""))
                  for d in _all_decls}
        sys_prompt = _render_prompt(sys_prompt, {
            "assistant_name": self._asst_name,
            "platform": f"{_platform.system()} {_platform.release()}".strip(),
            "capabilities": _describe_tools(_all_decls),
            "limits": _describe_limits(
                has_vision="screen_process" in _names,
                has_mic=True,
            ),
        })

        parts = [time_ctx, identity_ctx, personal_prompt_context()]
        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)
        from core.assistant_guidance import conversation_guidance
        parts.append(conversation_guidance("voice"))

        # Gemini 3.8 Live defaults to asynchronous function calling. CHARLIE's
        # action loop waits for a tool result before speaking its outcome, so
        # keep that dependable behavior explicitly blocking after migration.
        _live_decls = []
        for declaration in _all_decls:
            if isinstance(declaration, dict):
                item = dict(declaration)
                item["behavior"] = "BLOCKING"
            else:
                try:
                    item = declaration.model_copy(
                        update={"behavior": types.Behavior.BLOCKING})
                except Exception:
                    item = declaration
            _live_decls.append(item)

        cfg = dict(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": _live_decls}],
            # Hand back the handle captured from the last session_resumption
            # update. `handle=None` is exactly the old behaviour (ask for
            # handles, start fresh), so the first connect of a run is unchanged.
            session_resumption=types.SessionResumptionConfig(
                handle=self._resume_handle
            ),
            # Sliding-window compression: session never dies from a full context
            # window — CHARLIE can stay in one conversation for hours
            context_window_compression=types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow(),
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=get_voice()
                    )
                )
            ),
        )
        if self._enhanced_live:
            # Proactive audio: CHARLIE stays silent when speech isn't addressed
            # to it (background chatter, talking to someone else in the room).
            # (Affective dialog was dropped: gemini-3.1-flash-live does not
            #  support it, and it never reliably detected tone in practice.
            #  To restore it on a 2.5 native-audio model, add back:
            #  cfg["enable_affective_dialog"] = True )
            if get_proactive_audio_enabled():
                cfg["proactivity"] = types.ProactivityConfig(proactive_audio=True)

        if self._tuned_live:
            cfg.update(self._tuning_config())

        return types.LiveConnectConfig(**cfg)

    def _tuning_config(self) -> dict:
        """The optional knobs, kept apart so one bad field can be dropped wholesale.

        Every one of these is a preview-API field. If a future model release
        stops accepting any of them the connection fails at setup, so the run
        loop turns `_tuned_live` off and reconnects on the plain config rather
        than leaving the user with an assistant that will not start.
        """
        out: dict = {}

        # How long the server waits through a pause before deciding your turn is
        # over. This — not the size of the prompt — is what most of the delay
        # before a reply actually is, and the default has to suit everybody, so
        # it is necessarily cautious.
        turn = get_turn_tuning()
        if turn.get("enabled", True):
            detect = types.AutomaticActivityDetection(
                silence_duration_ms=turn["silence_ms"],
                prefix_padding_ms=turn["prefix_ms"],
            )
            if turn["end_sensitivity"] == "high":
                detect.end_of_speech_sensitivity = types.EndSensitivity.END_SENSITIVITY_HIGH
            elif turn["end_sensitivity"] == "low":
                detect.end_of_speech_sensitivity = types.EndSensitivity.END_SENSITIVITY_LOW
            if turn["start_sensitivity"] == "high":
                detect.start_of_speech_sensitivity = types.StartSensitivity.START_SENSITIVITY_HIGH
            elif turn["start_sensitivity"] == "low":
                detect.start_of_speech_sensitivity = types.StartSensitivity.START_SENSITIVITY_LOW
            out["realtime_input_config"] = types.RealtimeInputConfig(
                automatic_activity_detection=detect)

        # Screenshots and camera frames are tokenised at this resolution and then
        # stay in the session's context. 'medium' keeps on-screen text legible
        # for a fraction of a full-resolution frame.
        res = get_media_resolution()
        if res != "default":
            out["media_resolution"] = {
                "low":    types.MediaResolution.MEDIA_RESOLUTION_LOW,
                "medium": types.MediaResolution.MEDIA_RESOLUTION_MEDIUM,
                "high":   types.MediaResolution.MEDIA_RESOLUTION_HIGH,
            }[res]

        # Thinking is left at the server default deliberately. Forcing the budget
        # to zero was measured on gemini-3.1-flash-live over interleaved trials
        # and did not make the first word arrive sooner — this model does not
        # appear to deliberate on the Live path, so pinning the field only adds a
        # way for a future release to behave differently. Set "thinking_enabled"
        # in config/api_keys.json to true to let it reason instead.
        # Gemini 3.8 Live performs interleaved reasoning internally and rejects
        # thinking_config in session setup, so the legacy toggle is ignored.

        return out

    def _get_fallback_stt(self):
        if not hasattr(self, "_fallback_stt") or self._fallback_stt is None:
            try:
                from core.stt import WhisperSTT
                self._fallback_stt = WhisperSTT(model_name="base")
            except Exception as e:
                print(f"[STT] Fallback WhisperSTT init error: {e}")
                self._fallback_stt = None
        return self._fallback_stt

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        # Opt-in voice enrollment/identification reads this local rolling sample.
        # Updating it is harmless for other tools and never persists raw audio.
        try:
            from memory.learning_brain import set_recent_voice_sample
            set_recent_voice_sample(b"".join(self._voice_audio), SEND_SAMPLE_RATE)
        except Exception:
            pass

        print(f"[CHARLIE] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")


        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        loop   = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "recall_memory":
                # Local file search: no network, no second model. Kept out of
                # the executor deliberately — it is a dictionary scan over a few
                # hundred short strings, and a thread hop would cost more than
                # the work itself.
                result = search_memory(args.get("query", ""), limit=8)

            elif name == "undo":
                if str(args.get("action", "")).lower().strip() == "list":
                    items = undo_stack.history()
                    result = ("Things I can undo, most recent first:\n"
                              + "\n".join(f"{i+1}. {t}" for i, t in enumerate(items))
                              ) if items else "I have not changed anything I can undo yet."
                else:
                    result = await loop.run_in_executor(None, undo_stack.undo_last)

            elif name == "screen_process":
                import time as _t_mod
                _now = _t_mod.monotonic()
                _cooldown = 4.0  # seconds — covers echo window after speaking ends
                if self._vision_busy or (_now - self._vision_last_time) < _cooldown:
                    _wait = max(0, _cooldown - (_now - self._vision_last_time))
                    print(f"[Vision] ⏳ Cooldown active ({_wait:.1f}s remaining) — ignoring duplicate call")
                    result = "Vision is still processing the previous request. I will not call this again."
                else:
                    self._vision_busy      = True
                    self._vision_last_time = _now
                    angle     = args.get("angle", "screen").lower()
                    user_text = args.get("text", "What do you see?")
                    if angle == "camera":
                        try:
                            img_b, mime_t = await loop.run_in_executor(None, _capture_camera)
                            self.ui.start_camera_stream()
                            self._vision_cam_active = True
                            print(f"[Vision] 📷 Camera: {len(img_b):,} bytes")
                            _stall = "camera"
                        except Exception as cam_err:
                            print(f"[Vision] ❌ Camera capture failed: {cam_err}")
                            self._vision_busy = False
                            return types.FunctionResponse(
                                id=fc.id, name=name,
                                response={"result": f"Camera could not be opened: {cam_err}. Please ensure webcam is connected and allowed in privacy settings.", "silent": False}
                            )
                    else:
                        img_b, mime_t = await loop.run_in_executor(None, _capture_screen)
                        print(f"[Vision] 🖥️  Screen: {len(img_b):,} bytes")
                        _stall = "screen"
                    self._pending_vision = (img_b, mime_t, user_text, angle)
                    # The image is attached to this same exchange, so there is
                    # nothing to stall for and nothing to announce. Asking for an
                    # acknowledgement here is what produced two spoken answers —
                    # the model filled that turn by answering the question from
                    # imagination, then answered it again once it could see.
                    if _stall == "camera":
                        result = (
                            "[VISION_ACTIVE: CAMERA OBJECT SCAN & OCR]\n"
                            "Camera frame captured and attached to this exchange.\n"
                            "Instructions for Charlie:\n"
                            "1. Identify the exact object, brand, and type shown to the camera.\n"
                            "2. Perform OCR: read and transcribe visible text, labels, ingredients, or model numbers.\n"
                            "3. Explain what this object is used for in everyday life or work.\n"
                            "4. Provide step-by-step guidance on how to properly use or operate it.\n"
                            "5. Respond in the user's spoken language (English, Hindi, Marathi, Bengali, Tamil, Telugu, Gujarati, Punjabi, or any regional/chosen language) with professional clarity.\n"
                            "Reply once directly from what you actually see in the attached camera frame."
                        )
                    else:
                        result = (
                            f"[VISION_ACTIVE] Screen captured and attached to this "
                            f"same exchange. Do not acknowledge and do not answer yet — the image "
                            f"is arriving with this result. Reply once, from what you actually see "
                            f"in it."
                        )

            elif name == "close_camera":
                self.ui.stop_camera_stream()
                result = "Camera closed."

            elif name == "system_status":
                r = await loop.run_in_executor(None, get_system_status)
                result = str(r)

            elif name == "manage_monitor":
                action = args.get("action", "").lower().strip()
                topic  = args.get("topic", "").strip()
                if action == "add" and topic:
                    result = await asyncio.to_thread(add_monitor, topic)
                elif action == "remove" and topic:
                    result = await asyncio.to_thread(remove_monitor, topic)
                elif action == "list":
                    topics = await asyncio.to_thread(list_monitors)
                    result = ("Monitoring: " + ", ".join(topics)) if topics else "No topics are being monitored."
                else:
                    result = "Specify action (add/remove/list) and a topic."

            elif name in ("shutdown_charlie", "shutdown_jarvis"):
                self.ui.write_log("SYS: Shutdown requested.")
                async def _do_shutdown():
                    await self._save_session_summary()
                    if self.session:
                        try:
                            await self.session.send_client_content(
                                turns={"role": "user", "parts": [{"text": "Say a brief natural goodbye to the user."}]},
                                turn_complete=True,
                            )
                        except Exception:
                            pass
                    await asyncio.sleep(1.5)
                    try:
                        from core.runtime_voice_control import unregister_voice_runtime
                        unregister_voice_runtime()
                    except Exception:
                        pass
                    try:
                        from core.tool_gateway import clear_discovery_session
                        clear_discovery_session()
                    except Exception:
                        pass
                    try:
                        self.ui._app.quit()
                    except Exception:
                        import os as _os
                        _os._exit(0)
                asyncio.create_task(_do_shutdown())

            elif name == "discover_tools":
                from core.tool_gateway import discover_candidates, record_telemetry
                intent = args.get("intent", "")
                category = args.get("category")
                sid = str(getattr(self, "_resume_handle", "active_session"))
                try:
                    candidates = discover_candidates(
                        intent=intent,
                        category=category,
                        session_id=sid,
                        action_registry=self._action_registry,
                        plugin_registry=self._plugin_registry,
                    )
                    result = json.dumps({"candidates": candidates}, indent=2)
                except Exception as disc_err:
                    record_telemetry("gateway_failures")
                    cb = getattr(self, "_gateway_circuit_breaker", None)
                    if cb and cb.record_failure(is_infrastructure=True) and not getattr(self, "_pilot_fallback_occurred", False):
                        self._pilot_fallback_occurred = True
                        from core.tool_gateway import clear_discovery_session
                        clear_discovery_session(sid)
                        record_telemetry("discovery_fallback_to_full")
                        self.ui.write_log("SYS: Discovery circuit breaker tripped — falling back to full tool mode.")
                        raise _ReconnectSignal("Gateway circuit breaker tripped")
                    result = f"Error: Tool discovery failed: {disc_err}"

            elif name == "invoke_discovered_tool":
                from core.tool_gateway import execute_discovered_tool, record_telemetry
                target_tool = args.get("tool_name", "")
                args_json = args.get("arguments_json", "{}")
                sid = str(getattr(self, "_resume_handle", "active_session"))
                _ctx = {"player": self.ui, "speak": self.speak,
                        "response": None, "session_memory": None,
                        "action_registry": self._action_registry}
                try:
                    res_str = await loop.run_in_executor(
                        None,
                        lambda: execute_discovered_tool(
                            tool_name=target_tool,
                            arguments_json=args_json,
                            session_id=sid,
                            action_registry=self._action_registry,
                            plugin_registry=self._plugin_registry,
                            ctx=_ctx,
                        )
                    )
                    result = res_str
                except Exception as inv_err:
                    record_telemetry("gateway_failures")
                    cb = getattr(self, "_gateway_circuit_breaker", None)
                    if cb and cb.record_failure(is_infrastructure=True) and not getattr(self, "_pilot_fallback_occurred", False):
                        self._pilot_fallback_occurred = True
                        record_telemetry("pilot_fallback_to_full")
                        self.ui.write_log("SYS: Invocation circuit breaker tripped — falling back to full tool mode.")
                        raise _ReconnectSignal("Gateway circuit breaker tripped")
                    result = f"Error: Discovered tool execution failed: {inv_err}"

            elif self._action_registry.has(name):
                # file_processor: fall back to the currently-uploaded file when none is given
                if name == "file_processor" and not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                _ctx = {"player": self.ui, "speak": self.speak,
                        "response": None, "session_memory": None,
                        "action_registry": self._action_registry}
                self._tool_progress_active = True
                try:
                    r = await loop.run_in_executor(None, lambda: self._action_registry.run(name, args, _ctx))
                finally:
                    self._tool_progress_active = False
                result = r or "Done."
                # web_search: mirror results to the on-screen content panel
                if (name == "web_search" and r
                        and not r.startswith("No results")
                        and not r.startswith("Search failed")):
                    _mode  = args.get("mode", "search")
                    _query = args.get("query") or ", ".join(args.get("items", []))
                    _label = f"{_mode.upper()} — {_query[:38]}" if _query else _mode.upper()
                    self.ui.show_content(_label, r)
                if (name == "personal_hub" and r and args.get("action") in {
                        "daily_plan", "goal_list", "task_list", "event_list",
                        "learning_list", "meeting_list", "privacy_summary"}):
                    self.ui.show_content("PERSONAL HUB", str(r))

            else:
                if self._plugin_registry.has(name):
                    self._tool_progress_active = True
                    try:
                        r = await loop.run_in_executor(
                            None,
                            lambda: self._plugin_registry.run(name, args, player=self.ui, session_memory=None)
                        )
                    finally:
                        self._tool_progress_active = False
                    result = r or "Done."
                else:
                    result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        # A durable action trail lets the user review what CHARLIE actually did
        # after a long voice task. Parameters are privacy-redacted by the store;
        # audit logging must never make an otherwise successful action fail.
        result_text = str(result).lower()
        history_state = ("failed" if (result_text.startswith(("tool '", "unknown tool", "could not", "access denied", "error"))
                                       or " failed" in result_text[:120]) else "completed")
        record_task_history(name, args, result, state=history_state)

        if name == "action_history" and result:
            self.ui.show_content("CHARLIE ACTION HISTORY", str(result))

        print(f"[CHARLIE] 📤 {name} → {str(result)[:80]}")

        # A tool that declared itself NON_BLOCKING also says when its answer may
        # re-enter the conversation. Without this the model finishes whatever it
        # was saying and then reads the result out on top of it — which, for
        # something like a phone call already ringing, is exactly the noise the
        # non-blocking call was meant to avoid. Tools that declared nothing get
        # the API default and behave as they always have.
        _sched = (self._action_registry.scheduling(name)
                  or self._plugin_registry.scheduling(name))
        _extra = {"scheduling": _sched} if _sched else {}
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result},
            **_extra
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            # Gemini 3.x Live rejects the old realtime_input.media_chunks field
            # (what `media=...` maps to) and closes the socket with a 1007. Send
            # mic / phone PCM through the new `audio` field instead. Queue items
            # are {"data": <bytes>, "mime_type": <str>} from _listen_audio and
            # the phone relay.
            mime_type = str(msg.get("mime_type") or "").strip()
            # Older producers used bare `audio/pcm`. Treat that as our desktop
            # capture format so every raw PCM block tells Live its sample rate.
            if not mime_type or mime_type.lower() == "audio/pcm":
                mime_type = INPUT_AUDIO_MIME
            await self.session.send_realtime_input(
                audio=types.Blob(
                    data=msg["data"],
                    mime_type=mime_type,
                )
            )

    def _stop_mic_worker(self) -> None:
        """Cleanly stop the dedicated microphone DSP worker thread."""
        stop_event = getattr(self, "_mic_worker_stop", None)
        if stop_event:
            stop_event.set()
        q = getattr(self, "_mic_raw_queue", None)
        if q:
            try:
                q.put_nowait(None)
            except Exception:
                pass
        worker = getattr(self, "_mic_worker_thread", None)
        if worker and worker.is_alive():
            if threading.current_thread() != worker:
                worker.join(timeout=0.5)
        self._mic_worker_thread = None
        self._mic_worker_stop = None
        self._mic_raw_queue = None

    def _mic_dsp_worker(self, loop: asyncio.AbstractEventLoop) -> None:
        """Dedicated background worker thread for offloaded mic DSP, AGC, and classification."""
        stop_event = self._mic_worker_stop
        q = self._mic_raw_queue
        while stop_event and not stop_event.is_set():
            try:
                if q is None:
                    break
                indata = q.get(timeout=0.2)
            except (_queue.Empty, AttributeError):
                continue
            if indata is None:
                break
            try:
                self._process_mic_chunk(indata, loop)
            except Exception:
                pass

    def _process_mic_chunk(self, indata: np.ndarray, loop: asyncio.AbstractEventLoop) -> None:
        """Process a single raw microphone chunk off the PortAudio callback thread."""
        with self._speaking_lock:
            charlie_speaking = self._is_speaking

        # ── Barge-in ─────────────────────────────────────────────────────
        # While CHARLIE talks, inspect the microphone locally and forward
        # only speech that differs from its own playback. This keeps echo
        # out of the session while allowing a person to interrupt naturally.
        if charlie_speaking:
            try:
                level = _pcm_level(indata)
                user_speech = self._echo.is_user_speech(
                    indata, SEND_SAMPLE_RATE, level
                )
                if user_speech:
                    # Keep only evidence that was already distinct from the
                    # playback echo. Once the run is confirmed, forwarding
                    # this short pre-roll lets commands such as "stop" retain
                    # their first word instead of beginning mid-utterance.
                    block_bytes = indata.tobytes()
                    self._voice_audio.append(block_bytes)
                    self._barge_in_buffer.append(block_bytes)
                    max_blocks = max(self._echo.required_blocks, 12)
                    if len(self._barge_in_buffer) > max_blocks:
                        del self._barge_in_buffer[:-max_blocks]
                    if self._echo.speech_blocks >= self._echo.required_blocks:
                        for block in self._barge_in_buffer:
                            self._queue_realtime_audio(loop, block)
                        self._barge_in_buffer.clear()
                        self._last_user_speech = time.monotonic()
                        if not self._barge_in_pending:
                            self._barge_in_pending = True
                            self._request_interrupt_from_audio_thread()
                else:
                    self._barge_in_buffer.clear()
            except Exception:
                pass          # audio callback faults must never kill the mic
            # Do not forward ordinary speaker echo while CHARLIE talks.
            return

        # ── Echo tail ────────────────────────────────────────────────────
        # The speaking flag has dropped but the speakers have not finished.
        # Sending this to the model is how an assistant hears itself, decides
        # it was addressed, and answers its own last sentence. The microphone
        # stays OPEN — the guard only drops blocks that are our own voice, so
        # replying the instant it stops still works.
        if self._tail_active():
            try:
                if not self._echo.is_user_speech(
                        indata, SEND_SAMPLE_RATE, _pcm_level(indata)):
                    return
                self._tail_until = 0.0      # a real voice ends the tail early
            except Exception:
                return
        elif self._echo._hist:
            self._echo.reset()

        # ── Push-to-talk ─────────────────────────────────────────────────
        # When it is on the microphone is closed by default and the chord
        # opens it, which is the whole point: nothing leaves the machine
        # unless you are holding the key.
        if self._ptt_enabled and not self._ptt_held:
            return

        if not self.ui.muted and not self.ui.chat_mode and not self._phone_active:
            # Software AGC boost: lift quiet voices and faint accents into clear range.
            # Adaptive target: boost to ~400 RMS for quiet input, soft-limit louds.
            # Noise gate: drop near-silence frames (keyboard, HVAC) that fragment utterances.
            audio_np = indata.astype(np.float32)
            rms = float(np.sqrt(np.mean(audio_np ** 2)))

            # Adaptive noise floor tracking
            self._noise_floor = 0.98 * self._noise_floor + 0.02 * min(rms, 60.0)
            gate_threshold = max(35.0, self._noise_floor * 1.5)

            if rms < gate_threshold:
                if self._speech_hangover > 0:
                    self._speech_hangover -= 1
                    processed = audio_np.astype(np.int16)
                else:
                    # Drop pure ambient noise / silence completely. Do NOT stream to Gemini.
                    try:
                        self.ui.set_audio_level(0)
                    except Exception:
                        pass
                    return
            else:
                # Speech detected: reset hangover counter (~8 frames = ~250ms)
                self._speech_hangover = 8
                if 60.0 <= rms < 300.0:
                    boost = min(1.8, 300.0 / max(rms, 1.0))
                    audio_np = np.clip(audio_np * boost, -32767.0, 32767.0)
                elif rms > 6000.0:
                    audio_np = np.clip(audio_np * 0.75, -32767.0, 32767.0)
                processed = audio_np.astype(np.int16)

            # Feed to background noise classifier & real-time acoustic emotion detector
            try:
                get_noise_classifier().feed(indata)
            except Exception:
                pass
            try:
                from engine.voice.emotion_detector import get_emotion_detector
                get_emotion_detector().feed(indata)
            except Exception:
                pass

            data = processed.tobytes()
            self._voice_audio.append(data)
            self._queue_realtime_audio(loop, data)
            # Feed the live mic level to the HUD so the waveform reacts to
            # the user's actual voice while listening. Purely cosmetic — any
            # failure here must never disturb the mic.
            try:
                self.ui.set_audio_level(_pcm_level(processed))
            except Exception:
                pass

    async def _listen_audio(self):
        print("[CHARLIE] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        # Stop any existing worker to prevent duplicates on reconnect
        self._stop_mic_worker()
        self._mic_raw_queue = _queue.Queue(maxsize=64)
        self._mic_worker_stop = threading.Event()
        self._mic_dropped_frames = 0
        self._mic_last_drop_log = 0.0

        self._mic_worker_thread = threading.Thread(
            target=self._mic_dsp_worker,
            args=(loop,),
            daemon=True,
            name="charlie-mic-dsp",
        )
        self._mic_worker_thread.start()

        def callback(indata, frames, time_info, status):
            # ── Wake-word gate ───────────────────────────────────────────────
            # While asleep, the mic audio NEVER goes to Gemini (nothing is
            # streamed, so CHARLIE can't respond to speech not addressed to it and
            # nothing leaves the machine). Frames are instead handed to the local
            # detector, which runs its model in ITS OWN thread — the cost here is
            # only a queue push, so the audio path is never slowed. When wake word
            # is off (default) or we're awake, this is a single boolean check.
            if self._wake_enabled and not self._awake:
                det = self._wake_detector
                if det is not None:
                    det.feed(indata)
                return

            # These are privacy controls even while CHARLIE is speaking. A held
            # push-to-talk chord is also an intentional barge-in signal.
            if self._ptt_enabled and not self._ptt_held:
                return
            if self.ui.muted or self.ui.chat_mode or self._phone_active:
                return

            q = self._mic_raw_queue
            if q is None:
                return

            raw = indata.copy()
            try:
                q.put_nowait(raw)
            except _queue.Full:
                try:
                    # Drop stale audio to keep voice conversation latency low
                    _ = q.get_nowait()
                    q.put_nowait(raw)
                except Exception:
                    pass
                self._mic_dropped_frames += 1
                now = time.monotonic()
                if now - self._mic_last_drop_log > 5.0:
                    print(f"[CHARLIE] ⚠️ Mic queue full — dropped {self._mic_dropped_frames} frames")
                    self._mic_last_drop_log = now

        try:
            def _open_mic(dev):
                return sd.InputStream(
                    samplerate=SEND_SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype="int16",
                    blocksize=CHUNK_SIZE,
                    device=dev,
                    callback=callback,
                )

            # Which microphone. resolve() returns None for "system default" and
            # for a saved device that is no longer present — so a headset
            # unplugged since the last run falls back to the built-in mic
            # instead of raising on startup and taking the session with it.
            _mic_name = get_input_device()
            _mic_dev  = audio_devices.resolve(_mic_name, "input")
            if _mic_dev is not None:
                print(f"[CHARLIE] 🎤 Input device: {_mic_name}")
            try:
                _mic_stream = _open_mic(_mic_dev)
            except Exception as _e:
                # A device the picker listed but the driver will not open right
                # now — exclusive mode, a webcam already in use, a virtual mic
                # whose source went away. Chosen hardware failing must never
                # mean the assistant cannot hear at all.
                if _mic_dev is None:
                    raise
                print(f"[CHARLIE] ⚠️  Mic '{_mic_name}' failed: {_e} — using default")
                self.ui.write_log(
                    f"SYS: Microphone '{_mic_name}' unavailable — using system default."
                )
                _mic_stream = _open_mic(None)

            with _mic_stream:
                print("[CHARLIE] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[CHARLIE] ❌ Mic: {e}")
            raise
        finally:
            self._stop_mic_worker()

    async def _flush_pending_vision(self) -> bool:
        """Send a captured frame immediately after its tool response.

        The frame is already in hand by the time `screen_process` returns — the
        capture happened inside the tool call. The old flow still made the model
        speak a turn first and only injected the image on that turn's
        turn_complete, which cost a whole extra round trip AND produced two
        spoken answers: one improvised without the picture, then the real one.
        Sending it here means the model has the tool result and the image before
        it generates anything, so the user gets one answer, sooner.
        """
        if not (self._pending_vision and self.session):
            return False

        import base64 as _b64
        img_b, mime_t, question, angle = self._pending_vision
        self._pending_vision = None
        b64 = _b64.b64encode(img_b).decode("ascii")
        print(f"[Vision] 📤 {len(img_b):,} bytes (angle={angle}) → main session")

        # Label the source. Without it the image arrives carrying nothing but
        # the user's own sentence, and a screenshot of this app — which has a
        # face in the middle of it — got read as a photo of the user. What the
        # label *means* is explained once, in the generated [SELF] block.
        src = ("[IMAGE SOURCE: WEBCAM]" if angle == "camera"
               else "[IMAGE SOURCE: SCREEN CAPTURE]")
        await self.session.send_client_content(
            turns={"role": "user", "parts": [
                {"inline_data": {"mime_type": mime_t, "data": b64}},
                {"text": f"{src}\n\n{question}"},
            ]},
            turn_complete=True,
        )

        if self._vision_cam_active:
            # Camera: stay busy until CHARLIE has finished speaking the answer,
            # then close the preview.
            self._vision_cam_active    = False
            self._vision_close_pending = True
        else:
            self._vision_busy = False
        return True

    async def _receive_audio(self):
        print("[CHARLIE] 👂 Recv started")
        out_buf, in_buf = [], []
        turn_audio_bytes = 0

        try:
            while True:
                async for response in self.session.receive():

                    # ── Session resumption ───────────────────────────────────
                    # The server sends this periodically. `resumable` goes false
                    # while a turn is mid-flight — replaying a handle from that
                    # moment is what the flag exists to prevent — so only
                    # resumable handles are kept. This is three lines and it is
                    # the entire fix for "every reconnect forgets everything".
                    _sru = getattr(response, "session_resumption_update", None)
                    if _sru is not None:
                        if getattr(_sru, "resumable", False) and getattr(_sru, "new_handle", None):
                            if self._resume_handle is None:
                                print("[CHARLIE] 🔗 Session resumption armed")
                            self._resume_handle = _sru.new_handle

                    _audio_data = getattr(response, "data", None)
                    if not _audio_data and getattr(response, "server_content", None) and getattr(response.server_content, "model_turn", None):
                        parts = getattr(response.server_content.model_turn, "parts", None) or []
                        _buf = bytearray()
                        for _p in parts:
                            _idata = getattr(_p, "inline_data", None)
                            if _idata and getattr(_idata, "data", None):
                                _raw = _idata.data
                                if isinstance(_raw, bytes):
                                    _buf.extend(_raw)
                                elif isinstance(_raw, str):
                                    import base64
                                    try:
                                        _buf.extend(base64.b64decode(_raw))
                                    except Exception:
                                        pass
                        if _buf:
                            _audio_data = bytes(_buf)

                    if _audio_data:
                        if self._interrupted or getattr(self, "_foreign_hallucination_blocked", False):
                            pass  # discard: interrupted or blocked foreign speech
                        else:
                            turn_audio_bytes += len(_audio_data)
                            if self._turn_done_event and self._turn_done_event.is_set():
                                self._turn_done_event.clear()
                            # Split into ~50 ms chunks so interrupt() stops audio within 50 ms
                            # (24000 Hz × 2 bytes/sample × 0.05 s = 2400 bytes per slice)
                            _SLICE = 2400
                            for _i in range(0, len(_audio_data), _SLICE):
                                self.audio_in_queue.put_nowait(_audio_data[_i : _i + _SLICE])

                    if response.server_content:
                        sc = response.server_content

                        # Live VAD accepted user speech during a reply. The
                        # server has stopped generating, but its already-buffered
                        # audio is still local, so discard it before it talks over
                        # the person who just started speaking.
                        if getattr(sc, "interrupted", False) and not self._interrupted:
                            self.interrupt()

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if self._has_unauthorized_foreign(txt):
                                print(f"[CHARLIE] 🛑 Intercepted unauthorized foreign speech: '{txt}'")
                                self._foreign_hallucination_blocked = True
                                self.interrupt()
                                out_buf.clear()
                                turn_audio_bytes = 0
                            elif not getattr(self, "_foreign_hallucination_blocked", False):
                                if txt and not _is_repeat_chunk(txt, out_buf):
                                    out_buf.append(txt)
                                    self._visemes.feed_text(txt)
                                    self.ui.classify_and_set_emotion(" ".join(out_buf)[-800:])

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if self._has_unauthorized_foreign(txt):
                                print(f"[CHARLIE] 🛑 Filtered foreign hallucination in user transcription: '{txt}'")
                                self._foreign_hallucination_blocked = True
                                self.interrupt()
                                txt = ""
                            if txt:
                                in_buf.append(txt)
                                self._last_user_speech = time.monotonic()

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            was_foreign_blocked = getattr(self, "_foreign_hallucination_blocked", False)

                            # If this turn_complete ends an interrupted response (and wasn't a blocked foreign hallucination)
                            if self._interrupted and not was_foreign_blocked:
                                self._interrupted = False
                                in_buf  = []
                                out_buf = []
                                turn_audio_bytes = 0
                                self._voice_audio.clear()
                                self._visemes.reset()
                                continue

                            full_in = " ".join(in_buf).strip()
                            # 2-way visual sync: if Gemini Live omitted input_transcription, transcribe recorded voice audio
                            if not full_in and self._voice_audio:
                                try:
                                    _v_raw = b"".join(self._voice_audio)
                                    # Require at least 0.5s of audio (16,000 bytes at 16kHz 16-bit mono = 32,000 B/s)
                                    if len(_v_raw) >= 16000:
                                        _v_arr = np.frombuffer(_v_raw, dtype=np.int16).astype(np.float32) / 32768.0
                                        # Strict audio energy check: discard ambient silence/hum
                                        _rms = float(np.sqrt(np.mean(_v_arr ** 2)))
                                        if _rms >= 0.015:
                                            stt = self._get_fallback_stt()
                                            if stt:
                                                _fallback_txt = await asyncio.to_thread(stt.transcribe, _v_arr)
                                                if _fallback_txt:
                                                    from engine.voice.stt import TranscriptNormalizer
                                                    _fallback_txt = TranscriptNormalizer.normalize(_fallback_txt)
                                                    from core.stt import is_stt_hallucination
                                                    if not is_stt_hallucination(_fallback_txt) and not self._has_unauthorized_foreign(_fallback_txt):
                                                        full_in = _fallback_txt
                                except Exception as _stt_err:
                                    print(f"[STT] Fallback voice transcribe error: {_stt_err}")

                            if full_in:
                                self._last_out_logged = ""   # new exchange
                                self.ui.write_log(f"You: {full_in}")
                                self._session_log.append(f"User: {full_in}")
                                await asyncio.to_thread(record_conversation_turn, "User", full_in)
                                if self._dashboard:
                                    asyncio.create_task(self._dashboard.broadcast({
                                        "type": "log", "speaker": "user",
                                        "text": full_in,
                                        "ts": datetime.now().isoformat(),
                                    }))

                                # ── Real-time acoustic emotion & empathetic avatar ──
                                try:
                                    from engine.voice.emotion_detector import get_emotion_detector
                                    from core.digital_human import Emotion
                                    u_state = get_emotion_detector().get_state()
                                    _u_emo = u_state.get("emotion")
                                    _MAP = {
                                        "calm": Emotion.NEUTRAL,
                                        "stressed": Emotion.CONCERNED,
                                        "tired": Emotion.TIRED,
                                        "frustrated": Emotion.APOLOGETIC,
                                        "energetic": Emotion.HAPPY,
                                    }
                                    if _u_emo in _MAP:
                                        self.ui.set_emotion(_MAP[_u_emo], intensity=0.25)
                                except Exception:
                                    pass

                                # ── Voice Profile speaker identification ───────
                                if self._voice_audio:
                                    try:
                                        _v_raw = b"".join(self._voice_audio)
                                        if len(_v_raw) >= 4000:
                                            _v_arr = np.frombuffer(_v_raw, dtype=np.int16)
                                            _match = get_voice_profile_manager().identify(_v_arr)
                                            if _match and _match.get("user_name"):
                                                _uid = _match["user_name"]
                                                if not getattr(self, "_recognized_user", None):
                                                    self._recognized_user = _uid
                                                    self.ui.write_log(f"SYS: Voice recognized as {_uid} ({int(_match['score']*100)}% match)")
                                    except Exception:
                                        pass

                                # ── Language preference & switch detection ──────
                                if self._lang_mgr is not None:
                                    _lm = self._lang_mgr
                                    current_lang = getattr(self, "_current_chat_lang", "en")

                                    # 1. Check for explicit language switch command
                                    new_lang = _lm.check_switch(full_in)
                                    if new_lang and new_lang != current_lang:
                                        self._current_chat_lang = new_lang
                                        _lm._lang = new_lang
                                        from engine.voice.user_greeter_clean import build_language_confirm
                                        _conf_msg = build_language_confirm(new_lang, self._asst_name)
                                        _switch_note = (
                                            f"[LANGUAGE SWITCH CONFIRMED]: Speak this confirmation verbatim: '{_conf_msg}'. "
                                            f"From now on, speak ONLY in '{new_lang}'. "
                                            f"DO NOT change the language in between unless the user explicitly asks to change it."
                                        )
                                        try:
                                            await self.session.send_client_content(
                                                turns={"role": "user", "parts": [{"text": _switch_note}]},
                                                turn_complete=True,
                                            )
                                        except Exception:
                                            pass
                                    elif current_lang == "en":
                                        from engine.voice.user_greeter_clean import detect_hindi_speech
                                        if detect_hindi_speech(full_in):
                                            # User spoke in Hindi: transition into Hindi and LOCK it!
                                            self._current_chat_lang = "hi"
                                            _lm._lang = "hi"
                                            _hindi_note = (
                                                "[LANGUAGE DIRECTIVE — SWITCH TO HINDI]: The user has spoken in Hindi. "
                                                "You must now respond ONLY in natural conversational Hindi or Hinglish. "
                                                "Keep speaking in Hindi for all future responses. "
                                                "DO NOT change or switch to Tamil, Telugu, English, or any other language "
                                                "in between unless the user explicitly asks to change it."
                                            )
                                            try:
                                                await self.session.send_client_content(
                                                    turns={"role": "user", "parts": [{"text": _hindi_note}]},
                                                    turn_complete=False,
                                                )
                                            except Exception:
                                                pass
                                # ── Cultural / Religious greeting detection ─────
                                if self._cultural_mgr is not None and full_in:
                                    _cult_reply = self._cultural_mgr.process(
                                        user_id        = self._user_id,
                                        text           = full_in,
                                        user_name      = self._user_name_display,
                                        assistant_name = self._asst_name,
                                    )
                                    if _cult_reply:
                                        # Inject a system directive so Gemini speaks the reply verbatim
                                        _cult_note = (
                                            f"[CULTURAL GREETING DETECTED — respond with this EXACT text, "
                                            f"naturally and warmly, do not add or change anything]: "
                                            f"{_cult_reply}"
                                        )
                                        try:
                                            await self.session.send_client_content(
                                                turns={"role": "user", "parts": [{"text": _cult_note}]},
                                                turn_complete=True,
                                            )
                                        except Exception:
                                            pass
                                # ───────────────────────────────────────────────

                            in_buf = []
                            self._voice_audio.clear()

                            full_out = " ".join(out_buf).strip()
                            if was_foreign_blocked or self._has_unauthorized_foreign(full_out):
                                current_lang = getattr(self._lang_mgr, "lang", "en") if self._lang_mgr else "en"
                                if current_lang in ("hi", "hindi", "hinglish"):
                                    full_out = HINDI_UNCLEAR_FALLBACK
                                else:
                                    full_out = "I didn't catch that clearly. Could you please repeat that?"
                                self._foreign_hallucination_blocked = False
                                self._interrupted = False
                                self._last_out_logged = full_out
                                self.ui.write_log(f"{self._asst_name}: {full_out}")
                                self._session_log.append(f"{self._asst_name}: {full_out}")
                                await asyncio.to_thread(
                                    record_conversation_turn, self._asst_name, full_out)
                                if self._dashboard:
                                    asyncio.create_task(self._dashboard.broadcast({
                                        "type": "log", "speaker": "charlie",
                                        "text": full_out,
                                        "ts": datetime.now().isoformat(),
                                    }))
                                self.speak(full_out)
                                _corr_note = (
                                    "[SILENT SYSTEM DIRECTIVE — CRITICAL] "
                                    "A foreign language output was intercepted and blocked. "
                                    "The user speaks Hindi and English. If user speech is ever unclear "
                                    "or words cannot be understood, your ONLY response must be: "
                                    "'Mujhe aapki baat samajh nahi aayi barabar, aap phir se bol sakte ho taki mai apki madad kar saku?' "
                                    "Never speak Chinese, Japanese, or any other foreign language."
                                )
                                try:
                                    await self.session.send_client_content(
                                        turns={"role": "user", "parts": [{"text": _corr_note}]},
                                        turn_complete=False,
                                    )
                                except Exception:
                                    pass
                            else:
                                # Second line of defence: even if a repeat slips
                                # into a *fresh* buffer after a flush, never log the
                                # same answer (or a tail of it) twice in a row.
                                if full_out and len(full_out) >= _REPEAT_MIN and self._last_out_logged:
                                    if full_out in self._last_out_logged:
                                        full_out = ""
                                if full_out:
                                    self._last_out_logged = full_out
                                    self.ui.write_log(f"{self._asst_name}: {full_out}")
                                    self._session_log.append(f"{self._asst_name}: {full_out}")
                                    await asyncio.to_thread(
                                        record_conversation_turn, self._asst_name, full_out)
                                    if self._dashboard:
                                        asyncio.create_task(self._dashboard.broadcast({
                                            "type": "log", "speaker": "charlie",
                                            "text": full_out,
                                            "ts": datetime.now().isoformat(),
                                        }))
                                    if turn_audio_bytes == 0 and not self._interrupted:
                                        print(f"[CHARLIE] ⚠️ Live session returned text with no audio stream — vocalizing via TTS")
                                        self.speak(full_out)
                            out_buf = []
                            turn_audio_bytes = 0

                            if self._vision_close_pending:
                                # This turn_complete IS the vision answer — close camera + release busy flag
                                self._vision_close_pending = False
                                self._vision_busy = False
                                async def _cam_close():
                                    await asyncio.sleep(2.0)
                                    self.ui.stop_camera_stream()
                                asyncio.create_task(_cam_close())

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[CHARLIE] 📞 {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )
                        await self._flush_pending_vision()
        except Exception as e:
            print(f"[CHARLIE] ❌ Recv: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[CHARLIE] 🔊 Play started")

        _spk_name = get_output_device()
        _spk_dev  = audio_devices.resolve(_spk_name, "output")
        if _spk_dev is not None:
            print(f"[CHARLIE] 🔊 Output device: {_spk_name}")

        def _open_spk(dev):
            st = sd.RawOutputStream(
                samplerate=RECEIVE_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                device=dev,
            )
            st.start()
            return st

        try:
            stream = _open_spk(_spk_dev)
        except Exception as _e:
            print(f"[CHARLIE] ⚠️  Output device '{_spk_name}' ({_spk_dev}) failed: {_e} — using fallback")
            self.ui.write_log(f"SYS: Speaker '{_spk_name}' unavailable — using fallback.")
            try:
                stream = _open_spk(None)
            except Exception as _e2:
                stream = None
                for d_idx in range(len(sd.query_devices())):
                    if audio_devices._usable(d_idx, "output") and audio_devices._transport_works(d_idx, "output", ("fallback", "output")):
                        try:
                            stream = _open_spk(d_idx)
                            print(f"[CHARLIE] 🔊 Fallback output device: {d_idx}")
                            break
                        except Exception:
                            pass
                if stream is None:
                    raise _e2

        # Ask the device how far behind the speakers actually are, rather than
        # assuming. This is what the echo tail is sized from, so a machine with a
        # large audio buffer gets a correspondingly longer guard — and one with a
        # tiny buffer is not penalised with a delay it does not need.
        try:
            lat = float(getattr(stream, "latency", 0.0) or 0.0)
            if 0.0 < lat < 1.0:
                self._out_latency = lat
            print(f"[CHARLIE] 🔊 Output latency {self._out_latency*1000:.0f} ms "
                  f"→ echo tail {(self._out_latency + _TAIL_MARGIN)*1000:.0f} ms")
        except Exception:
            pass

        _recovery_boost = 0
        self._playback_underruns = 0

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    with self._speaking_lock:
                        was_speaking = self._is_speaking
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    elif was_speaking and not self._interrupted:
                        # Queue starved mid-utterance: record underrun and arm adaptive recovery
                        self._playback_underruns += 1
                        _recovery_boost = 2
                    continue

                with self._speaking_lock:
                    starting_turn = not self._is_speaking
                batch = bytearray(chunk)

                if starting_turn:
                    try:
                        self.ui.trigger_nod()
                    except Exception:
                        pass
                    # Adaptive jitter buffer: 50 ms nominal (starts immediately if chunk ready);
                    # temporary recovery buffer (~100 ms) only if underrun occurred
                    target_prebuffer = 4800 if _recovery_boost > 0 else 2400
                    if _recovery_boost > 0:
                        _recovery_boost -= 1
                    deadline = asyncio.get_running_loop().time() + 0.04
                    while len(batch) < target_prebuffer:
                        remaining = deadline - asyncio.get_running_loop().time()
                        if remaining <= 0:
                            break
                        try:
                            batch.extend(await asyncio.wait_for(
                                self.audio_in_queue.get(), timeout=remaining))
                        except asyncio.TimeoutError:
                            break

                self.set_speaking(True)

                # Cap write batch at ~50 ms (2400 bytes at 24 kHz 16-bit mono)
                # Eliminates sluggish 200ms batch delay and ensures interrupt() stops audio within ~50ms
                while len(batch) < 2400:
                    try:
                        batch.extend(self.audio_in_queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break

                if len(batch) % 2 != 0:
                    batch = batch[:len(batch) - 1]
                if not batch:
                    continue

                # Drive the HUD waveform and the avatar's mouth from CHARLIE's
                # own voice. The batch is up to 200 ms long, so we hand over a
                # *schedule* of 20 ms viseme frames instead of a single averaged
                # level and let the HUD play it out in step with the audio.
                try:
                    pcm = np.frombuffer(bytes(batch), dtype=np.int16)
                    hop = _VIS_HOP / RECEIVE_SAMPLE_RATE
                    frames = _pcm_visemes(pcm, sr=RECEIVE_SAMPLE_RATE)
                    now = time.time()
                    horizon = self._out_latency + _CURSOR_SLACK
                    if not (now <= self._play_cursor <= now + horizon):
                        self._play_cursor = now + _FIRST_SOUND
                    at = self._play_cursor
                    self._play_cursor += pcm.size / RECEIVE_SAMPLE_RATE
                    if frames:
                        frames = self._visemes.frames(frames, hop)
                        self.ui.push_visemes(frames, hop, at)
                        self._out_level = max(f[0] for f in frames)
                        self._echo.note_output(pcm, RECEIVE_SAMPLE_RATE,
                                               self._out_level)
                    else:
                        lvl = _pcm_level(pcm)
                        self.ui.set_audio_level(lvl)
                        self._out_level = lvl
                        self._echo.note_output(pcm, RECEIVE_SAMPLE_RATE, lvl)
                except Exception:
                    pass

                try:
                    await asyncio.to_thread(stream.write, bytes(batch))
                except (RuntimeError, asyncio.CancelledError):
                    break   # executor shutting down — exit cleanly
                except Exception as write_err:
                    print(f"[CHARLIE] ⚠️ Audio write error: {write_err}")
        except Exception as e:
            print(f"[CHARLIE] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    # ── Morning briefing ────────────────────────────────────────────────────────

    async def _send_greeting(self) -> None:
        """
        Personalised session greeting:
          - Time-appropriate salutation (Good morning / afternoon / evening)
          - Uses the user's real name from config / profile
          - If language preference unknown → asks once
          - Remembers returning voices and mentions last topic
        """
        await asyncio.sleep(0.5)          # let session fully open
        if not self.session:
            return

        try:
            _cfg       = json.loads(open(API_CONFIG_PATH, encoding="utf-8").read())
            _asst_name = (_cfg.get("assistant_name") or "Charlie").strip()
            _user_name = (
                active_profile().get("name") or _cfg.get("user_name") or ""
            ).strip()
        except Exception:
            _asst_name = "Charlie"
            _user_name = ""

        _user_id = (_user_name.lower().replace(" ", "_")) or "default_user"

        # Store user identity on instance for use in receive loop
        self._user_id           = _user_id
        self._user_name_display = _user_name

        # ── Init cultural greeting manager for this session ───────────────────
        reset_cultural_greeting_manager()
        self._cultural_mgr = get_cultural_greeting_manager()

        # Try to recall last session topic for the 'returning voice' line
        last_topic = ""
        try:
            last = await asyncio.to_thread(pop_last_session)
            if last:
                _sum = last.get("summary", "") or ""
                last_topic = _sum[:60].split(".")[0].strip()
        except Exception:
            pass

        greeting_text, lang_mgr = build_session_greeting(
            user_name      = _user_name,
            user_id        = _user_id,
            assistant_name = _asst_name,
            last_topic     = last_topic,
        )

        # Store lang_mgr on the instance so the receive loop can use it
        self._lang_mgr = lang_mgr
        self._current_chat_lang = "en"
        self._awaiting_lang_pref = False

        self.ui.write_log(f"SYS: Greeting user '{_user_name or 'unknown'}'.")

        # Send as a system instruction so Gemini speaks it verbatim
        greeting_instruction = (
            f"[START-OF-SESSION GREETING — speak this EXACTLY in English, do not add or remove anything]\n"
            f"{greeting_text}\n\n"
            f"[SESSION LANGUAGE BASELINE]: The conversation starts in English. "
            f"If the user speaks in Hindi, switch to Hindi and maintain Hindi. "
            f"NEVER switch to Tamil, Telugu, or any other language unless explicitly requested by the user."
        )
        try:
            await self.session.send_client_content(
                turns={"role": "user", "parts": [{"text": greeting_instruction}]},
                turn_complete=True,
            )
        except Exception as exc:
            print(f"[Greeting] Could not send greeting: {exc}")

    async def _send_startup_briefing(self) -> None:
        """
        Two-phase briefing optimized for speed:
          Phase 1 — instant greeting (no tools) → speech starts in <1s
          Phase 2 — news pre-fetched in a background thread while Phase 1 plays,
                    delivered as ready text (no Gemini tool-call round-trip) and
                    shown on the UI content panel. Waits for turn_complete event
                    instead of a fixed sleep so there is no unnecessary gap.
        """
        memory   = load_memory()
        identity = memory.get("identity", {})

        def _val(k: str) -> str:
            e = identity.get(k, {})
            return (e.get("value", "") if isinstance(e, dict) else str(e)).strip()

        lang = _val("language")
        name = _val("name")
        time_str = datetime.now().strftime("%H:%M")

        # Start fetching news immediately — runs in parallel while phase 1 plays
        loop = asyncio.get_event_loop()
        news_future = loop.run_in_executor(None, _fetch_news_sync, "top world news today")

        await asyncio.sleep(0.3)
        if not self.session:
            return

        # ── Phase 1: instant greeting ─────────────────────────────────────────
        # The briefing fires before the user has said anything, so the
        # remembered language is the only signal there is. It is a starting
        # point, not a setting: the moment they reply, their language wins.
        lang_clause = (f" Speak this greeting in {lang}, then follow the "
                       f"user's own language from their first reply onward."
                       if lang else "")
        name_clause = f" Address the user as {name}." if name else ""

        # Inject last session context if available — pop removes it so it's never repeated
        last = await asyncio.to_thread(pop_last_session)
        session_clause = ""
        if last:
            try:
                _delta = (datetime.now() - datetime.strptime(last["date"], "%Y-%m-%d")).days
                _when  = "earlier today" if _delta == 0 else ("yesterday" if _delta == 1 else f"{_delta} days ago")
            except Exception:
                _when = "last time"
            session_clause = (
                f" Also briefly and naturally mention that {_when}: {last['summary']}"
            )

        daily_clause = ""
        try:
            from memory.learning_brain import daily_intelligence, load_brain
            if load_brain()["settings"].get("daily_intelligence", True):
                snapshot = await asyncio.to_thread(daily_intelligence, "morning")
                daily_clause = (
                    " Quietly use this private daily snapshot to mention only the single most useful "
                    f"priority or follow-up: {json.dumps(snapshot, ensure_ascii=False)[:5000]}"
                )
        except Exception as exc:
            print(f"[DailyIntelligence] {exc}")

        p1 = (
            f"Greet the user warmly, mention it is {time_str}, and say you are fetching today's news now.{session_clause} "
            f"Keep it to 2 short sentences max. Do not call any tools.{lang_clause}{name_clause}{daily_clause}"
        )

        # Clear the turn-done event so we can wait for Phase 1 to finish
        if self._turn_done_event:
            self._turn_done_event.clear()

        await self.session.send_client_content(
            turns={"role": "user", "parts": [{"text": p1}]},
            turn_complete=True,
        )
        print("[CHARLIE] Briefing phase 1 (greeting) sent.")

        # ── Phase 2: fire as soon as Phase 1 audio is done ───────────────────
        async def _deliver_news():
            try:
                lang_str = (f" Speak in {lang} unless the user has since "
                            f"spoken another language, in which case use theirs."
                            if lang else "")

                # Wait for news fetch (already running) and Phase 1 turn-complete
                # in parallel — whichever takes longer determines the wait time
                news_done   = asyncio.wrap_future(news_future)
                turn_waited = False
                if self._turn_done_event:
                    try:
                        await asyncio.wait_for(self._turn_done_event.wait(), timeout=6.0)
                        turn_waited = True
                    except asyncio.TimeoutError:
                        pass

                # Extra buffer: turn_complete fires when Gemini finishes *generating*
                # Phase 1, but audio may still be playing.  Waiting a beat here
                # prevents Phase 2 audio from arriving while Phase 1 is mid-sentence
                # (which sounds like a "repeated first response" to the user).
                if turn_waited:
                    await asyncio.sleep(0.8)
                else:
                    await asyncio.sleep(1.0)

                try:
                    news_text = await asyncio.wait_for(news_done, timeout=8.0)
                except Exception as e:
                    self.ui.write_log(f"SYS: News fetch timed out/failed: {e!r}")
                    news_text = ""

                if not self.session:
                    return

                failed = (not news_text) or news_text.startswith(
                    ("No news found", "Search failed", "Please provide")
                )
                if not failed:
                    # Show on UI content panel immediately
                    self.ui.show_content("NEWS — top world news today", news_text)

                    p2 = (
                        f"[BRIEFING] Here are today's top news headlines:\n{news_text}\n\n"
                        "Pick ONE headline, summarise it in one sentence, then say the full list "
                        f"is displayed on screen. Do not call any tools.{lang_str}"
                    )
                else:
                    self.ui.write_log(
                        f"SYS: News unavailable — backend returned: {news_text[:120]!r}"
                    )
                    p2 = (
                        "News headlines could not be fetched right now. "
                        f"Let the user know briefly.{lang_str}"
                    )

                await self.session.send_client_content(
                    turns={"role": "user", "parts": [{"text": p2}]},
                    turn_complete=True,
                )
                print("[CHARLIE] Briefing phase 2 (news) sent.")
            except Exception as e:
                print(f"[Briefing] Phase 2 error: {e}")
                print(f"[CHARLIE] Briefing phase 2 failed: {e}")
                self.ui.write_log("SYS: Could not fetch the news for the briefing.")

        asyncio.create_task(_deliver_news())

    # ── Session memory ──────────────────────────────────────────────────────────

    async def _save_session_summary(self) -> None:
        """Summarise the current session in 1-2 sentences and save to long_term.json."""
        log = self._session_log
        if len(log) < 3:          # need at least one exchange to be worth saving
            return
        self._session_log = []    # reset immediately so the next session starts clean

        memory = load_memory()
        lang_entry = memory.get("identity", {}).get("language", {})
        lang = (lang_entry.get("value", "") if isinstance(lang_entry, dict) else str(lang_entry)).strip()
        lang = lang or "English"

        convo = "\n".join(log[-40:])   # cap at last 40 turns to stay within token budget
        prompt = (
            f"Summarize this conversation in 1-2 sentences in {lang}. "
            "Focus on what the user accomplished or discussed. "
            "Output ONLY the summary text, nothing else:\n\n" + convo
        )
        try:
            from core import gemini
            summary = await asyncio.to_thread(
                gemini.text, prompt, gemini.SMART, None, 30_000,
            )
            if summary:
                save_session_summary(summary, lang)
        except Exception as e:
            print(f"[Memory] ⚠️ Session summary failed: {e}")

    async def _send_companion_checkin(self) -> None:
        """Start an opted-in daily/weekly check-in when conversation is idle."""
        if not checkin_due():
            return
        await asyncio.sleep(12)
        for _ in range(12):
            if not self.session or not self._awake:
                return
            with self._speaking_lock:
                speaking = self._is_speaking
            if not speaking and (time.monotonic() - self._last_user_speech) >= 10:
                break
            await asyncio.sleep(5)
        else:
            return
        try:
            await self.session.send_client_content(
                turns={"role": "user", "parts": [{"text": (
                    "[COMPANION CHECK-IN] Start one brief, warm, specific conversation using "
                    "the active profile's goals, tasks, learning plan, or recent context. Ask "
                    "only one question. Do not say 'How can I help?' and do not call tools."
                )}]},
                turn_complete=True,
            )
            mark_checkin()
        except Exception as exc:
            print(f"[Companion] Check-in failed: {exc}")

    async def _send_voice_preview(self) -> None:
        """Let the user hear the newly connected voice in their chosen style."""
        await asyncio.sleep(1.2)
        if not self.session or not self._awake:
            return
        try:
            await self.session.send_client_content(
                turns={"role": "user", "parts": [{"text": (
                    "[VOICE PREVIEW] In one short natural sentence, say that this is my new voice "
                    "and ask whether it feels right. Follow the active Natural Speech Director. "
                    "Do not mention these instructions and do not call tools."
                )}]},
                turn_complete=True,
            )
        except Exception as exc:
            print(f"[VoicePreview] {exc}")

    # ── System monitor ──────────────────────────────────────────────────────────

    async def _run_system_monitor(self) -> None:
        """Background task: voice alerts when metrics exceed thresholds."""
        while True:
            await asyncio.sleep(10)
            alert = await asyncio.to_thread(self._sys_monitor.check)
            if not alert or not self.session or not self._awake:
                continue
            # Don't interrupt an active conversation
            with self._speaking_lock:
                speaking = self._is_speaking
            if speaking or (time.monotonic() - self._last_user_speech) < 10:
                continue
            try:
                await self.session.send_client_content(
                    turns={"role": "user", "parts": [{"text": alert}]},
                    turn_complete=True,
                )
            except Exception as e:
                print(f"[Monitor] ⚠️ Could not send alert: {e}")

    # ── Background monitor ──────────────────────────────────────────────────────

    async def _run_background_monitor(self) -> None:
        """Check user-configured topics once per day; speak alerts when new headlines appear."""
        await asyncio.sleep(300)          # wait 5 min after startup before first check
        while True:
            if self.session and self._awake:
                # Don't interrupt if user spoke recently or CHARLIE is mid-sentence
                with self._speaking_lock:
                    speaking = self._is_speaking
                recent_speech = (time.monotonic() - self._last_user_speech) < 30
                if not speaking and not recent_speech:
                    try:
                        alerts = await asyncio.to_thread(monitor_check_all)
                        memory = load_memory()
                        lang_e = memory.get("identity", {}).get("language", {})
                        lang   = (lang_e.get("value", "") if isinstance(lang_e, dict) else str(lang_e)).strip() or "English"
                        for alert in alerts:
                            msg = (
                                f"{alert}\n\n"
                                f"Inform the user about this development naturally in {lang}. "
                                "One brief sentence only."
                            )
                            await self.session.send_client_content(
                                turns={"role": "user", "parts": [{"text": msg}]},
                                turn_complete=True,
                            )
                            print("[CHARLIE] Monitor alert sent.")
                            await asyncio.sleep(6)   # gap between consecutive alerts
                    except Exception as e:
                        print(f"[Monitor] ⚠️ Background check error: {e}")
            await asyncio.sleep(1800)     # check every 30 minutes

    async def _run_noise_monitor(self) -> None:
        """
        Polls the background noise classifier every 5 s.
        When children noise is detected → speaks polite Hindi/English message.
        When adult crowd noise is detected → asks user to move to quieter spot.
        Rate-limited to once per 90 s (enforced inside NoiseClassifier).
        """
        await asyncio.sleep(15)          # wait for session to fully settle
        while True:
            await asyncio.sleep(5)
            if not self.session or not self._awake:
                continue
            with self._speaking_lock:
                speaking = self._is_speaking
            if speaking:
                continue

            # Determine active language once per poll
            lang = "en"
            if self._lang_mgr is not None and self._lang_mgr.lang:
                lang = self._lang_mgr.lang

            # Do not interrupt if user spoke within last 15 seconds
            if time.time() - getattr(self, "_last_user_speech", 0) < 15.0:
                continue

            try:
                nc = get_noise_classifier()

                # ── Low voice check (silent log only — do NOT prompt speech) ──────
                if nc.get_low_voice_event():
                    self.ui.write_log("SYS: [Noise] Low voice detected.")
                    continue   # don't also fire ambient in the same cycle

                # ── Ambient noise check (silent log only — do NOT prompt speech) ──
                event = nc.get_event()
                if event is None:
                    continue

                if event in (NoiseClassifier.CHILDREN, NoiseClassifier.CROWD):
                    self.ui.write_log("SYS: [Noise] Background noise detected.")
                else:
                    continue
            except Exception as exc:
                print(f"[NoiseMonitor] Error: {exc}")

    # ── Proactive mode ──────────────────────────────────────────────────────────

    async def _run_proactive_mode(self) -> None:
        """
        Background task: periodically checks if the user has been silent long enough,
        then hands time + memory context to Gemini so it can decide what (if anything)
        to say proactively. No hardcoded rules — Gemini makes the call.
        """
        while True:
            await asyncio.sleep(60)   # evaluate once per minute

            if not self.session or not self._awake:
                continue

            if not get_proactive_audio_enabled():
                continue

            with self._speaking_lock:
                speaking = self._is_speaking
            if speaking:
                continue

            if not self._proactive.should_trigger(self._last_user_speech):
                continue

            self._proactive.mark_triggered()

            try:
                memory       = await asyncio.to_thread(load_memory)
                monitors     = await asyncio.to_thread(list_monitors)
                recent_turns = self._session_log[-8:] if self._session_log else []
                prompt = self._proactive.build_prompt(
                    memory       = memory,
                    monitors     = monitors or None,
                    recent_turns = recent_turns or None,
                )
                await self.session.send_client_content(
                    turns={"role": "user", "parts": [{"text": prompt}]},
                    turn_complete=True,
                )
                print("[CHARLIE] Proactive check-in.")
            except Exception as e:
                print(f"[Proactive] ⚠️ {e}")

    # ── Phone audio relay ────────────────────────────────────────────────────────

    async def _relay_phone_audio(self) -> None:
        """Forward phone mic PCM chunks from dashboard queue into the Gemini Live session."""
        if not self._dashboard:
            return
        q = getattr(self._dashboard, "_phone_audio_queue", None)
        if q is None:
            return
        while True:
            try:
                if not getattr(self._dashboard, "is_running", False):
                    self._phone_active = False
                    await asyncio.sleep(1.0)
                    continue
                chunk = await asyncio.wait_for(q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # No audio for 1 s → phone mic inactive, give PC mic back
                self._phone_active = False
                continue
            except asyncio.CancelledError:
                self._phone_active = False
                break
            except Exception as e:
                self._phone_active = False
                print(f"[Dashboard] Phone relay error: {e}")
                await asyncio.sleep(1.0)
                continue
            self._phone_active = True   # phone is streaming — silence PC mic
            with self._speaking_lock:
                speaking = self._is_speaking
            if not speaking and not self.ui.muted:
                try:
                    self.out_queue.put_nowait(chunk)
                except asyncio.QueueFull:
                    pass

    def _on_phone_connected(self) -> None:
        self.ui.write_log("SYS: Phone connected via Remote Dashboard.")
        self.ui.notify_phone_connected()

    # ── dashboard command relay ─────────────────────────────────────────────

    async def _process_dashboard_commands(self) -> None:
        while True:
            try:
                if not self._dashboard or not getattr(self._dashboard, "is_running", False):
                    await asyncio.sleep(1.0)
                    continue
                cmd_q = getattr(self._dashboard, "_command_queue", None)
                if cmd_q is None:
                    await asyncio.sleep(1.0)
                    continue
                text = await asyncio.wait_for(
                    cmd_q.get(), timeout=0.5
                )
                if not text:
                    continue
                # Wait up to 8s for session to become ready after a wake
                for _ in range(80):
                    if self.session:
                        break
                    await asyncio.sleep(0.1)
                if self.session:
                    # A remote command is deliberate control and the phone user
                    # has no desktop WAKE button — so it wakes CHARLIE if asleep.
                    if self._wake_enabled and not self._awake:
                        self.wake(reason="remote command")
                    await self.session.send_client_content(
                        turns={"role": "user", "parts": [{"text": text}]},
                        turn_complete=True,
                    )
                    self.ui.write_log(f"[Web]: {text}")
                else:
                    print(f"[Dashboard] Dropped command (no session): {text}")
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[Dashboard] Command error: {e}")
                await asyncio.sleep(0.5)

    # ── main loop ───────────────────────────────────────────────────────────

    async def run(self):
        self._loop = asyncio.get_event_loop()
        self._reconnect_event = asyncio.Event()

        # ── Wire the shared core services to the interface ───────────────────
        # The confirmation gate is useless without a way to ask, and a memory
        # trim is invisible without a way to say so. Both are bound once here
        # rather than passed down through every action signature.
        confirm_gate.bind(
            show = self.ui.show_confirm,
            hide = self.ui.hide_confirm,
            log  = self.ui.write_log,
        )
        set_trim_notifier(self.ui.write_log)

        # Tell the device picker the exact rates the streams open at, from the
        # constants that actually open them — so it can never list a device that
        # cannot be opened at them.
        audio_devices.configure(SEND_SAMPLE_RATE, RECEIVE_SAMPLE_RATE)

        # Enumerate audio devices off-thread. The settings drawer must never pay
        # for host-API enumeration on the Qt thread.
        # Start dashboard (optional — needs: pip install fastapi "uvicorn[standard]" cryptography)
        async def _safe_dashboard_serve():
            try:
                if self._dashboard:
                    await self._dashboard.serve()
            except SystemExit as se:
                print(f"[Dashboard] Uvicorn exit isolated: {se}", flush=True)
            except Exception as exc:
                print(f"[Dashboard] Serve failure isolated: {exc}", flush=True)
            finally:
                if self._dashboard:
                    self._dashboard.shutdown()

        try:
            from dashboard.server import DashboardServer
            self._dashboard = DashboardServer()
            self._dashboard.set_connect_callback(self._on_phone_connected)
            asyncio.create_task(_safe_dashboard_serve())
            # Runs for the whole lifetime, not just inside an active session
            asyncio.create_task(self._process_dashboard_commands())
        except (SystemExit, Exception) as e:
            print(f"[Dashboard] Disabled: {e}", flush=True)
            self._dashboard = None

        _model_idx = 0
        while True:
            try:
                cur_model = LIVE_MODEL_FALLBACKS[_model_idx % len(LIVE_MODEL_FALLBACKS)]
                print(f"[CHARLIE] Initializing connection to {cur_model}...")
                self.ui.set_state("READY")
                _resumed_with = self._resume_handle is not None
                config = self._build_config()

                # Fresh client on every reconnect — avoids stale HTTP session state
                resolved_key = _get_api_key()
                if not resolved_key:
                    print("[CHARLIE] ⚠️ Gemini credential not configured.", flush=True)
                    self.ui.write_log("ERR: Gemini credential not configured — please initialize key.")
                    self.ui.set_state("OFFLINE")
                    if hasattr(self.ui, "prompt_reconfig"):
                        self.ui.prompt_reconfig()
                    while not self.ui._win._ready:
                        await asyncio.sleep(0.5)
                    self._retry_count = 0
                    continue

                client = None
                try:
                    client = genai.Client(
                        api_key=resolved_key,
                        http_options={"api_version": "v1beta"}
                    )
                except Exception as _cl_init_err:
                    print(f"[CHARLIE] ⚠️ Gemini client creation failed: {_cl_init_err}", flush=True)
                    self.ui.write_log("ERR: Failed to initialize Gemini client — please re-enter key.")
                    self.ui.set_state("ERROR")
                    if hasattr(self.ui, "prompt_reconfig"):
                        self.ui.prompt_reconfig()
                    while not self.ui._win._ready:
                        await asyncio.sleep(0.5)
                    self._retry_count = 0
                    continue

                async with (
                    client.aio.live.connect(model=cur_model, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session          = session
                    self.audio_in_queue   = asyncio.Queue()
                    self.out_queue        = asyncio.Queue(maxsize=200)
                    self._turn_done_event = asyncio.Event()

                    # Reset transient state that must not carry over from a previous session
                    self._pending_vision       = None
                    self._vision_cam_active    = False
                    self._vision_close_pending = False
                    self._vision_busy          = False
                    self._vision_last_time     = 0.0
                    self._interrupted          = False
                    self._barge_in_pending     = False
                    self._barge_in_buffer.clear()

                    print("[CHARLIE] Connected.")
                    self._retry_count = 0
                    if _resumed_with:
                        # Say it plainly: the difference between "it reconnected"
                        # and "it reconnected and still knows what we were doing"
                        # is the whole point, and it is invisible otherwise.
                        self.ui.write_log("SYS: Reconnected — conversation restored.")

                    # Wake word: if enabled, come up ASLEEP (mic gated, silent)
                    # until the user says "Hey Charlie" or taps wake in the UI.
                    if self._wake_enabled:
                        self._ensure_wake_detector()
                        self._awake = False
                        self.ui.set_state("READY")
                        self.ui.write_log("SYS: CHARLIE online — sleeping. Say 'Hey Charlie' to wake me.")
                    else:
                        self._awake = True
                        self.ui.set_state("READY")
                        self.ui.write_log("SYS: CHARLIE online.")

                    if self._dashboard and getattr(self._dashboard, "is_running", False):
                        await self._dashboard.broadcast({"type": "status", "state": "active"})

                    # Do not clear the event here. A settings change can arrive
                    # while `live.connect()` is still establishing this session;
                    # clearing it now would lose that newer request and leave the
                    # server using the previous voice even though the UI already
                    # shows the new profile. `_watch_reconnect()` clears only the
                    # request it actually consumes.
                    tg.create_task(self._watch_reconnect())
                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    tg.create_task(self._run_system_monitor())
                    tg.create_task(self._run_background_monitor())
                    tg.create_task(self._run_proactive_mode())
                    tg.create_task(self._run_sleep_watch())
                    tg.create_task(self._run_noise_monitor())
                    if self._dashboard and getattr(self._dashboard, "is_running", False):
                        tg.create_task(self._relay_phone_audio())

                    # Morning briefing — fires once per process launch (if enabled).
                    # Skipped in wake-word mode: it comes up asleep, and a briefing
                    # would mean talking while "asleep".
                    # ── Personalised greeting (fires every fresh connect) ──────
                    if not self._greeting_sent and self._awake:
                        self._greeting_sent = True
                        tg.create_task(self._send_greeting())
                    if not self._briefing_sent and get_brief_enabled() and self._awake:
                        self._briefing_sent = True
                        tg.create_task(self._send_startup_briefing())
                    if self._awake and checkin_due():
                        tg.create_task(self._send_companion_checkin())
                    if self._awake and self._voice_preview_pending:
                        self._voice_preview_pending = False
                        tg.create_task(self._send_voice_preview())

            except KeyboardInterrupt:
                raise
            except SystemExit:
                raise
            except BaseException as e:
                # Catches both Exception and BaseExceptionGroup (Python 3.11+
                # TaskGroup raises BaseExceptionGroup when tasks are cancelled
                # externally, which `except Exception` would miss, letting the
                # exception escape the while-loop and causing asyncio.run() to
                # start shutdown — resulting in "executor after shutdown" errors).
                # Voluntary reconnect (voice change) — not an error. Rebuild the
                # session immediately with no backoff and no scary logs.
                if _is_reconnect_signal(e):
                    print("[CHARLIE] Voluntary reconnect requested.")
                    try:
                        from core.tool_gateway import clear_discovery_session
                        clear_discovery_session(str(getattr(self, "_resume_handle", "active_session")))
                    except Exception:
                        pass
                    if not _keep_context_of(e):
                        # A deliberate clean slate (voice change) — drop the
                        # handle so the next connect really does start empty.
                        self._resume_handle = None
                    self._conn_backoff = 0
                    continue

                # A resumption handle the server will not accept — expired, or
                # belonging to a session it has since dropped. Without this, the
                # same dead handle would be replayed on every retry and the
                # assistant would never come back at all: the feature meant to
                # survive a reconnect would be the thing preventing one. Drop it
                # once and let the next attempt start clean.
                if _resumed_with and (
                    "resum" in str(e).lower()
                    or "handle" in str(e).lower()
                    or "INVALID_ARGUMENT" in str(e)
                    or "NOT_FOUND" in str(e)
                ):
                    print("[CHARLIE] 🔗 Resumption handle rejected — starting a fresh session")
                    self.ui.write_log("SYS: Could not restore the conversation — starting fresh.")
                    self._resume_handle = None
                    self._conn_backoff = 0
                    continue

                err_str = str(e)
                print(f"[CHARLIE] Error ({type(e).__name__}): {e}")
                traceback.print_exc()

                # Model not found / rejected — advance fallback ladder
                if "not_found" in err_str.lower() or "404" in err_str or "not found" in err_str.lower():
                    _model_idx += 1
                    print(f"[CHARLIE] Model failed. Trying next model: {LIVE_MODEL_FALLBACKS[_model_idx % len(LIVE_MODEL_FALLBACKS)]}")
                    continue

                # Turn-taking / media / thinking knobs rejected by the server
                # (preview API drift) — drop them first, because they are the
                # newest fields and the cheapest to lose. Proactive audio is
                # tried again on the next pass if the error persists.
                if self._tuned_live and (
                    "INVALID_ARGUMENT" in err_str
                    or "Unknown name" in err_str
                    or "unexpected keyword" in err_str
                    or "realtime_input" in err_str.lower()
                    or "media_resolution" in err_str.lower()
                    or "thinking" in err_str.lower()
                ):
                    self._tuned_live = False
                    print("[CHARLIE] Live tuning rejected — reconnecting without it.")
                    continue

                # Proactive audio rejected by the server (preview API drift) —
                # drop it and reconnect with the plain config.
                if self._enhanced_live and (
                    "INVALID_ARGUMENT" in err_str
                    or "proactiv" in err_str.lower()
                    or "Unknown name" in err_str
                    or "unexpected keyword" in err_str
                ):
                    self._enhanced_live = False
                    self.ui.write_log(
                        "SYS: Proactive audio unavailable — reconnecting without it."
                    )
                    continue

                # Invalid API key — stop hammering the API, prompt re-configuration
                if any(x in err_str for x in (
                    "API key not valid", "1007", "No API key was provided",
                    "Gemini credential not configured", "no Gemini API key",
                    "API_KEY_INVALID"
                )):
                    self.ui.write_log("ERR: API key invalid or unconfigured — please re-enter key.")
                    self.ui.set_state("ERROR")
                    if hasattr(self.ui, "prompt_reconfig"):
                        self.ui.prompt_reconfig()
                    while not self.ui._win._ready:
                        await asyncio.sleep(1)
                    print("[CHARLIE] New API key saved — reconnecting...")
                    self._retry_count = 0
                    _conn_backoff = 3
                    continue

                # Network / timeout errors — log clearly and back off
                is_net_err = any(k in err_str for k in (
                    "TimeoutError", "timed out", "getaddrinfo", "CancelledError",
                    "ConnectionRefusedError", "OSError", "Cannot connect",
                ))
                if is_net_err:
                    _conn_backoff = min(getattr(self, "_conn_backoff", 3) * 2, 60)
                    self._conn_backoff = _conn_backoff
                    self.ui.write_log(
                        f"NET: Connection failed — retrying in {_conn_backoff}s."
                    )
                else:
                    self._conn_backoff = 3
            finally:
                self.session = None
                if client is not None:
                    try:
                        from core.gemini import safe_aclose_client
                        await safe_aclose_client(client)
                    except Exception:
                        pass
                # Only save if there was a real conversation (≥3 turns)
                if len(self._session_log) >= 3:
                    asyncio.create_task(self._save_session_summary())

            self.set_speaking(False)
            self._retry_count = getattr(self, "_retry_count", 0) + 1
            if self._retry_count > 3:
                print(f"[CHARLIE] Max reconnect attempts reached ({self._retry_count}). Charlie is OFFLINE.")
                self.ui.set_state("OFFLINE")
                if self._dashboard and getattr(self._dashboard, "is_running", False):
                    await self._dashboard.broadcast({"type": "status", "state": "offline"})
                # Halt continuous loop; wait for user action / reconnect signal
                while self._retry_count > 3:
                    if self._reconnect_event and self._reconnect_event.is_set():
                        self._reconnect_event.clear()
                        self._retry_count = 0
                        break
                    await asyncio.sleep(1)
            else:
                self.ui.set_state("ERROR")
                await asyncio.sleep(0.5)
                self.ui.set_state("RECONNECTING")
                if self._dashboard and getattr(self._dashboard, "is_running", False):
                    await self._dashboard.broadcast({"type": "status", "state": "reconnecting"})

                delay = getattr(self, "_conn_backoff", 3)
                print(f"[CHARLIE] Reconnecting in {delay}s (attempt {self._retry_count}/3)...")
                try:
                    await asyncio.wait_for(self._reconnect_event.wait(), timeout=delay)
                    self._reconnect_event.clear()
                except (asyncio.TimeoutError, Exception):
                    pass

# Backward-compatible alias
JarvisLive = CharlieLive


def main():
    try:
        from core.single_instance import acquire_single_instance
        if not acquire_single_instance():
            print("[Startup] Charlie is already running.", flush=True)
            sys.exit(0)
    except Exception as _inst_err:
        print(f"[Startup] Single instance check warning: {_inst_err}", flush=True)

    if _platform.system() == "Windows":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            hStdin = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(hStdin, ctypes.byref(mode)):
                # Disable QuickEdit Mode (0x0040) so clicking inside the terminal does not freeze the app
                new_mode = mode.value & ~0x0040
                kernel32.SetConsoleMode(hStdin, new_mode)
        except Exception:
            pass

    print("[CHARLIE] 🚀 Initializing Charlie AI Assistant runtime...", flush=True)
    try:
        from memory.config_manager import ensure_credentials_migrated
        ensure_credentials_migrated()
    except Exception as _mig_err:
        print(f"[CHARLIE] ⚠️ Credential migration warning: {_mig_err}", flush=True)
    try:
        from core.speech_booster import configure_speech_engine
        _opt = configure_speech_engine()
        print(f"[CHARLIE] ⚡ Speech accelerator active ({_opt.get('device')}, {_opt.get('compute_type')}, threads={_opt.get('threads')})", flush=True)
    except Exception:
        pass
    import traceback
    try:
        from engine.deployment.crash_reporter import CrashReportingManager
        _crash_mgr = CrashReportingManager()
    except Exception:
        _crash_mgr = None

    def _global_excepthook(exc_type, exc_val, exc_tb):
        try:
            from core.secret_redactor import redact_text
            safe_val = redact_text(str(exc_val))
            tb_str = redact_text("".join(traceback.format_exception(exc_type, exc_val, exc_tb)))
        except Exception:
            safe_val = str(exc_val)
            tb_str = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
        print(f"\n[CHARLIE] ❌ Unhandled exception ({exc_type.__name__}): {safe_val}", flush=True)
        if _crash_mgr and exc_val is not None:
            try:
                _crash_mgr.capture_crash(component="core.runtime", error=exc_val, stack_trace=tb_str)
            except Exception:
                pass

    sys.excepthook = _global_excepthook
    if hasattr(threading, "excepthook"):
        def _thread_excepthook(args):
            try:
                from core.secret_redactor import redact_text
                safe_val = redact_text(str(args.exc_value))
                tb_str = redact_text("".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))) if args.exc_traceback else ""
            except Exception:
                safe_val = str(args.exc_value)
                tb_str = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)) if args.exc_traceback else ""
            print(f"\n[CHARLIE] ❌ Thread exception in {args.thread.name}: {safe_val}", flush=True)
            if _crash_mgr and args.exc_value is not None:
                try:
                    _crash_mgr.capture_crash(component=f"thread.{args.thread.name}", error=args.exc_value, stack_trace=tb_str)
                except Exception:
                    pass
        threading.excepthook = _thread_excepthook

    print("[CHARLIE] 🎙️ Checking voice configurations...", flush=True)
    ensure_sweet_voice_profiles()
    print("[CHARLIE] 🖥️ Launching desktop GUI...", flush=True)
    ui = CharlieUI("face.png")

    # ── Immediate Plugin Pre-Discovery ────────────────────────────────────────
    # Discover and wire plugins synchronously at UI startup so Integrations & Plugin Store
    # works immediately without waiting for the background AI live runner.
    try:
        from core.plugin_loader import discover_plugins
        if str(BASE_DIR) not in sys.path:
            sys.path.insert(0, str(BASE_DIR))
        _pre_plugin_reg = discover_plugins(
            plugins_dir=BASE_DIR / "plugins",
            core_tool_names=set(),
            logger=lambda msg: print(f"[Plugins] {msg}"),
            notify=lambda msg: ui.write_log(f"SYS: {msg}"),
        )
        ui.get_plugins = _pre_plugin_reg.list_for_ui
        ui.get_plugin_settings = _pre_plugin_reg.settings_schemas
        ui.rescan_plugins = lambda: _pre_plugin_reg.rescan(BASE_DIR / "plugins", set())
        print(f"[CHARLIE] 🧩 Pre-discovered {len(_pre_plugin_reg._all_records)} plugins for UI ({len(_pre_plugin_reg._plugins)} valid)", flush=True)
    except Exception as _p_err:
        print(f"[CHARLIE] ⚠️ Plugin pre-discovery error: {_p_err}", flush=True)

    try:
        from core.audio_router import get_audio_router
        _router = get_audio_router()
        _router.add_change_callback(lambda direction, old_d, new_d: ui.write_log(f"AUDIO: Hardware hot-swap ({direction}): '{new_d}'"))
        _router.start_monitoring()
        ui.on_audio_device_change = lambda: _router.scan_devices()
        print("[CHARLIE] 🎧 Audio router active (hot-swap ready)", flush=True)
    except Exception as _router_err:
        print(f"[CHARLIE] ⚠️ Audio router warning: {_router_err}", flush=True)

    # Backfill language tags on existing RAG memory docs (non-blocking)
    def _rag_lang_backfill():
        try:
            from core.semantic_rag import get_rag_memory
            n = get_rag_memory().backfill_language_tags()
            if n:
                print(f"[RAG] Language tags backfilled on {n} existing memory docs.", flush=True)
        except Exception as _rag_err:
            print(f"[RAG] Backfill warning: {_rag_err}", flush=True)
    threading.Thread(target=_rag_lang_backfill, daemon=True, name="RAGLangBackfill").start()
    print("[CHARLIE] ✅ Charlie UI is now running! (Check taskbar / front window)", flush=True)

    def runner():
        print("[CHARLIE] ⚡ Background AI runner active — validating configuration...", flush=True)
        ui.wait_for_api_key()
        print("[CHARLIE] 🌐 Starting live connection...", flush=True)
        while True:
            try:
                charlie = CharlieLive(ui)
                asyncio.run(charlie.run())
            except KeyboardInterrupt:
                print("\n🔴 Shutting down...", flush=True)
                break
            except Exception as e:
                try:
                    from core.secret_redactor import redact_text
                    err_msg = redact_text(str(e))
                except Exception:
                    err_msg = str(e)
                print(f"\n[CHARLIE] ⚠️ Runner recovered from error: {err_msg}", flush=True)
                traceback.print_exc()
                time.sleep(2)

    threading.Thread(target=runner, daemon=True, name="CharlieLiveRunner").start()
    try:
        ret = ui.root.mainloop()
        print(f"\n[CHARLIE] Qt mainloop finished with code: {ret}", flush=True)
    finally:
        try:
            from core.runtime_voice_control import unregister_voice_runtime
            unregister_voice_runtime()
        except Exception:
            pass
        try:
            from core.single_instance import release_single_instance
            release_single_instance()
        except Exception:
            pass

if __name__ == "__main__":
    main()
