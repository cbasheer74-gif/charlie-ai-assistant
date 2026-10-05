"""
Text-to-Speech engines for MARK XL.

EdgeTTS     – free Microsoft TTS (internet required, no API key)
Kokoro      – fully offline neural TTS (~330 MB model)
ElevenLabs  – cloud API (API key required, best quality)
"""
from __future__ import annotations

import asyncio
import os
import queue as _queue
import threading
from typing import Callable, Optional

import numpy as np
import sounddevice as sd



# USE_TF=0 stops transformers from importing TensorFlow (saves 4-8 s startup).
# Do NOT set USE_TORCH or USE_JAX explicitly — forcing those values breaks
# transformers' lazy-loader on certain versions, causing AutoModel and other
# classes to vanish from the public namespace.  Auto-detection is reliable.
os.environ.setdefault("USE_TF",                 "0")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


# ---------------------------------------------------------------------------
# Audio playback helpers
# ---------------------------------------------------------------------------

def _to_numpy(samples) -> np.ndarray:
    """Convert samples to float32 numpy array.

    Handles both numpy arrays and PyTorch tensors (Kokoro >= 0.9).

    PyTorch built against numpy 1.x raises RuntimeError('Numpy is not available')
    when numpy 2.x is installed.  The .tolist() fallback always works regardless
    of PyTorch / numpy version pairing.
    """
    if hasattr(samples, "detach"):                  # PyTorch tensor
        t = samples.detach().cpu().float()
        try:
            return t.numpy()                        # fast path (compatible versions)
        except RuntimeError:
            # PyTorch/numpy version mismatch — convert via Python list (always safe)
            return np.asarray(t.tolist(), dtype=np.float32)
    return np.asarray(samples, dtype=np.float32)


def _compress_silence(
    arr: np.ndarray,
    sample_rate: int    = 24_000,
    max_silence_ms: int = 500,    # cap punctuation pauses — keeps natural rhythm
    threshold: float    = 0.003,  # RMS below this = silence; lower = less clipping
) -> np.ndarray:
    """
    Shorten Kokoro's very long punctuation pauses (1-2 s → ≤500 ms).
    Conservative settings preserve natural prosody; only trims extreme pauses.
    """
    max_samp  = int(max_silence_ms * sample_rate / 1000)
    frame_len = 240                   # ~10 ms at 24 kHz
    out: list[np.ndarray] = []
    silent_acc = 0

    for i in range(0, len(arr), frame_len):
        chunk = arr[i : i + frame_len]
        if np.sqrt(np.mean(chunk ** 2) + 1e-12) < threshold:
            silent_acc += len(chunk)
            if silent_acc <= max_samp:
                out.append(chunk)
        else:
            silent_acc = 0
            out.append(chunk)

    return np.concatenate(out) if out else arr


def _get_output_device_idx():
    """Resolve configured output device for sounddevice."""
    try:
        from memory.config_manager import get_output_device
        from core import audio_devices
        spk_name = get_output_device()
        return audio_devices.resolve(spk_name, "output")
    except Exception:
        return None


def _safe_play_samples(
    samples: np.ndarray,
    sample_rate: int,
    dev=None,
    cancel_event: Optional[threading.Event] = None,
) -> None:
    """Stream audio samples with safe per-stream cancellation without affecting other streams."""
    if cancel_event and cancel_event.is_set():
        return

    arr = np.asarray(samples, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr.reshape(-1)

    cursor = 0
    finished = threading.Event()

    def callback(outdata, frames, time_info, status):
        nonlocal cursor
        if cancel_event and cancel_event.is_set():
            outdata.fill(0)
            raise sd.CallbackAbort

        remaining = len(arr) - cursor
        if remaining <= 0:
            outdata.fill(0)
            raise sd.CallbackStop

        chunk_len = min(frames, remaining)
        outdata[:chunk_len, 0] = arr[cursor : cursor + chunk_len]
        if chunk_len < frames:
            outdata[chunk_len:].fill(0)
            cursor += chunk_len
            raise sd.CallbackStop
        cursor += chunk_len

    def finished_callback():
        finished.set()

    try:
        stream = sd.OutputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            device=dev,
            callback=callback,
            finished_callback=finished_callback,
        )
        with stream:
            while not finished.is_set():
                if cancel_event and cancel_event.is_set():
                    try:
                        stream.abort()
                    except Exception:
                        pass
                    break
                finished.wait(timeout=0.05)
    except Exception:
        # Fallback if custom OutputStream fails
        if not (cancel_event and cancel_event.is_set()):
            try:
                sd.play(arr, sample_rate, device=dev)
                import time
                dur = len(arr) / float(sample_rate)
                end_time = time.time() + dur
                while time.time() < end_time:
                    if cancel_event and cancel_event.is_set():
                        sd.stop()
                        break
                    time.sleep(0.05)
            except Exception:
                pass


def _play_np(samples, sample_rate: int, cancel_event: Optional[threading.Event] = None) -> None:
    """Play float32 mono (or stereo) audio via sounddevice.
    Accepts numpy arrays or PyTorch tensors.
    """
    if cancel_event and cancel_event.is_set():
        return
    dev = _get_output_device_idx()
    arr = _to_numpy(samples)
    _safe_play_samples(arr, sample_rate, dev=dev, cancel_event=cancel_event)


def _play_audio_bytes(audio_bytes: bytes, cancel_event: Optional[threading.Event] = None) -> None:
    """Decode MP3/WAV/OGG bytes and play via sounddevice (uses miniaudio)."""
    if cancel_event and cancel_event.is_set():
        return
    import miniaudio
    decoded = miniaudio.decode(
        audio_bytes,
        output_format=miniaudio.SampleFormat.FLOAT32,
        nchannels=1,
    )
    samples = np.array(decoded.samples, dtype=np.float32)
    dev = _get_output_device_idx()
    _safe_play_samples(samples, decoded.sample_rate, dev=dev, cancel_event=cancel_event)


# ---------------------------------------------------------------------------
# Engines
# ---------------------------------------------------------------------------

class WindowsSAPITTSEngine:
    """Windows native SAPI5 TTS – zero dependency, fully offline."""

    def __init__(self, voice: str = "en-US-GuyNeural"):
        self.voice = str(voice or "").lower()

    def speak(self, text: str, cancel_event: Optional[threading.Event] = None) -> None:
        if not text or not text.strip():
            return
        if cancel_event and cancel_event.is_set():
            return
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        try:
            import win32com.client
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            want_female = any(k in self.voice for k in ("female", "zira", "aoede", "kore", "jenny", "aria"))
            for v in speaker.GetVoices():
                desc = v.GetDescription().lower()
                if want_female and "zira" in desc:
                    speaker.Voice = v
                    break
                elif not want_female and "david" in desc:
                    speaker.Voice = v
                    break
            # SVSFlagsAsync = 1 (pollable async playback)
            speaker.Speak(str(text).strip(), 1)
            while not speaker.WaitUntilDone(50):
                if cancel_event and cancel_event.is_set():
                    try:
                        # SVSFPurgeBeforeSpeak = 2 (instantly purges and cancels speech)
                        speaker.Speak("", 2)
                    except Exception:
                        pass
                    break
        except Exception as e:
            print(f"[TTS] SAPI5 error: {e}")


# ---------------------------------------------------------------------------
# Script-aware TTS chunker
# ---------------------------------------------------------------------------

def _classify_char_script(ch: str) -> str:
    """Return a coarse script bucket for a Unicode character.

    Buckets align with EdgeTTS voice families so that each chunk can be
    synthesised with the right voice.  Latin-script characters all share one
    bucket because EdgeTTS auto-handles accent detection within Latin.
    """
    cp = ord(ch)
    if 0x0900 <= cp <= 0x097F:  return "devanagari"   # Hindi / Marathi / Sanskrit
    if 0x0980 <= cp <= 0x09FF:  return "bengali"       # Bengali / Assamese
    if 0x0A00 <= cp <= 0x0A7F:  return "gurmukhi"      # Punjabi
    if 0x0A80 <= cp <= 0x0AFF:  return "gujarati"
    if 0x0B00 <= cp <= 0x0B7F:  return "odia"
    if 0x0B80 <= cp <= 0x0BFF:  return "tamil"
    if 0x0C00 <= cp <= 0x0C7F:  return "telugu"
    if 0x0C80 <= cp <= 0x0CFF:  return "kannada"
    if 0x0D00 <= cp <= 0x0D7F:  return "malayalam"
    if 0x0600 <= cp <= 0x06FF:  return "arabic"        # Arabic / Urdu / Persian
    if 0x0400 <= cp <= 0x04FF:  return "cyrillic"      # Russian / Bulgarian
    if 0x0370 <= cp <= 0x03FF:  return "greek"
    if 0x0590 <= cp <= 0x05FF:  return "hebrew"
    if 0x0E00 <= cp <= 0x0E7F:  return "thai"
    if 0x3040 <= cp <= 0x30FF:  return "japanese"      # Hiragana + Katakana
    if 0x31F0 <= cp <= 0x31FF:  return "japanese"      # Katakana phonetic ext
    if 0xAC00 <= cp <= 0xD7AF:  return "korean"        # Hangul syllables
    if (0x4E00 <= cp <= 0x9FFF or                      # CJK Unified
        0x3400 <= cp <= 0x4DBF):return "chinese"
    # ASCII / Latin extended / punctuation / digits → Latin bucket
    return "latin"


def split_by_script(text: str) -> list[str]:
    """Split *text* into contiguous runs sharing the same script bucket.

    Example:
        "Hello चार्ली, how are you? கேளு!"
        → ["Hello ", "चार्ली", ", how are you? ", "கேளு", "!"]

    Whitespace and punctuation inherit the *preceding* bucket so they stay
    attached to the run they semantically belong to.  If the text starts with
    whitespace/punctuation it is assigned to the first non-neutral script found
    afterward (or "latin" as fallback).
    """
    if not text:
        return []

    NEUTRAL = {"latin"}   # punctuation/spaces assigned to adjacent non-neutral run

    chunks: list[str] = []
    current_script: str = ""
    current_buf: list[str] = []

    for ch in text:
        script = _classify_char_script(ch)
        # Punctuation/digits/spaces (all "latin") inherit current script to avoid
        # trivial 1-char "latin" splits inside non-Latin runs.
        effective = script if script != "latin" else (current_script or "latin")

        if effective != current_script:
            if current_buf:
                chunks.append("".join(current_buf))
            current_buf = [ch]
            current_script = effective
        else:
            current_buf.append(ch)

    if current_buf:
        chunks.append("".join(current_buf))

    # Merge trivially short trailing punctuation back into the preceding chunk
    merged: list[str] = []
    for chunk in chunks:
        if merged and len(chunk.strip()) <= 2 and not any(
            0x0080 <= ord(c) for c in chunk  # no high-Unicode → safe to merge
        ):
            merged[-1] += chunk
        else:
            merged.append(chunk)

    return [c for c in merged if c.strip()]  # drop whitespace-only shards


# ---------------------------------------------------------------------------


class EdgeTTSEngine:
    """Microsoft EdgeTTS – free, requires internet."""

    def __init__(self, voice: str = "en-US-GuyNeural"):
        self.voice = voice

    def speak(self, text: str, ui=None, emotion=None, lang: Optional[str] = None, cancel_event: Optional[threading.Event] = None) -> None:
        """Speak *text*, splitting at script boundaries first.

        If the response mixes scripts (e.g. "Sure! यहाँ देखें: click here"),
        each run is synthesised with the matching voice so there are no
        mid-word voice glitches.  Single-script responses go through the
        original fast path with zero overhead.
        """
        if cancel_event and cancel_event.is_set():
            return
        chunks = split_by_script(text)
        if not chunks:
            return

        if len(chunks) == 1:
            # Fast path — no split needed
            self._speak_chunk(chunks[0], ui=ui, emotion=emotion, lang=lang, cancel_event=cancel_event)
        else:
            # Multi-script: synthesise each chunk sequentially
            for chunk in chunks:
                if cancel_event and cancel_event.is_set():
                    break
                if chunk.strip():
                    self._speak_chunk(chunk, ui=ui, emotion=emotion, lang=lang, cancel_event=cancel_event)

    def _speak_chunk(self, text: str, ui=None, emotion=None, lang: Optional[str] = None, cancel_event: Optional[threading.Event] = None) -> None:
        """Synthesise a single script-homogeneous text chunk."""
        if cancel_event and cancel_event.is_set():
            return
        try:
            loop = asyncio.new_event_loop()
            try:
                audio_bytes, boundaries = loop.run_until_complete(
                    self._synth_with_boundaries(text, emotion=emotion, lang=lang)
                )
            finally:
                loop.close()
            if cancel_event and cancel_event.is_set():
                return
            if audio_bytes:
                self._play_with_visemes(audio_bytes, boundaries, ui=ui, cancel_event=cancel_event)
                return
        except Exception as e:
            if cancel_event and cancel_event.is_set():
                return
            print(f"[TTS] EdgeTTS failed ({e}) — falling back to Windows SAPI5")
        if not (cancel_event and cancel_event.is_set()):
            WindowsSAPITTSEngine(voice=self.voice).speak(text, cancel_event=cancel_event)

    def _select_voice(self, text: str, lang: Optional[str] = None) -> str:
        """Auto-detect language from active preference, Unicode script ranges,
        or language keywords and route to the correct EdgeTTS Neural voice.
        Supports all Indian regional languages, European languages, and Asian languages.

        Priority: explicit lang/voice -> script/word detection -> English fallback.
        """
        # ── 0. Resolve voice gender from hub preference (authoritative) ──────
        is_female = True  # default
        try:
            from memory.personal_hub import load_hub
            _hub_gender = load_hub().get("speech", {}).get("voice_gender", "female")
            is_female = (_hub_gender != "male")
        except Exception:
            # Fallback: infer from current voice name keywords
            is_female = any(
                k in str(self.voice).lower()
                for k in ("female", "zira", "aoede", "kore", "jenny", "aria", "swara",
                          "ananya", "neerja", "roshni", "avri", "indira", "aarohi",
                          "pallavi", "shruti", "sapna", "sobhana", "tanishaa", "dhwani",
                          "ojas", "subhasini", "uzma", "yashica", "elvira", "denise",
                          "katja", "elsa", "francisca", "svetlana", "nanami", "xiaoxiao",
                          "sunhi", "zariyah")
            )

        # ── 1. Explicit language parameter or active system configuration ────
        _target_lang = (lang or "").lower().strip()
        if not _target_lang or _target_lang == "auto":
            try:
                from engine.voice.user_greeter_clean import _lang_pref
                saved_lang = _lang_pref.get("default_user")
                if saved_lang and saved_lang != "auto":
                    _target_lang = saved_lang.lower().strip()
            except Exception:
                pass
        if not _target_lang or _target_lang == "auto":
            try:
                from memory.personal_hub import load_hub
                hub_lang = load_hub().get("speech", {}).get("language")
                if hub_lang and hub_lang != "auto":
                    _target_lang = hub_lang.lower().strip()
            except Exception:
                pass

        if _target_lang and _target_lang not in ("auto", "automatic"):
            try:
                from core.languages import get_language_voice
                v = get_language_voice(_target_lang, is_female=is_female)
                if v:
                    return v
            except Exception:
                pass

        # Check Unicode script detection across all regional and world scripts
        try:
            from core.languages import detect_language_script
            detected_info = detect_language_script(text)
            if detected_info:
                return detected_info.tts_female if is_female else detected_info.tts_male
        except Exception:
            pass

        _LANG_VOICES: dict[str, tuple[str, str]] = {
            "hi":        ("hi-IN-SwaraNeural",     "hi-IN-MadhurNeural"),
            "hindi":     ("hi-IN-SwaraNeural",     "hi-IN-MadhurNeural"),
            "hinglish":  ("en-IN-NeerjaNeural",    "en-IN-PrabhatNeural"),
            "mr":        ("mr-IN-AarohiNeural",    "mr-IN-ManoharNeural"),
            "marathi":   ("mr-IN-AarohiNeural",    "mr-IN-ManoharNeural"),
            "bn":        ("bn-IN-TanishaaNeural",  "bn-IN-BashkarNeural"),
            "bengali":   ("bn-IN-TanishaaNeural",  "bn-IN-BashkarNeural"),
            "ta":        ("ta-IN-PallaviNeural",   "ta-IN-ValluvarNeural"),
            "tamil":     ("ta-IN-PallaviNeural",   "ta-IN-ValluvarNeural"),
            "te":        ("te-IN-ShrutiNeural",    "te-IN-MohanNeural"),
            "telugu":    ("te-IN-ShrutiNeural",    "te-IN-MohanNeural"),
            "gu":        ("gu-IN-DhwaniNeural",    "gu-IN-NiranjanNeural"),
            "gujarati":  ("gu-IN-DhwaniNeural",    "gu-IN-NiranjanNeural"),
            "kn":        ("kn-IN-SapnaNeural",     "kn-IN-GaganNeural"),
            "kannada":   ("kn-IN-SapnaNeural",     "kn-IN-GaganNeural"),
            "ml":        ("ml-IN-SobhanaNeural",   "ml-IN-MidhunNeural"),
            "malayalam": ("ml-IN-SobhanaNeural",   "ml-IN-MidhunNeural"),
            "pa":        ("pa-IN-OjasNeural",      "pa-IN-OjasNeural"),
            "punjabi":   ("pa-IN-OjasNeural",      "pa-IN-OjasNeural"),
            "ur":        ("ur-PK-UzmaNeural",      "ur-PK-AsadNeural"),
            "urdu":      ("ur-PK-UzmaNeural",      "ur-PK-AsadNeural"),
            "or":        ("or-IN-SubhasiniNeural", "or-IN-SukantaNeural"),
            "odia":      ("or-IN-SubhasiniNeural", "or-IN-SukantaNeural"),
            "as":        ("as-IN-YashicaNeural",   "as-IN-PriyomNeural"),
            "assamese":  ("as-IN-YashicaNeural",   "as-IN-PriyomNeural"),
            "es":        ("es-ES-ElviraNeural",    "es-ES-AlvaroNeural"),
            "spanish":   ("es-ES-ElviraNeural",    "es-ES-AlvaroNeural"),
            "fr":        ("fr-FR-DeniseNeural",    "fr-FR-HenriNeural"),
            "french":    ("fr-FR-DeniseNeural",    "fr-FR-HenriNeural"),
            "de":        ("de-DE-KatjaNeural",     "de-DE-ConradNeural"),
            "german":    ("de-DE-KatjaNeural",     "de-DE-ConradNeural"),
            "it":        ("it-IT-ElsaNeural",      "it-IT-DiegoNeural"),
            "italian":   ("it-IT-ElsaNeural",      "it-IT-DiegoNeural"),
            "pt":        ("pt-BR-FranciscaNeural", "pt-BR-AntonioNeural"),
            "portuguese":("pt-BR-FranciscaNeural", "pt-BR-AntonioNeural"),
            "ru":        ("ru-RU-SvetlanaNeural",  "ru-RU-DmitryNeural"),
            "russian":   ("ru-RU-SvetlanaNeural",  "ru-RU-DmitryNeural"),
            "ja":        ("ja-JP-NanamiNeural",    "ja-JP-KeitaNeural"),
            "japanese":  ("ja-JP-NanamiNeural",    "ja-JP-KeitaNeural"),
            "zh":        ("zh-CN-XiaoxiaoNeural",  "zh-CN-YunjianNeural"),
            "chinese":   ("zh-CN-XiaoxiaoNeural",  "zh-CN-YunjianNeural"),
            "mandarin":  ("zh-CN-XiaoxiaoNeural",  "zh-CN-YunjianNeural"),
            "ko":        ("ko-KR-SunHiNeural",     "ko-KR-InJoonNeural"),
            "korean":    ("ko-KR-SunHiNeural",     "ko-KR-InJoonNeural"),
            "ar":        ("ar-SA-ZariyahNeural",   "ar-SA-HamedNeural"),
            "arabic":    ("ar-SA-ZariyahNeural",   "ar-SA-HamedNeural"),
            "nl":        ("nl-NL-ColetteNeural",   "nl-NL-MaartenNeural"),
            "pl":        ("pl-PL-AgnieszkaNeural", "pl-PL-MarekNeural"),
            "tr":        ("tr-TR-EmelNeural",      "tr-TR-AhmetNeural"),
        }

        # If a non-English, non-auto language is actively requested, use its dedicated voice
        if _target_lang in _LANG_VOICES:
            fv, mv = _LANG_VOICES[_target_lang]
            return fv if is_female else mv

        # ── 2. Script detection with language refinement ─────────────────────
        t = text or ""
        t_lower = t.lower()

        # Japanese: Hiragana / Katakana checked FIRST (before Kanji shared with CJK)
        if any("\u3040" <= ch <= "\u309F" or "\u30A0" <= ch <= "\u30FF" for ch in t):
            return "ja-JP-NanamiNeural" if is_female else "ja-JP-KeitaNeural"

        # Korean: Hangul
        if any("\uAC00" <= ch <= "\uD7AF" for ch in t):
            return "ko-KR-SunHiNeural" if is_female else "ko-KR-InJoonNeural"

        # Chinese: CJK Unified Ideographs (when no Hiragana/Katakana)
        if any("\u4E00" <= ch <= "\u9FFF" or "\u3400" <= ch <= "\u4DBF" for ch in t):
            return "zh-CN-XiaoxiaoNeural" if is_female else "zh-CN-YunjianNeural"

        # Cyrillic: Russian
        if any("\u0400" <= ch <= "\u04FF" for ch in t):
            return "ru-RU-SvetlanaNeural" if is_female else "ru-RU-DmitryNeural"

        # Greek
        if any("\u0370" <= ch <= "\u03FF" for ch in t):
            return "el-GR-AthinaNeural" if is_female else "el-GR-NestorasNeural"

        # Thai
        if any("\u0E00" <= ch <= "\u0E7F" for ch in t):
            return "th-TH-PremwadeeNeural" if is_female else "th-TH-NiwatNeural"

        # Hebrew
        if any("\u0590" <= ch <= "\u05FF" for ch in t):
            return "he-IL-HilaNeural" if is_female else "he-IL-AvriNeural"

        # Arabic / Urdu (Arabic script)
        if any("\u0600" <= ch <= "\u06FF" for ch in t):
            # Urdu markers vs Standard Arabic
            if any(w in t for w in ("ہیں", "کیا", "آپ", "ہوں", "کے", "کی", "سے", "نہیں")):
                return "ur-PK-UzmaNeural" if is_female else "ur-PK-AsadNeural"
            return "ar-SA-ZariyahNeural" if is_female else "ar-SA-HamedNeural"

        # Tamil
        if any("\u0B80" <= ch <= "\u0BFF" for ch in t):
            return "ta-IN-PallaviNeural" if is_female else "ta-IN-ValluvarNeural"

        # Telugu
        if any("\u0C00" <= ch <= "\u0C7F" for ch in t):
            return "te-IN-ShrutiNeural" if is_female else "te-IN-MohanNeural"

        # Kannada
        if any("\u0C80" <= ch <= "\u0CFF" for ch in t):
            return "kn-IN-SapnaNeural" if is_female else "kn-IN-GaganNeural"

        # Malayalam
        if any("\u0D00" <= ch <= "\u0D7F" for ch in t):
            return "ml-IN-SobhanaNeural" if is_female else "ml-IN-MidhunNeural"

        # Gujarati
        if any("\u0A80" <= ch <= "\u0AFF" for ch in t):
            return "gu-IN-DhwaniNeural" if is_female else "gu-IN-NiranjanNeural"

        # Gurmukhi (Punjabi)
        if any("\u0A00" <= ch <= "\u0A7F" for ch in t):
            return "pa-IN-OjasNeural"

        # Odia (Oriya)
        if any("\u0B00" <= ch <= "\u0B7F" for ch in t):
            return "or-IN-SubhasiniNeural" if is_female else "or-IN-SukantaNeural"

        # Bengali & Assamese (shared script range \u0980-\u09FF)
        if any("\u0980" <= ch <= "\u09FF" for ch in t):
            # Check for Assamese-specific characters: ৰ (\u09F0), ৱ (\u09F1) or Assamese vocabulary
            if any(ch in t for ch in ("\u09F0", "\u09F1")) or any(w in t for w in ("অসমীয়া", "আছোঁ", "কৰক", "নহয়", "ধন্যবাদ", "মই", "আপুনি")):
                return "as-IN-YashicaNeural" if is_female else "as-IN-PriyomNeural"
            return "bn-IN-TanishaaNeural" if is_female else "bn-IN-BashkarNeural"

        # Devanagari: Marathi vs Hindi
        if any("\u0900" <= ch <= "\u097F" for ch in t):
            # Check if text contains Marathi vocabulary markers
            _marathi_markers = ("आहे", "नाही", "करा", "सांगा", "नमस्कार", "कसे", "माझे",
                                "नाव", "होय", "काय", "झाले", "आहात", "धन्यवाद", "मराठी",
                                "मित्रा", "तुम्ही", "आम्ही", "आपण", "कसा", "कशी", "केले",
                                "आलो", "गेलो", "मदत", "शकतो", "बदल")
            if any(w in t for w in _marathi_markers):
                return "mr-IN-AarohiNeural" if is_female else "mr-IN-ManoharNeural"
            return "hi-IN-SwaraNeural" if is_female else "hi-IN-MadhurNeural"

        # ── 3. Latin-script language detection ───────────────────────────────
        # Spanish
        if "¿" in t or "¡" in t or any(w in t_lower for w in ("hola", "gracias", "por favor", "cómo estás", "buenos días", "amigo", "bienvenido")):
            return "es-ES-ElviraNeural" if is_female else "es-ES-AlvaroNeural"

        # French
        if any(w in t_lower for w in ("bonjour", "merci", "s'il vous plaît", "comment allez-vous", "au revoir", "oui")):
            return "fr-FR-DeniseNeural" if is_female else "fr-FR-HenriNeural"

        # German
        if any(w in t_lower for w in ("guten tag", "danke", "bitte", "wie geht", "auf wiedersehen", "hallo")):
            return "de-DE-KatjaNeural" if is_female else "de-DE-ConradNeural"

        # Italian
        if any(w in t_lower for w in ("buongiorno", "grazie", "per favore", "come stai", "ciao", "arrivederci")):
            return "it-IT-ElsaNeural" if is_female else "it-IT-DiegoNeural"

        # Portuguese
        if any(w in t_lower for w in ("olá", "obrigado", "por favor", "como vai", "bom dia", "boa tarde")):
            return "pt-BR-FranciscaNeural" if is_female else "pt-BR-AntonioNeural"

        # Hinglish / Indian Romanized Speech
        _hinglish_markers = ("kholo", "banao", "chalao", "theek", "accha", "kya", "kaise",
                             "batao", "bhai", "namaste", "shukriya", "madat", "bolo", "karo")
        if any(w in t_lower.split() for w in _hinglish_markers):
            return "en-IN-NeerjaNeural" if is_female else "en-IN-PrabhatNeural"

        # ── 4. Fallback: honour configured voice or English default ──────────
        v_lower = str(self.voice).lower()
        for prefix, (fv, mv) in _LANG_VOICES.items():
            if v_lower.startswith(prefix + "-"):
                return fv if is_female else mv

        return self.voice or ("en-US-JennyNeural" if is_female else "en-US-GuyNeural")

    async def _synth(self, text: str, emotion=None, lang: Optional[str] = None) -> bytes:
        data, _ = await self._synth_with_boundaries(text, emotion=emotion, lang=lang)
        return data

    async def _synth_with_boundaries(self, text: str, emotion=None, lang: Optional[str] = None) -> tuple[bytes, list[dict]]:
        import edge_tts
        v = self._select_voice(text, lang=lang)
        rate, pitch, vol = "+0%", "+0Hz", "+0%"
        if emotion is not None:
            try:
                from core.digital_human import ProsodyPlanner
                rate, pitch, vol = ProsodyPlanner.get_prosody(emotion)
            except Exception:
                pass
        comm = edge_tts.Communicate(text, v, rate=rate, pitch=pitch, volume=vol, boundary="WordBoundary")
        buf  = bytearray()
        boundaries = []
        async for chunk in comm.stream():
            if chunk.get("type") == "audio":
                buf.extend(chunk["data"])
            elif chunk.get("type") == "WordBoundary":
                boundaries.append(chunk)
        return bytes(buf), boundaries

    def _play_with_visemes(self, audio_bytes: bytes, boundaries: list[dict], ui=None, cancel_event: Optional[threading.Event] = None) -> None:
        if cancel_event and cancel_event.is_set():
            return
        import miniaudio
        decoded = miniaudio.decode(
            audio_bytes,
            output_format=miniaudio.SampleFormat.FLOAT32,
            nchannels=1,
        )
        samples = np.array(decoded.samples, dtype=np.float32)
        sr = decoded.sample_rate
        total_duration = len(samples) / float(sr)
        dev = _get_output_device_idx()

        if cancel_event and cancel_event.is_set():
            return

        if ui is not None and hasattr(ui, "push_visemes"):
            try:
                import time
                from core.viseme import text_to_visemes, VISEMES
                hop = 0.02
                n_frames = max(1, int(total_duration / hop))
                frame_vis = ["REST"] * n_frames

                word_items = []
                for b in boundaries:
                    w_text = b.get("text", "")
                    w_offset = b.get("offset", 0) / 1e7
                    w_dur = b.get("duration", 0) / 1e7
                    word_items.append((w_text, w_offset, w_dur))

                for word, w_start, w_dur in word_items:
                    v_list = text_to_visemes(word)
                    if not v_list:
                        continue
                    tot_w = sum(w for _, w in v_list)
                    t_cursor = w_start
                    for v, weight in v_list:
                        v_dur = (weight / tot_w) * w_dur
                        v_end = t_cursor + v_dur
                        f_start = max(0, int(t_cursor / hop))
                        f_end = min(n_frames, int(v_end / hop))
                        for fi in range(f_start, f_end):
                            frame_vis[fi] = v
                        t_cursor = v_end

                frame_size = int(hop * sr)
                frames = []
                for i in range(n_frames):
                    start_sample = i * frame_size
                    end_sample = min(len(samples), (i + 1) * frame_size)
                    chunk = samples[start_sample:end_sample]
                    rms = float(np.sqrt(np.mean(chunk ** 2))) if len(chunk) > 0 else 0.0
                    lvl = min(1.0, rms * 4.5)
                    v_name = frame_vis[i]
                    t_open, t_wide, closure = VISEMES.get(v_name, (0.0, 0.0, 0.0))
                    o = max(0.0, min(1.0, t_open * (1.0 - closure) * (0.5 + 0.5 * lvl)))
                    w = max(-1.0, min(1.0, t_wide))
                    frames.append((lvl, o, w, v_name))

                start_at = time.time() + 0.05
                ui.push_visemes(frames, hop, start_at)
            except Exception as e:
                print(f"[TTS] Viseme timeline error: {e}")

        _safe_play_samples(samples, sr, dev=dev, cancel_event=cancel_event)


# Alias for backward and external compatibility
EdgeTTS = EdgeTTSEngine



# ---------------------------------------------------------------------------
# Kokoro import helper — auto-upgrades on version-mismatch errors
# ---------------------------------------------------------------------------

# Errors that indicate the installed kokoro uses old transformers classes
# (AlbertModel, AutoModel) that are no longer exported at the top level.
_KOKORO_COMPAT_ERRORS = ("AlbertModel", "AutoModel", "cannot import name")


def _import_kokoro_pipeline():
    """Import KPipeline, auto-upgrading kokoro if a version mismatch is found.

    Old kokoro (<0.9) imports AlbertModel / AutoModel from transformers.
    Newer transformers versions no longer export these at the top level,
    causing an ImportError.  kokoro>=0.9 removed these dependencies.

    When the error is detected we:
      1. Upgrade kokoro to >=0.9 via pip (silent, background)
      2. Flush stale kokoro entries from sys.modules
      3. Re-import — this time it should succeed
    """
    import sys

    def _try_import():
        from kokoro import KPipeline  # noqa: PLC0415
        return KPipeline

    try:
        return _try_import()
    except Exception as first_err:
        err_msg = str(first_err)
        if not any(marker in err_msg for marker in _KOKORO_COMPAT_ERRORS):
            # Unrelated error (kokoro not installed, etc.)
            raise RuntimeError(
                f"Kokoro import failed: {first_err}\n"
                "Run: pip install kokoro>=0.9 soundfile"
            ) from first_err

        # ── Version mismatch: upgrade kokoro silently and retry ──────────
        print("[TTS] Kokoro/transformers version mismatch detected — upgrading kokoro…")
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "kokoro>=0.9",
             "--upgrade", "--quiet", "--disable-pip-version-check"],
            capture_output=True,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace").strip()
            raise RuntimeError(
                f"Kokoro auto-upgrade failed: {stderr[:200]}\n"
                "Run manually: pip install kokoro>=0.9 soundfile"
            ) from first_err

        # Flush any stale kokoro submodules from the import cache
        stale = [k for k in sys.modules if k == "kokoro" or k.startswith("kokoro.")]
        for key in stale:
            del sys.modules[key]

        print("[TTS] Kokoro upgraded — retrying import…")
        try:
            return _try_import()
        except Exception as retry_err:
            raise RuntimeError(
                f"Kokoro still broken after upgrade: {retry_err}\n"
                "Run manually: pip install --upgrade kokoro transformers"
            ) from retry_err


# Kokoro voice prefix → KPipeline lang_code mapping
_KOKORO_LANG_CODES = {
    "a": "a",   # American English  (af_*, am_*)
    "b": "b",   # British English   (bf_*, bm_*)
    "j": "j",   # Japanese          (jf_*, jm_*)
    "z": "z",   # Mandarin Chinese  (zf_*, zm_*)
    "s": "s",   # Spanish           (sf_*, sm_*)
    "f": "f",   # French            (ff_*, fm_*)
    "h": "h",   # Hindi             (hf_*, hm_*)
    "i": "i",   # Italian           (if_*, im_*)
    "p": "p",   # Brazilian Portuguese
    "r": "r",   # Russian           (rf_*, rm_*)
    "e": "e",   # German            (ef_*, em_*)
}


class KokoroTTSEngine:
    """Fully offline Kokoro neural TTS.

    Model (~330 MB) is downloaded from HuggingFace on first use,
    then cached locally — subsequent starts load from disk.

    Warmup strategy: _init() runs synchronously in the background
    _do_tts() thread (not the UI thread).  After the pipeline loads,
    a dummy inference compiles the PyTorch JIT graph immediately so
    the first real speak() call has zero compilation overhead.
    """

    def __init__(self, voice: str = "af_heart", speed: float = 1.0):
        self.voice     = voice
        self.speed     = speed
        self._pipeline = None
        self._lock     = threading.Lock()
        self._init()   # blocking, but called from background thread

    @property
    def _lang_code(self) -> str:
        prefix = self.voice[0].lower() if self.voice else "a"
        return _KOKORO_LANG_CODES.get(prefix, "a")

    def _init(self) -> None:
        if self._pipeline is not None:
            return

        lang = self._lang_code

        # Prefer GPU — Kokoro on CUDA is ~10x faster than CPU.
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            if device == "cpu":
                import os as _os
                n_threads = max(1, min(4, (_os.cpu_count() or 4) // 2))
                try:
                    torch.set_num_threads(n_threads)
                    torch.set_num_interop_threads(2)
                except RuntimeError:
                    pass
                print(
                    f"[TTS] Kokoro on CPU — for faster speech install CUDA PyTorch:\n"
                    "      pip install torch --index-url https://download.pytorch.org/whl/cu118"
                )
        except Exception:
            device = "cpu"

        print(f"[TTS] Kokoro — loading (lang='{lang}', device='{device}')…")

        KPipeline = _import_kokoro_pipeline()

        def _create_pipeline():
            try:
                return KPipeline(lang_code=lang, device=device)
            except TypeError:
                return KPipeline(lang_code=lang)   # older build — no device param

        try:
            self._pipeline = _create_pipeline()
        except Exception as _first_err:
            # Offline flag set but model not cached yet → clear flags and download once.
            # Keywords cover multiple huggingface_hub error message variants across versions.
            _e = str(_first_err).lower()
            _offline_keywords = (
                "offline", "not found", "cache", "localentry",
                "does not exist", "outgoing", "local_files_only",
            )
            if any(k in _e for k in _offline_keywords):
                print("[TTS] Kokoro model not in local cache — downloading (one-time, internet required)…")
                os.environ.pop("HF_HUB_OFFLINE",      None)
                os.environ.pop("TRANSFORMERS_OFFLINE", None)
                os.environ.pop("HF_DATASETS_OFFLINE",  None)
                try:
                    self._pipeline = _create_pipeline()
                except Exception as _dl_err:
                    raise RuntimeError(
                        f"Kokoro model download failed.\n"
                        f"Internet access is required the first time to download the voice model (~330 MB).\n"
                        f"After the first download it runs fully offline.\n"
                        f"Tip: Switch to EdgeTTS (free, no download) in the Configure panel if offline.\n"
                        f"Details: {_dl_err}"
                    ) from _dl_err
            else:
                raise

        print("[TTS] Kokoro compiling (first-time only)…")
        # Warmup: compiles PyTorch JIT graph so first real speak() call is instant.
        try:
            for _ in self._pipeline("hello", voice=self.voice, speed=self.speed):
                pass
            print("[TTS] Kokoro ready.")
        except Exception as e:
            print(f"[TTS] Kokoro warmup warning: {e}")

    def speak(self, text: str) -> None:
        with self._lock:
            if self._pipeline is None:
                self._init()

        # ── Concurrent synthesise + playback ────────────────────────────────
        # Kokoro generates audio chunks lazily.  Without threading, we:
        #   synthesise chunk N → play N → synthesise N+1 → play N+1 …
        # With a producer/consumer pair, chunk N+1 synthesises WHILE chunk N
        # plays, cutting perceived latency by the playback duration of all but
        # the last chunk (typically 1-3 s on multi-sentence responses).
        audio_q: "_queue.Queue[np.ndarray | None]" = _queue.Queue(maxsize=4)
        synth_error: list[Exception] = []

        def _synth():
            try:
                for _, _, audio in self._pipeline(text, voice=self.voice, speed=self.speed):
                    if audio is not None:
                        arr = _to_numpy(audio)
                        arr = _compress_silence(arr)
                        if arr.size > 0:
                            audio_q.put(arr)          # blocks if player is slow (backpressure)
            except Exception as exc:
                synth_error.append(exc)
            finally:
                audio_q.put(None)                     # sentinel → player exits

        synth_thread = threading.Thread(target=_synth, daemon=True)
        synth_thread.start()

        # Player runs in this thread so sd.wait() doesn't block the synth thread.
        while True:
            arr = audio_q.get()
            if arr is None:
                break
            _play_np(arr, 24000)

        synth_thread.join()

        if synth_error:
            raise synth_error[0]


class ElevenLabsTTSEngine:
    """ElevenLabs cloud TTS – supports low-latency streaming and custom cloned voice IDs."""

    def __init__(self, api_key: str, voice_id: str = "pNInz6obpgDQGcFmaJgB", model_id: str = "eleven_turbo_v2_5"):
        self.api_key  = api_key
        self.voice_id = voice_id or "pNInz6obpgDQGcFmaJgB"
        self.model_id = model_id or "eleven_turbo_v2_5"

    def speak(self, text: str) -> None:
        import requests
        headers = {
            "xi-api-key":   self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text":     text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": 0.45,
                "similarity_boost": 0.80,
                "use_speaker_boost": True
            },
        }
        # Use stream endpoint for ultra-fast time-to-first-byte
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream?optimize_streaming_latency=4"
        resp = requests.post(url, json=payload, headers=headers, stream=True, timeout=20)
        resp.raise_for_status()
        
        # Buffer and play
        audio_data = bytearray()
        for chunk in resp.iter_content(chunk_size=4096):
            if chunk:
                audio_data.extend(chunk)
        if audio_data:
            _play_audio_bytes(bytes(audio_data))



# ---------------------------------------------------------------------------
# Thread-safe player wrapper
# ---------------------------------------------------------------------------

class TTSPlayer:
    """
    Wraps any *Engine. Exposes a blocking speak() method
    meant to be called from a dedicated background thread.
    """

    def __init__(self, engine):
        self._engine  = engine
        self._playing = False
        self._lock    = threading.Lock()
        self._stop_event = threading.Event()

    @property
    def is_playing(self) -> bool:
        return self._playing

    def speak(
        self,
        text:     str,
        on_start: Optional[Callable] = None,
        on_done:  Optional[Callable] = None,
    ) -> None:
        """Synthesise and play text. BLOCKING – call from a dedicated thread."""
        import time as _t
        t0 = _t.monotonic()
        try:
            with self._lock:
                self._stop_event.clear()
                self._playing = True
            if on_start:
                on_start()
            if hasattr(self._engine, "speak"):
                try:
                    self._engine.speak(text, cancel_event=self._stop_event)
                except TypeError:
                    self._engine.speak(text)
        except Exception as e:
            print(f"[TTS] Error: {e}")
        finally:
            elapsed = max(0.0, _t.monotonic() - t0)
            try:
                from engine.commercial.core import get_commercial_engine
                get_commercial_engine().usage_meter.record_active_seconds(elapsed)
            except Exception:
                pass
            with self._lock:
                self._playing = False
            if on_done:
                on_done()

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            self._playing = False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_tts_player(config: dict) -> TTSPlayer:
    engine_name = config.get("tts_engine", "edgetts").lower()
    if engine_name == "kokoro":
        voice  = config.get("tts_voice", "af_heart")
        speed  = float(config.get("tts_speed", 1.0))
        engine = KokoroTTSEngine(voice=voice, speed=speed)
    elif engine_name == "elevenlabs":
        api_key  = config.get("elevenlabs_api_key", "")
        voice_id = config.get("tts_voice", "pNInz6obpgDQGcFmaJgB")
        engine   = ElevenLabsTTSEngine(api_key=api_key, voice_id=voice_id)
    elif engine_name in ("sapi", "sapi5", "windows"):
        voice  = config.get("tts_voice", "en-US-GuyNeural")
        engine = WindowsSAPITTSEngine(voice=voice)
    else:   # edgetts (default)
        voice  = config.get("tts_voice", "en-US-GuyNeural")
        engine = EdgeTTSEngine(voice=voice)
    return TTSPlayer(engine)


# Global alias for engine/voice compatibility
EdgeTTS = EdgeTTSEngine

