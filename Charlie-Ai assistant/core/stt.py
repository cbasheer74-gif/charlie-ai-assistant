"""
Speech-to-Text engines for MARK XL.

Whisper  – offline transcription via faster-whisper (VAD-buffered)
Vosk     – offline streaming transcription (lighter)
"""
import json
import numpy as np


def is_stt_hallucination(text: str) -> bool:
    """Detects Whisper silence/noise hallucinations (repetitive words, subtitle credits, stray loops)."""
    if not text or not str(text).strip():
        return True
    import re
    t = str(text).strip()
    words = re.findall(r"\b\w+\b", t.lower())
    if not words:
        return True

    # 1. Repeated identical word / token loop (e.g. 'Indian, Indian, Indian...', 'you you you')
    if re.search(r"(\b\w+\b)(?:[,\s\-]+(?:\1\b)){2,}", t, re.I):
        return True

    # 2. Unnatural vocabulary repetition ratio for phrases >= 4 words
    if len(words) >= 4 and (len(set(words)) / len(words)) < 0.45:
        return True

    # 3. Known standard Whisper silence artifacts on empty / static audio
    cleaned = t.lower().strip(" .!?,:;\"'")
    _ARTIFACTS = {
        "thank you", "thanks for watching", "subtitles by", "amara.org",
        "subscribe", "you", "english", "indian", "english, indian", "bye", "okay",
        "silence", "pause", "music", "applause",
    }
    if cleaned in _ARTIFACTS:
        return True
    return False


class WhisperSTT:
    """Offline transcription using faster-whisper."""

    def __init__(self, model_name: str = "base", language: str | None = None, vocabulary_manager: object = None):
        import os
        from faster_whisper import WhisperModel
        print(f"[STT] Loading Whisper '{model_name}'…")
        try:
            import torch
            device  = "cuda" if torch.cuda.is_available() else "cpu"
            compute = "float16" if device == "cuda" else "int8"
        except Exception:
            device, compute = "cpu", "int8"

        try:
            self._model = WhisperModel(model_name, device=device, compute_type=compute)
        except Exception as _first_err:
            _e = str(_first_err).lower()
            _offline_keywords = (
                "offline", "not found", "cache", "localentry",
                "does not exist", "outgoing", "local_files_only",
            )
            if any(k in _e for k in _offline_keywords):
                print(f"[STT] Whisper '{model_name}' not in local cache — downloading (one-time, internet required)…")
                os.environ.pop("HF_HUB_OFFLINE",      None)
                os.environ.pop("TRANSFORMERS_OFFLINE", None)
                os.environ.pop("HF_DATASETS_OFFLINE",  None)
                try:
                    self._model = WhisperModel(model_name, device=device, compute_type=compute)
                except Exception as _dl_err:
                    raise RuntimeError(
                        f"Whisper '{model_name}' model download failed.\n"
                        f"Internet access is required the first time to download the speech model (~75–290 MB).\n"
                        f"After the first download it runs fully offline.\n"
                        f"Details: {_dl_err}"
                    ) from _dl_err
            else:
                raise

        self._auto_detect = True  # True when user chose 'auto'
        if not language or language.strip().lower() in ("auto", ""):
            self._language = None
            self._auto_detect = True
        else:
            try:
                from core.languages import get_whisper_code
                self._language = get_whisper_code(language)
            except Exception:
                self._language = language.strip().lower()
            self._auto_detect = False

        self._vocab_mgr = vocabulary_manager
        if self._vocab_mgr is None:
            try:
                from engine.voice.stt import VocabularyContextManager
                self._vocab_mgr = VocabularyContextManager()
            except Exception:
                self._vocab_mgr = None

        # Build language-specific Whisper vocabulary prompt
        self._initial_prompt = self._build_initial_prompt(self._language, self._vocab_mgr)
        print(f"[STT] Whisper '{model_name}' ready ({device}, lang={self._language or 'auto'})")

    def set_language(self, language: str | None) -> None:
        """Hot-swap the Whisper language hint without reloading the model."""
        if not language or language.strip().lower() in ("auto", ""):
            self._language = None
            self._auto_detect = True
        else:
            try:
                from core.languages import get_whisper_code
                self._language = get_whisper_code(language)
            except Exception:
                self._language = language.strip().lower()
        self._auto_detect = False
        self._initial_prompt = self._build_initial_prompt(self._language, self._vocab_mgr)
        print(f"[STT] Language updated → {self._language or 'auto'}")

    @staticmethod
    def _build_initial_prompt(whisper_code: str | None, vocab_mgr: object = None) -> str:
        """Return domain vocabulary in the target language so Whisper has a strong
        prior for names, technical terms, and common filler words.
        English terms (Charlie, VS Code, Python…) are appended to every prompt
        since they appear in any language context.
        """
        _BASE = "Charlie, VS Code, GitHub, Python, YouTube, Windows, AI, OK."
        if vocab_mgr and hasattr(vocab_mgr, "get_prompt_context"):
            try:
                v_ctx = vocab_mgr.get_prompt_context()
                if v_ctx:
                    _BASE = v_ctx
            except Exception:
                pass
        _PROMPTS: dict[str, str] = {
            # South Asian
            "hi":  "चार्ली, पाइथन, गिटहब, विंडोज़, यूट्यूब, ठीक है, हाँ, नहीं। " + _BASE,
            "mr":  "चार्ली, पायथन, गिटहब, विंडोज, यूट्यूब, ठीक आहे, हो, नाही। " + _BASE,
            "bn":  "চার্লি, পাইথন, গিটহাব, উইন্ডোজ, ইউটিউব, ঠিক আছে, হ্যাঁ, না। " + _BASE,
            "ta":  "சார்லி, பைதான், கிட்ஹப், விண்டோஸ், யூடியூப், சரி, ஆம், இல்லை। " + _BASE,
            "te":  "చార్లీ, పైతాన్, గిట్‌హబ్, విండోస్, యూట్యూబ్, సరే, అవును, కాదు। " + _BASE,
            "gu":  "ચાર્લી, પાઇથન, ગિટહબ, વિન્ડોઝ, યુટ્યુબ, ઠીક છે, હા, ના। " + _BASE,
            "kn":  "ಚಾರ್ಲಿ, ಪೈಥಾನ್, ಗಿಟ್‌ಹಬ್, ವಿಂಡೋಸ್, ಯೂಟ್ಯೂಬ್, ಸರಿ, ಹೌದು, ಇಲ್ಲ। " + _BASE,
            "ml":  "ചാർലി, പൈത്തൺ, ഗിറ്റ്ഹബ്, വിൻഡോസ്, യൂട്യൂബ്, ശരി, അതെ, ഇല്ല। " + _BASE,
            "pa":  "ਚਾਰਲੀ, ਪਾਇਥਨ, ਗਿੱਟਹੱਬ, ਵਿੰਡੋਜ਼, ਯੂਟਿਊਬ, ਠੀਕ ਹੈ, ਹਾਂ, ਨਹੀਂ। " + _BASE,
            "ur":  "چارلی، پائتھن، گٹ ہب، ونڈوز، یوٹیوب، ٹھیک ہے، ہاں، نہیں۔ " + _BASE,
            "or":  "ଚାର୍ଲି, ପାଇଥନ, ଗିଟ୍‌ହବ, ୱିଣ୍ଡୋଜ, ୟୁଟ୍ୟୁବ, ଠିକ ଅଛି, ହଁ, ନାହିଁ। " + _BASE,
            "as":  "চাৰ্লি, পাইথন, গিটহাব, উইণ্ড'জ, ইউটিউব, ঠিক আছে, হয়, নহয়। " + _BASE,
            "ne":  "चार्ली, पाइथन, गिटहब, विन्डोज, युट्युब, ठीक छ, हो, होइन। " + _BASE,
            "si":  "චාලී, පයිතන්, ගිට්හබ්, වින්ඩෝස්, යූටියුබ්, හරි, ඔව්, නෑ। " + _BASE,
            # East/SE Asian
            "zh":  "查理，Python，GitHub，Windows，YouTube，好的，是，不。" + _BASE,
            "ja":  "チャーリー、パイソン、ギットハブ、ウィンドウズ、ユーチューブ、はい、いいえ、わかった。" + _BASE,
            "ko":  "찰리, 파이썬, 깃허브, 윈도우, 유튜브, 네, 아니요, 알겠습니다. " + _BASE,
            "th":  "ชาร์ลี, ไพธอน, กิตฮับ, วินโดวส์, ยูทูบ, ตกลง, ใช่, ไม่. " + _BASE,
            "vi":  "Charlie, Python, GitHub, Windows, YouTube, được, vâng, không. " + _BASE,
            "id":  "Charlie, Python, GitHub, Windows, YouTube, oke, ya, tidak. " + _BASE,
            "ms":  "Charlie, Python, GitHub, Windows, YouTube, okay, ya, tidak. " + _BASE,
            # Middle East
            "ar":  "تشارلي، بايثون، جيت هاب، ويندوز، يوتيوب، حسناً، نعم، لا. " + _BASE,
            "fa":  "چارلی، پایتون، گیت‌هاب، ویندوز، یوتیوب، باشه، بله، نه. " + _BASE,
            "he":  "צ'רלי, פייתון, גיטהאב, ווינדוס, יוטיוב, בסדר, כן, לא. " + _BASE,
            # European
            "es":  "Charlie, Python, GitHub, Windows, YouTube, de acuerdo, sí, no. " + _BASE,
            "fr":  "Charlie, Python, GitHub, Windows, YouTube, d'accord, oui, non. " + _BASE,
            "de":  "Charlie, Python, GitHub, Windows, YouTube, okay, ja, nein. " + _BASE,
            "it":  "Charlie, Python, GitHub, Windows, YouTube, va bene, sì, no. " + _BASE,
            "pt":  "Charlie, Python, GitHub, Windows, YouTube, tudo bem, sim, não. " + _BASE,
            "ru":  "Чарли, Питон, Гитхаб, Виндоус, Ютуб, хорошо, да, нет. " + _BASE,
            "uk":  "Чарлі, Пайтон, Гітхаб, Віндоус, Ютуб, добре, так, ні. " + _BASE,
            "pl":  "Charlie, Python, GitHub, Windows, YouTube, okej, tak, nie. " + _BASE,
            "tr":  "Charlie, Python, GitHub, Windows, YouTube, tamam, evet, hayır. " + _BASE,
            "nl":  "Charlie, Python, GitHub, Windows, YouTube, oké, ja, nee. " + _BASE,
            "sw":  "Charlie, Python, GitHub, Windows, YouTube, sawa, ndiyo, hapana. " + _BASE,
            "am":  "ቻርሊ, ፓይቶን, ጊትሃብ, ዊንዶውስ, ዩቲዩብ, እሺ, አዎ, አይ. " + _BASE,
        }
        if not whisper_code:
            return _BASE
        return _PROMPTS.get(whisper_code.lower(), _BASE)

    def transcribe(
        self,
        audio: np.ndarray,
        beam_size: int = 5,
        vocabulary_context: str = "",
        initial_prompt: str | None = None,
    ) -> str:
        """Transcribe a float32 mono 16 kHz numpy array with energy gating and anti-hallucination validation."""
        if audio is None or len(audio) < 8000:
            return ""

        # Energy gate: ignore near-silence, mic hiss, and ambient noise
        try:
            audio_f32 = audio.astype(np.float32)
            rms = float(np.sqrt(np.mean(audio_f32 ** 2)))
            if rms < 0.012:
                return ""
        except Exception:
            pass

        # Determine effective initial prompt
        effective_prompt = initial_prompt
        if not effective_prompt:
            if vocabulary_context:
                combined = f"{self._initial_prompt}, {vocabulary_context}".strip(", ")
                effective_prompt = combined[:450]
            else:
                effective_prompt = self._initial_prompt

        try:
            segments, _ = self._model.transcribe(
                audio,
                language=self._language,
                beam_size=beam_size,
                best_of=beam_size,
                initial_prompt=effective_prompt,
                condition_on_previous_text=False,
                temperature=0.0,
                compression_ratio_threshold=2.2,
                log_prob_threshold=-0.8,
                no_speech_threshold=0.6,
                vad_filter=True,
                vad_parameters={
                    "min_silence_duration_ms": 600,
                    "speech_pad_ms": 400,
                },
            )
            raw = " ".join(s.text for s in segments).strip()

            # Reject repetitive or standard silence hallucinations
            if is_stt_hallucination(raw):
                return ""

            # If language not explicitly Chinese/Japanese/Korean, strip CJK hallucinations on noisy speech
            if not self._language or self._language not in ("zh", "ja", "ko", "chinese", "japanese", "korean", "yue", "zh-tw"):
                import re
                if re.search(r"[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u30ff\uac00-\ud7af]", raw):
                    raw = re.sub(r"[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u30ff\uac00-\ud7af]+", "", raw).strip()

            if is_stt_hallucination(raw):
                return ""

            # Auto-detect script and confirm/update Whisper language hint dynamically
            if self._auto_detect and len(raw) > 8:
                try:
                    from core.languages import detect_language_script
                    detected = detect_language_script(raw)
                    if detected and detected.whisper_code and detected.whisper_code != self._language:
                        self._language = detected.whisper_code
                        print(f"[STT] Script auto-detected → {detected.name} ({detected.whisper_code})")
                except Exception:
                    pass

            return raw
        except Exception as e:
            print(f"[STT] Transcription error: {e}")
            raise


class VoskSTT:
    """Streaming transcription using Vosk."""

    def __init__(self, model_path: str | None = None, language: str = "en-us"):
        from vosk import Model, KaldiRecognizer
        print("[STT] Loading Vosk model…")
        if model_path:
            model = Model(model_path)
        else:
            lang  = language.strip().lower() if language and language.strip().lower() != "auto" else "en-us"
            model = Model(lang=lang)
        self._rec = KaldiRecognizer(model, 16000)
        print("[STT] Vosk ready.")

    def process_chunk(self, audio_bytes: bytes) -> tuple[str, bool]:
        """Feed raw int16 LE PCM bytes. Returns (text, is_final)."""
        if self._rec.AcceptWaveform(audio_bytes):
            result = json.loads(self._rec.Result())
            return result.get("text", ""), True
        partial = json.loads(self._rec.PartialResult())
        return partial.get("partial", ""), False
