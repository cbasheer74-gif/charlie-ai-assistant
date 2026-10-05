# -*- coding: utf-8 -*-
# engine/voice/user_greeter.py
"""
Smart session greeter for Charlie.

On every app start:
  1. Greets user by name with time-appropriate salutation
  2. Asks language preference (first time only OR if unknown)
  3. Stores preference — no repeated asking once set
  4. On language switch during a session: confirms once, then switches silently
  5. Recognizes returning voices and addresses users by name

Language state machine:
  UNKNOWN  -> asks preference on login
  SET      -> Charlie speaks in preferred language; detects switches
  SWITCHED -> confirms the switch once, then silent
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional


# ── Storage path ─────────────────────────────────────────────────────────────
def _cfg_dir() -> Path:
    from core.app_paths import get_config_dir
    return get_config_dir()


def _lang_pref_file() -> Path:
    return _cfg_dir() / "lang_pref.json"


# ── Greeting helpers ─────────────────────────────────────────────────────────

def _time_salutation(hour: Optional[int] = None) -> str:
    if hour is None:
        hour = datetime.now().hour
    if 5 <= hour < 12:
        return "Good morning"
    if 12 <= hour < 17:
        return "Good afternoon"
    if 17 <= hour < 21:
        return "Good evening"
    return "Good night"


def _hindi_salutation(hour: Optional[int] = None) -> str:
    if hour is None:
        hour = datetime.now().hour
    if 5 <= hour < 12:
        return "Suprabhat"          # Good morning
    if 12 <= hour < 17:
        return "Namaskar"           # Good afternoon
    if 17 <= hour < 21:
        return "Shubh sandhya"      # Good evening
    return "Shubh ratri"            # Good night


# ── Language preference store ────────────────────────────────────────────────

class LangPreference:
    """
    Persists language preference per user so Charlie never asks again.
    Stored in config/lang_pref.json  —  { "<user_id>": "auto" | "en" | "hi" | "mr" | ... }
    """
    _lock = threading.Lock()

    try:
        from core.languages import get_all_language_keys
        SUPPORTED = get_all_language_keys()
    except Exception:
        SUPPORTED = {
            "auto", "en", "hi", "hinglish",
            "mr", "bn", "ta", "te", "gu", "kn", "ml", "pa", "ur", "or", "as",
            "es", "fr", "de", "it", "pt", "ru", "ja", "zh", "ko", "ar",
            "marathi", "bengali", "tamil", "telugu", "gujarati", "kannada",
            "malayalam", "punjabi", "urdu", "odia", "assamese",
            "spanish", "french", "german", "italian", "portuguese",
            "russian", "japanese", "chinese", "mandarin", "korean", "arabic",
        }

    def __init__(self):
        self._file = _lang_pref_file()

    def _load(self) -> dict:
        try:
            if self._file.exists():
                return json.loads(self._file.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save(self, data: dict) -> None:
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            self._file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def get(self, user_id: str) -> Optional[str]:
        with self._lock:
            return self._load().get(user_id)

    def set(self, user_id: str, lang: str) -> None:
        val = lang.lower().strip()
        if val not in self.SUPPORTED:
            val = "auto"
        with self._lock:
            data = self._load()
            data[user_id] = val
            self._save(data)

    def clear(self, user_id: str) -> None:
        with self._lock:
            data = self._load()
            data.pop(user_id, None)
            self._save(data)


_lang_pref = LangPreference()


# ── Language Detection Helpers ───────────────────────────────────────────────

_MARATHI_WORDS = {
    "marathi", "मराठी", "marathi mein", "marathit", "marathi madhe",
    "marathit bola", "marathi bolo", "mala marathi",
}

_BENGALI_WORDS = {
    "bengali", "bangla", "বাংলা", "bengali mein", "banglay",
    "bangla bolo", "bangla bolein", "bangla bolun", "banglay kotha",
}

_TAMIL_WORDS = {
    "tamil", "தமிழ்", "tamilil", "tamilil pesu", "tamil pesu",
    "tamilil pesunga", "tamil please", "tamil mein",
}

_TELUGU_WORDS = {
    "telugu", "తెలుగు", "telugulo", "telugulo matladu", "telugu matladu",
    "telugu please", "telugu mein",
}

_GUJARATI_WORDS = {
    "gujarati", "ગુજરાતી", "gujaratima", "gujarati ma", "gujaratima bolo",
    "gujarati bolo", "gujarati mein",
}

_KANNADA_WORDS = {
    "kannada", "ಕನ್ನಡ", "kannadadalli", "kannada matadi", "kannadalli",
    "kannada mein", "kannada please",
}

_MALAYALAM_WORDS = {
    "malayalam", "മലയാളം", "malayalam samsariku", "malayalathil",
    "malayalam mein", "malayalam please",
}

_PUNJABI_WORDS = {
    "punjabi", "ਪੰਜਾਬੀ", "punjabi vich", "punjabi ch", "punjabi bolo",
    "punjabi mein", "punjabi please",
}

_URDU_WORDS = {
    "urdu", "اردو", "urdu mein", "urdu me", "urdu bolo", "urdu mein baat",
    "urdu please",
}

_ODIA_WORDS = {
    "odia", "oriya", "ଓଡ଼ିଆ", "odia re", "odia katha", "odia mein",
}

_ASSAMESE_WORDS = {
    "assamese", "অসমীয়া", "oxomiya", "asamiya", "assamese mein",
}

_HINDI_WORDS = {
    "hindi", "हिन्दी", "hindi mein", "hindi me", "hindhi",
    "hindi bolein", "hindi bolo", "hindi mein baat",
    "mujhe hindi", "hindi chahiye", "hindi prefer",
}

_ENGLISH_WORDS = {
    "english", "english mein", "english me",
    "in english", "speak english", "english please",
    "switch to english", "let's switch", "english prefer",
    "english chahiye", "english hi",
}

_HINGLISH_WORDS = {
    "hinglish", "hinglish mein", "mix", "mixing",
    "half half", "thoda hindi thoda english",
}

# Regional & International script regexes
_REGIONAL_SCRIPTS = [
    (re.compile(r"[\u3040-\u30ff]"), "ja"),  # Hiragana / Katakana -> Japanese
    (re.compile(r"[\uac00-\ud7af]"), "ko"),  # Hangul -> Korean
    (re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]"), "zh"),  # CJK Ideographs -> Chinese
    (re.compile(r"[\u0400-\u04ff]"), "ru"),  # Cyrillic -> Russian
    (re.compile(r"[\u0980-\u09FF]"), "bn"),  # Bengali / Assamese
    (re.compile(r"[\u0A00-\u0A7F]"), "pa"),  # Gurmukhi / Punjabi
    (re.compile(r"[\u0A80-\u0AFF]"), "gu"),  # Gujarati
    (re.compile(r"[\u0B00-\u0B7F]"), "or"),  # Odia
    (re.compile(r"[\u0B80-\u0BFF]"), "ta"),  # Tamil
    (re.compile(r"[\u0C00-\u0C7F]"), "te"),  # Telugu
    (re.compile(r"[\u0C80-\u0CFF]"), "kn"),  # Kannada
    (re.compile(r"[\u0D00-\u0D7F]"), "ml"),  # Malayalam
    (re.compile(r"[\u0600-\u06FF]"), "ur"),  # Urdu / Arabic
]


def detect_lang_from_response(text: str) -> Optional[str]:
    """
    Returns language code ('auto', 'en', 'hi', 'hinglish', 'mr', 'bn',
    'ta', 'te', 'gu', 'kn', 'ml', 'pa', 'ur', 'or', 'as', 'es', 'fr',
    'de', 'it', 'pt', 'ru', 'ja', 'zh', 'ko', 'ar') if detected.
    """
    if not text:
        return None
    t = text.lower().strip()

    # Core languages detection helper
    try:
        from core.languages import detect_language_script, resolve_language
        script_detected = detect_language_script(text)
        if script_detected:
            return script_detected.code
        matched_info = resolve_language(t)
        if matched_info:
            return matched_info.code
    except Exception:
        pass

    # Native scripts
    for pattern, code in _REGIONAL_SCRIPTS:
        if pattern.search(text):
            return code

    # Indian Regional word sets
    if any(w in t for w in _MARATHI_WORDS): return "mr"
    if any(w in t for w in _BENGALI_WORDS): return "bn"
    if any(w in t for w in _TAMIL_WORDS):   return "ta"
    if any(w in t for w in _TELUGU_WORDS):  return "te"
    if any(w in t for w in _GUJARATI_WORDS): return "gu"
    if any(w in t for w in _KANNADA_WORDS):  return "kn"
    if any(w in t for w in _MALAYALAM_WORDS): return "ml"
    if any(w in t for w in _PUNJABI_WORDS):  return "pa"
    if any(w in t for w in _URDU_WORDS):     return "ur"
    if any(w in t for w in _ODIA_WORDS):     return "or"
    if any(w in t for w in _ASSAMESE_WORDS): return "as"

    # Hindi / Hinglish / English
    if any(w in t for w in _HINGLISH_WORDS): return "hinglish"
    if any(w in t for w in _HINDI_WORDS):    return "hi"
    if any(w in t for w in _ENGLISH_WORDS):  return "en"

    # European & Asian Keywords
    if any(w in t for w in ("spanish", "español", "espanol")): return "es"
    if any(w in t for w in ("french", "français", "francais")): return "fr"
    if any(w in t for w in ("german", "deutsch")): return "de"
    if any(w in t for w in ("italian", "italiano")): return "it"
    if any(w in t for w in ("portuguese", "português", "portugues")): return "pt"
    if any(w in t for w in ("russian", "русский")): return "ru"
    if any(w in t for w in ("japanese", "日本語", "nihongo")): return "ja"
    if any(w in t for w in ("chinese", "mandarin", "中文")): return "zh"
    if any(w in t for w in ("korean", "한국어", "hangul")): return "ko"
    if any(w in t for w in ("arabic", "العربية")): return "ar"

    if "auto" in t or "any" in t or "both" in t or "kuch bhi" in t:
        return "auto"

    return None


def detect_lang_switch(text: str, current_lang: str) -> Optional[str]:
    """
    Detects if the user explicitly asks to switch language.
    Returns the new language code if a switch was requested, else None.
    """
    if not text:
        return None
    t = text.lower().strip()

    # Look for explicit switch commands
    _switch_triggers = (
        "switch to", "speak in", "talk in", "change language to", "can you speak",
        "start speaking", "switch language", "mein baat karo", "me baat karo",
        "mein bolo", "me bolo", "bola", "pesu", "matladu", "samsariku",
    )
    is_switch_req = any(trig in t for trig in _switch_triggers)

    detected = detect_lang_from_response(t)
    if detected and (is_switch_req or detected != current_lang):
        return detected

    return None


def detect_hindi_speech(text: str) -> bool:
    """Detect if input contains Hindi Devanagari script or common Hindi/Hinglish vocabulary."""
    if not text:
        return False
    # Check Devanagari script
    if re.search(r"[\u0900-\u097F]", text):
        return True
    # Check Hinglish keywords
    hinglish_words = {
        "kholo", "banao", "chalao", "ruko", "band", "karo", "aaj", "mera", "meri", "ye", "wo",
        "kaise", "sach", "hai", "kya", "nahi", "theek", "accha", "bolo", "kaha", "idhar",
        "namaste", "shukriya", "bhai", "didi", "chahiye", "batao", "sunao", "madat"
    }
    words = set(re.findall(r"\w+", text.lower()))
    return len(words.intersection(hinglish_words)) >= 1


# ── Greeting builder ─────────────────────────────────────────────────────────

def build_greeting(
    user_name: str,
    lang: Optional[str] = "auto",
    assistant_name: str = "Charlie",
    is_returning: bool = False,
    last_topic: str = "",
) -> str:
    """
    Builds the natural start-of-session greeting for Charlie.
    """
    name = user_name.strip() if user_name.strip() and user_name.lower() not in ("", "primary user") else ""
    sal = _time_salutation()
    address = f", {name}!" if name else "!"

    if is_returning and last_topic:
        return (
            f"Welcome back{address} I am {assistant_name}, all systems ready. "
            f"Ready to continue with {last_topic}, or start something new?"
        )
    return (
        f"{sal}{address} I am {assistant_name}, all systems ready. "
        f"How may I assist you today?"
    )


def build_language_confirm(new_lang: str, assistant_name: str = "Charlie") -> str:
    """Natural confirmation message when switching languages."""
    lang_lower = str(new_lang).lower()
    if lang_lower in ("mr", "marathi"):
        return "नक्कीच, मी मराठीत बोलेन. (Switching to Marathi)"
    if lang_lower in ("bn", "bengali"):
        return "অবশ্যই, আমি বাংলায় কথা বলছি। (Switching to Bengali)"
    if lang_lower in ("gu", "gujarati"):
        return "ચોક્કસ, હું ગુજરાતીમાં બોલીશ. (Switching to Gujarati)"
    if lang_lower in ("ta", "tamil"):
        return "நிச்சயமாக, நான் தமிழில் பேசுகிறேன். (Switching to Tamil)"
    if lang_lower in ("te", "telugu"):
        return "ఖచ్చితంగా, నేను తెలుగులో మాట్లాడతాను. (Switching to Telugu)"
    if lang_lower in ("kn", "kannada"):
        return "ಖಂಡಿತ, ನಾನು ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡುತ್ತೇನೆ. (Switching to Kannada)"
    if lang_lower in ("ml", "malayalam"):
        return "തീർച്ചയായും, ഞാൻ മലയാളത്തിൽ സംസാരിക്കാം. (Switching to Malayalam)"
    if lang_lower in ("pa", "punjabi"):
        return "ਜ਼ਰੂਰ, ਮੈਂ ਪੰਜਾਬੀ ਵਿੱਚ ਬੋਲਾਂਗਾ। (Switching to Punjabi)"
    if lang_lower in ("ur", "urdu"):
        return "ضرور، میں اردو میں بات کروں گا۔ (Switching to Urdu)"
    if lang_lower in ("or", "odia"):
        return "ନିଶ୍ଚୟ, ମୁଁ ଓଡ଼ିଆରେ କହିବି। (Switching to Odia)"
    if lang_lower in ("as", "assamese"):
        return "নিশ্চয়, মই অসমীয়াত কম। (Switching to Assamese)"
    if lang_lower in ("hi", "hindi"):
        return "हाँ, अब हम हिन्दी में बात करेंगे। I am switching to Hindi."
    if lang_lower in ("hinglish",):
        return "Haan bilkul, Hinglish mein baat karte hain."
    if lang_lower in ("es", "spanish"):
        return "¡Por supuesto! Hablaremos en español. (Switching to Spanish)"
    if lang_lower in ("fr", "french"):
        return "Bien sûr! Je parlerai en français. (Switching to French)"
    if lang_lower in ("de", "german"):
        return "Natürlich! Ich werde Deutsch sprechen. (Switching to German)"
    if lang_lower in ("it", "italian"):
        return "Certamente! Parlerò in italiano. (Switching to Italian)"
    if lang_lower in ("pt", "portuguese"):
        return "Com certeza! Falarei em português. (Switching to Portuguese)"
    if lang_lower in ("ru", "russian"):
        return "Конечно! Я буду говорить по-русски. (Switching to Russian)"
    if lang_lower in ("zh", "chinese"):
        return "好的，我将使用中文交流。(Switching to Chinese)"
    if lang_lower in ("ja", "japanese"):
        return "かしこまりました。日本語で対応いたします。(Switching to Japanese)"
    if lang_lower in ("ko", "korean"):
        return "알겠습니다. 한국어로 대화하겠습니다。(Switching to Korean)"
    if lang_lower in ("ar", "arabic"):
        return "بالتأكيد، سأتحدث باللغة العربية. (Switching to Arabic)"
    if lang_lower in ("auto",):
        return "Auto language detection active. I will mirror your spoken language."

    return f"Understood, switching to {new_lang.title()}."


def build_unclear_audio_message(lang: str = "en") -> str:
    """Professional 'I didn't hear you' message for all supported languages."""
    lang_lower = str(lang).lower()
    if lang_lower in ("mr", "marathi"):
        return "माफ करा, मला स्पष्ट ऐकू आले नाही. कृपया पुन्हा सांगाल का?"
    if lang_lower in ("bn", "bengali"):
        return "দুঃখিত, আমি স্পষ্ট শুনতে পাইনি। দয়া করে আবার বলবেন কি?"
    if lang_lower in ("gu", "gujarati"):
        return "માફ કરશો, મને બરાબર સંભળાયું નહીં. શું તમે ફરીથી કહી શકશો?"
    if lang_lower in ("ta", "tamil"):
        return "மன்னிக்கவும், எனக்கு தெளிவாக கேட்கவில்லை. தயவுசெய்து மீண்டும் சொல்வீர்களா?"
    if lang_lower in ("te", "telugu"):
        return "క్షమించండి, నాకు స్పష్టంగా వినబడలేదు. దయచేసి మళ్లీ చెబుతారా?"
    if lang_lower in ("kn", "kannada"):
        return "ಕ್ಷಮಿಸಿ, ನನಗೆ ಸ್ಪಷ್ಟವಾಗಿ ಕೇಳಿಸಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಇನ್ನೊಮ್ಮೆ ಹೇಳುತ್ತೀರಾ?"
    if lang_lower in ("ml", "malayalam"):
        return "ക്ഷമിക്കണം, എനിക്ക് വ്യക്തമായി കേട്ടില്ല. ദയവായി വീണ്ടും പറയാമോ?"
    if lang_lower in ("pa", "punjabi"):
        return "ਮਾਫ਼ ਕਰਨਾ, ਮੈਨੂੰ ਸਾਫ਼ ਸੁਣਾਈ ਨਹੀਂ ਦਿੱਤਾ। ਕੀ ਤੁਸੀਂ ਦੁਬਾਰਾ ਬੋਲ ਸਕਦੇ ਹੋ?"
    if lang_lower in ("ur", "urdu"):
        return "معاف کیجیے گا، مجھے صاف سنائی نہیں دیا۔ کیا آپ دوبارہ کہہ سکتے ہیں؟"
    if lang_lower in ("or", "odia"):
        return "କ୍ଷମା କରିବେ, ମୋତେ ସ୍ପଷ୍ଟ ଶୁଣାଗଲା ନାହିଁ। ଦୟାକରି ଆଉ ଥରେ କହିବେ କି?"
    if lang_lower in ("as", "assamese"):
        return "ক্ষমা কৰিব, মই স্পষ্টকৈ শুনা নাপালোঁ। অনুগ্ৰহ কৰি পুনৰ ক'ব নেকি?"
    if lang_lower in ("hi", "hindi"):
        return "माफ़ कीजिए, मुझे आपकी आवाज़ साफ़ सुनाई नहीं दी। क्या आप दोबारा बोलेंगे?"
    if lang_lower in ("hinglish",):
        return "Sorry, mujhe theek se sunayi nahi diya. Kya aap dobara bol sakte hain?"
    if lang_lower in ("es", "spanish"):
        return "Disculpe, no le escuché con claridad. ¿Podría repetirlo, por favor?"
    if lang_lower in ("fr", "french"):
        return "Pardon, je n'ai pas bien entendu. Pourriez-vous répéter, s'il vous plaît ?"
    if lang_lower in ("de", "german"):
        return "Entschuldigung, ich habe Sie nicht genau verstanden. Könnten Sie das bitte wiederholen?"
    if lang_lower in ("it", "italian"):
        return "Mi scusi, non ho sentito chiaramente. Potrebbe重复, per favore?"
    if lang_lower in ("pt", "portuguese"):
        return "Desculpe, não ouvi com clareza. Poderia repetir, por favor?"
    if lang_lower in ("ru", "russian"):
        return "Извините, я не расслышал. Не могли бы вы повторить?"
    if lang_lower in ("zh", "chinese"):
        return "抱歉，我没有听清。能请您再重复一遍吗？"
    if lang_lower in ("ja", "japanese"):
        return "申し訳ありません、よく聞き取れませんでした。もう一度お願いできますか？"
    if lang_lower in ("ko", "korean"):
        return "죄송합니다, 잘 듣지 못했습니다. 다시 말씀해 주시겠습니까?"
    if lang_lower in ("ar", "arabic"):
        return "عذراً، لم أسمعك بوضوح. هل يمكنك الإعادة من فضلك؟"

    return "I didn't catch that clearly. Could you please repeat?"


# ── Session Language Manager ─────────────────────────────────────────────────

class SessionLanguageManager:
    """
    Tracks and updates the active language throughout the live conversation session.
    """
    def __init__(self, user_id: str = "default_user"):
        self.user_id = user_id
        saved = _lang_pref.get(user_id)
        self._lang = saved or "auto"
        self._switched_once = False

    @property
    def lang(self) -> Optional[str]:
        return self._lang

    def is_set(self) -> bool:
        return bool(self._lang and self._lang != "auto")

    def set_from_user_response(self, text: str) -> Optional[str]:
        """User answered a language question."""
        detected = detect_lang_from_response(text)
        if detected:
            self._lang = detected
            _lang_pref.set(self.user_id, detected)
            return detected
        return None

    def check_switch(self, text: str) -> Optional[str]:
        """Checks if ongoing speech triggers a language change."""
        current = self._lang or "auto"
        new_lang = detect_lang_switch(text, current)
        if new_lang is None or new_lang == current:
            return None
        self._lang = new_lang
        _lang_pref.set(self.user_id, new_lang)
        return new_lang

    def get_unclear_message(self) -> str:
        return build_unclear_audio_message(self._lang or "en")


def build_session_greeting(
    user_name: str,
    user_id: str = "default_user",
    assistant_name: str = "Charlie",
    last_topic: str = "",
) -> tuple[str, SessionLanguageManager]:
    """
    Instantiates SessionLanguageManager and builds greeting string for session.
    """
    mgr = SessionLanguageManager(user_id=user_id)
    is_returning = bool(last_topic)
    greeting = build_greeting(
        user_name=user_name,
        assistant_name=assistant_name,
        is_returning=is_returning,
        last_topic=last_topic,
    )
    return greeting, mgr
