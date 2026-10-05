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
  UNKNOWN  → asks preference on login
  SET      → Charlie speaks in preferred language; detects switches
  SWITCHED → confirms the switch once, then silent
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional


# ── Storage path ──────────────────────────────────────────────────────────────
def _cfg_dir() -> Path:
    """Mirror config_manager's BASE_DIR logic without importing it."""
    import sys
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "config"
    return Path(__file__).resolve().parent.parent.parent / "config"


def _lang_pref_file() -> Path:
    return _cfg_dir() / "lang_pref.json"


# ── Greeting helpers ──────────────────────────────────────────────────────────

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


# ── Language preference store ─────────────────────────────────────────────────

class LangPreference:
    """
    Persists language preference per user so Charlie never asks again.
    Stored in config/lang_pref.json  →  { "<user_id>": "auto" | "en" | "hi" | "mr" | ... }
    """
    _lock = threading.Lock()

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
        lang = lang.lower().strip()
        # Do not force unlisted languages to 'en'; keep whatever user requested or auto
        with self._lock:
            data = self._load()
            data[user_id] = lang
            self._save(data)

    def clear(self, user_id: str) -> None:
        with self._lock:
            data = self._load()
            data.pop(user_id, None)
            self._save(data)


# Global singleton
_lang_pref = LangPreference()


# ── Language detector from text ───────────────────────────────────────────────

_AUTO_WORDS = {
    "auto", "any", "all", "mixed", "mix", "dono", "sab", "har bhasha",
    "kisi bhi", "koi bhi", "any language", "auto language", "auto detect",
}

_MARATHI_WORDS = {
    "marathi", "marathit", "मराठी", "marathi mein", "marathi me",
    "marathi madhe", "marathit bola", "marathi bolo", "mala marathi",
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
    "hindi", "hindi mein", "hindi me", "hindhi",
    "हिंदी", "हिन्दी",
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

    # Native scripts
    for pattern, code in _REGIONAL_SCRIPTS:
        if pattern.search(text):
            if code == "bn" and (any(ch in text for ch in ("\u09F0", "\u09F1")) or any(w in t for w in ("অসমীয়া", "আছোঁ", "কৰক", "নহয়", "ধন্যবাদ", "মই", "আপুনি"))):
                return "as"
            return code
    if re.search(r"[\u0900-\u097F]", text):
        # Check if Marathi markers present in Devanagari
        if any(w in t for w in ("आहे", "नाही", "करा", "सांगा", "नमस्कार", "कसे", "माझे", "नाव", "काय", "झाले", "मराठी")):
            return "mr"
        return "hi"

    # Keywords
    for kw in _AUTO_WORDS:
        if kw in t:
            return "auto"
    for kw in _MARATHI_WORDS:
        if kw in t:
            return "mr"
    for kw in _BENGALI_WORDS:
        if kw in t:
            return "bn"
    for kw in _TAMIL_WORDS:
        if kw in t:
            return "ta"
    for kw in _TELUGU_WORDS:
        if kw in t:
            return "te"
    for kw in _GUJARATI_WORDS:
        if kw in t:
            return "gu"
    for kw in _KANNADA_WORDS:
        if kw in t:
            return "kn"
    for kw in _MALAYALAM_WORDS:
        if kw in t:
            return "ml"
    for kw in _PUNJABI_WORDS:
        if kw in t:
            return "pa"
    for kw in _URDU_WORDS:
        if kw in t:
            return "ur"
    for kw in _ODIA_WORDS:
        if kw in t:
            return "or"
    for kw in _ASSAMESE_WORDS:
        if kw in t:
            return "as"
    for kw in _HINDI_WORDS:
        if kw in t:
            return "hi"
    for kw in _HINGLISH_WORDS:
        if kw in t:
            return "hinglish"

    # European & International
    if any(w in t for w in ("hola", "gracias", "por favor", "cómo estás", "buenos días", "español", "amigo")):
        return "es"
    if any(w in t for w in ("bonjour", "merci", "s'il vous plaît", "français", "au revoir", "comment allez-vous")):
        return "fr"
    if any(w in t for w in ("guten tag", "danke", "bitte", "deutsch", "wie geht", "auf wiedersehen")):
        return "de"
    if any(w in t for w in ("ciao", "grazie", "per favore", "italiano", "buongiorno", "come stai")):
        return "it"
    if any(w in t for w in ("olá", "obrigado", "português", "bom dia", "como vai")):
        return "pt"
    if any(w in t for w in ("привет", "спасибо", "пожалуйста", "здравствуйте", "русский")):
        return "ru"
    if any(w in t for w in ("こんにちは", "ありがとう", "日本語", "はじめまして")):
        return "ja"
    if any(w in t for w in ("你好", "谢谢", "中文", "普通话")):
        return "zh"
    if any(w in t for w in ("안녕하세요", "감사합니다", "한국어")):
        return "ko"
    if any(w in t for w in ("marhaban", "shukran", "ahlan", "arabi")):
        return "ar"

    for kw in _ENGLISH_WORDS:
        if kw in t:
            return "en"
    return None


def detect_lang_switch(text: str, current_lang: str) -> Optional[str]:
    """
    Detects if the user is switching language mid-session.
    Returns the new language code when requested by user, else None.
    """
    if not text:
        return None
    t = text.lower().strip()

    # Explicit "switch to X" or "speak in X"
    m_switch = re.search(
        r"\b(?:switch\s+(?:language\s+)?to|speak\s+in|talk\s+in|start\s+speaking\s+in)\s+(auto|english|hindi|hinglish|marathi|bengali|bangla|tamil|telugu|gujarati|kannada|malayalam|punjabi|urdu|odia|assamese|spanish|french|german|italian|portuguese|russian|chinese|mandarin|japanese|korean|arabic)\b",
        t,
    )
    if m_switch:
        target = m_switch.group(1)
        mapping = {
            "auto": "auto", "english": "en", "hindi": "hi", "hinglish": "hinglish",
            "marathi": "mr", "bengali": "bn", "bangla": "bn", "tamil": "ta",
            "telugu": "te", "gujarati": "gu", "kannada": "kn", "malayalam": "ml",
            "punjabi": "pa", "urdu": "ur", "odia": "or", "assamese": "as",
            "spanish": "es", "french": "fr", "german": "de", "italian": "it",
            "portuguese": "pt", "russian": "ru",
            "chinese": "zh", "mandarin": "zh", "japanese": "ja", "korean": "ko",
            "arabic": "ar",
        }
        return mapping.get(target, "auto")

    # Explicit regional command: "X mein baat karo / X madhe bola / Xil pesu..."
    if re.search(r"\b(marathi|मराठी)\s*(mein|madhe|t)?\s*(baat|bolo|bola)\s*(karo|kara)?\b", t):
        return "mr"
    if re.search(r"\b(bengali|bangla|বাংলা)\s*(mein|te|y)?\s*(baat|bolo|kotha)\s*(karo|bolun)?\b", t):
        return "bn"
    if re.search(r"\b(gujarati|ગુજરાતી)\s*(mein|ma)?\s*(baat|bolo)\s*(karo)?\b", t):
        return "gu"
    if re.search(r"\b(tamil|தமிழ்)\s*(mein|il)?\s*(baat|bolo|pesu)\s*(karo|unga)?\b", t):
        return "ta"
    if re.search(r"\b(telugu|తెలుగు)\s*(mein|lo)?\s*(baat|bolo|matladu)\s*(karo)?\b", t):
        return "te"
    if re.search(r"\b(kannada|ಕನ್ನಡ)\s*(mein|dalli)?\s*(baat|bolo|matadi)\s*(karo)?\b", t):
        return "kn"
    if re.search(r"\b(punjabi|ਪੰਜਾਬੀ)\s*(mein|vich|ch)?\s*(baat|bolo)\s*(karo)?\b", t):
        return "pa"
    if re.search(r"\b(urdu|اردو)\s*(mein)?\s*(baat|bolo)\s*(karo)?\b", t):
        return "ur"
    if re.search(r"\b(odia|oriya|ଓଡ଼ିଆ)\s*(mein|re)?\s*(baat|bolo|katha)\s*(karo)?\b", t):
        return "or"
    if re.search(r"\b(assamese|অসমীয়া)\s*(mein)?\s*(baat|bolo|katha)\s*(karo)?\b", t):
        return "as"
    if re.search(r"\b(hindi|हिंदी)\s+mein\s+(baat|bolo|bolein)\s*(karo)?\b", t):
        return "hi"
    if re.search(r"\b(spanish|español)\s*(mein)?\s*(baat|bolo|speak)?\b", t):
        return "es"
    if re.search(r"\b(french|français)\s*(mein)?\s*(baat|bolo|speak)?\b", t):
        return "fr"
    if re.search(r"\b(german|deutsch)\s*(mein)?\s*(baat|bolo|speak)?\b", t):
        return "de"
    if re.search(r"\b(italian|italiano)\s*(mein)?\s*(baat|bolo|speak)?\b", t):
        return "it"
    if re.search(r"\b(portuguese|português)\s*(mein)?\s*(baat|bolo|speak)?\b", t):
        return "pt"
    if re.search(r"\b(russian|русский)\s*(mein)?\s*(baat|bolo|speak)?\b", t):
        return "ru"
    if re.search(r"\b(arabic|عربي)\s*(mein)?\s*(baat|bolo|speak)?\b", t):
        return "ar"
    if re.search(r"\benglish\s+(mein|me)?\s*(baat|bolo|bolein|please)?\s*(karo)?\b", t) and any(w in t for w in ("switch", "speak", "talk", "please", "karo")):
        return "en"
    if re.search(r"\b(chinese|mandarin|चीनी)\s*(mein)?\s*(baat|bolo|bolein)\s*(karo)?\b", t):
        return "zh"
    if re.search(r"\b(japanese|जापानी|nihongo)\s*(mein)?\s*(baat|bolo|bolein)\s*(karo)?\b", t):
        return "ja"
    if re.search(r"\b(korean|कोरियाई)\s*(mein)?\s*(baat|bolo|bolein)\s*(karo)?\b", t):
        return "ko"

    return None


# ── Greeting builder ───�def build_greeting(
    user_name: str,
    lang: Optional[str] = "auto",
    assistant_name: str = "Charlie",
    is_returning: bool = False,
    last_topic: str = "",
) -> str:
    """
    Builds the spoken startup greeting.
    Announces multilingual readiness across English, Hindi, Marathi, and all regional and world languages.
    """
    name = user_name.strip() if user_name.strip() and user_name.lower() not in ("", "primary user") else ""
    sal = _time_salutation()
    address = f", {name}!" if name else "!"

    if is_returning and last_topic:
        return (
            f"Welcome back{address} I am {assistant_name}, all systems ready. "
            f"I can speak in English, Hindi, Marathi, and all regional and global languages. "
            f"Ready to continue with {last_topic}, or start something new?"
        )
    return (
        f"{sal}{address} I am {assistant_name}, all systems ready. "
        f"I can speak in English, Hindi, Marathi, and all regional and global languages. "
        f"How may I assist you today?"
    )


def build_language_confirm(new_lang: str, assistant_name: str = "Charlie") -> str:
    """
    One-time confirmation message when user switches language.
    """
    lang_lower = str(new_lang).lower()
    if lang_lower in ("mr", "marathi"):
        return "नक्कीच! आता मी मराठीत बोलेन. तुम्ही कधीही भाषा बदलू शकता."
    if lang_lower in ("bn", "bengali"):
        return "নিশ্চয়ই! এখন থেকে আমি বাংলায় কথা বলব। আপনি যেকোনো সময় ভাষা পরিবর্তন করতে পারেন।"
    if lang_lower in ("gu", "gujarati"):
        return "ચોક્કસ! હવે હું ગુજરાતીમાં વાત કરીશ. તમે ગમે ત્યારે ભાષા બદલી શકો છો."
    if lang_lower in ("ta", "tamil"):
        return "நிச்சயமாக! இனி நான் தமிழில் பேசுகிறேன். நீங்கள் எப்போது வேண்டுமானாலும் மொழியை மாற்றலாம்."
    if lang_lower in ("te", "telugu"):
        return "తప్పకుండా! ఇకపై నేను తెలుగులో మాట్లాడుతాను. మీరు ఎప్పుడైనా భాషను మార్చవచ్చు."
    if lang_lower in ("kn", "kannada"):
        return "ಖಂಡಿತ! ಇನ್ನು ಮುಂದೆ ನಾನು ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡುತ್ತೇನೆ."
    if lang_lower in ("ml", "malayalam"):
        return "തീർച്ചയായും! ഇനി ഞാൻ മലയാളത്തിൽ സംസാരിക്കാം."
    if lang_lower in ("pa", "punjabi"):
        return "ਜ਼ਰੂਰ! ਹੁਣ ਮੈਂ ਪੰਜਾਬੀ ਵਿੱਚ ਗੱਲ ਕਰਾਂਗਾ।"
    if lang_lower in ("ur", "urdu"):
        return "بالکل! اب میں آپ سے اردو میں بات کروں گا۔"
    if lang_lower in ("or", "odia"):
        return "ନିଶ୍ଚୟ! ଏବେ ମୁଁ ଓଡ଼ିଆରେ କଥା ହେବି।"
    if lang_lower in ("as", "assamese"):
        return "নিশ্চয়! এতিয়াৰ পৰা মই অসমীয়াত কথা পাতিম।"
    if lang_lower in ("hi", "hindi"):
        return "Bilkul! Ab main Hindi mein baat karunga. Aap kabhi bhi bhasha badal sakte hain."
    if lang_lower in ("hinglish",):
        return "Sure! I'll speak in natural Hinglish for you. You can switch anytime."
    if lang_lower in ("es", "spanish"):
        return "¡Por supuesto! A partir de ahora hablaré en español. Puedes cambiar de idioma cuando quieras."
    if lang_lower in ("fr", "french"):
        return "Bien sûr ! Je parlerai désormais en français. Vous pouvez changer de langue à tout moment."
    if lang_lower in ("de", "german"):
        return "Natürlich! Ich spreche ab jetzt auf Deutsch. Sie können die Sprache jederzeit ändern."
    if lang_lower in ("it", "italian"):
        return "Certamente! D'ora in poi parlerò in italiano. Puoi cambiare lingua in qualsiasi momento."
    if lang_lower in ("pt", "portuguese"):
        return "Com certeza! A partir de agora falarei em português. Você pode mudar de idioma a qualquer momento."
    if lang_lower in ("ru", "russian"):
        return "Конечно! Теперь я буду говорить по-русски. Вы можете переключить язык в любое время."
    if lang_lower in ("zh", "chinese"):
        return "好的，我现在说中文。你可以随时切换回其他语言。"
    if lang_lower in ("ja", "japanese"):
        return "かしこまりました。これからは日本語でお話しします。いつでも言語を変更できます。"
    if lang_lower in ("ko", "korean"):
        return "알겠습니다. 이제부터 한국어로 말씀드리겠습니다. 언제든지 언어를 변경하실 수 있습니다."
    if lang_lower in ("ar", "arabic"):
        return "بالتأكيد! سأتحدث الآن باللغة العربية. يمكنك تغيير اللغة في أي وقت."
    if lang_lower in ("auto",):
        return "Sure! I will naturally speak in whichever regional or global language you use."
    return "Switching to English. You can speak to me in Hindi, Marathi, or any regional and global language anytime."


def build_unclear_audio_message(lang: str = "en") -> str:
    """Professional 'I didn't hear you' message for all supported languages."""
    lang_lower = str(lang).lower()
    if lang_lower in ("mr", "marathi"):
        return "मला तुमचा आवाज स्पष्ट ऐकू आला नाही. कृपया पुन्हा सांगू शकाल का?"
    if lang_lower in ("bn", "bengali"):
        return "আমি আপনার কথা পরিষ্কার শুনতে পাইনি। দয়া করে আবার বলবেন কি?"
    if lang_lower in ("gu", "gujarati"):
        return "મને તમારો અવાજ સ્પષ્ટ સંભળાયો નથી. શું તમે ફરીથી બોલી શકશો?"
    if lang_lower in ("ta", "tamil"):
        return "உங்கள் குரல் தெளிவாக கேட்கவில்லை. தயவுசெய்து மீண்டும் சொல்ல முடியுமா?"
    if lang_lower in ("te", "telugu"):
        return "మీ మాటలు స్పష్టంగా వినపడలేదు. దయచేసి మళ్ళీ చెప్పగలరా?"
    if lang_lower in ("kn", "kannada"):
        return "ನಿಮ್ಮ ಧ್ವನಿ ಸ್ಪಷ್ಟವಾಗಿ ಕೇಳಿಸಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಇನ್ನೊಮ್ಮೆ ಹೇಳುತ್ತೀರಾ?"
    if lang_lower in ("ml", "malayalam"):
        return "നിങ്ങളുടെ ശബ്ദം വ്യക്തമായി കേട്ടില്ല. ദയവായി വീണ്ടും പറയാമോ?"
    if lang_lower in ("pa", "punjabi"):
        return "ਮੈਨੂੰ ਤੁਹਾਡੀ ਆਵਾਜ਼ ਸਾਫ਼ ਨਹੀਂ ਸੁਣਾਈ ਦਿੱਤੀ। ਕਿਰਪਾ ਕਰਕੇ ਦੁਬਾਰਾ ਬੋਲੋਗੇ?"
    if lang_lower in ("ur", "urdu"):
        return "مجھے آپ کی آواز واضح نہیں آئی۔ کیا آپ دوبارہ کہہ سکتے ہیں؟"
    if lang_lower in ("or", "odia"):
        return "ମୁଁ ଆପଣଙ୍କ ସ୍ୱର ସ୍ପଷ୍ଟ ଭାବରେ ଶୁଣିପାରିଲି ନାହିଁ। ଦୟାକରି ପୁଣି କହିବେ କି?"
    if lang_lower in ("as", "assamese"):
        return "মই আপোনাৰ মাতটো স্পষ্টকৈ শুনা নাপালোঁ। অনুগ্ৰহ কৰি আকৌ এবাৰ ক'ব নেকি?"
    if lang_lower in ("es", "spanish"):
        return "No pude escucharte con claridad. ¿Podrías repetirlo, por favor?"
    if lang_lower in ("fr", "french"):
        return "Je n'ai pas bien entendu. Pourriez-vous répéter, s'il vous plaît ?"
    if lang_lower in ("de", "german"):
        return "Ich habe Sie leider nicht klar verstanden. Könnten Sie das bitte wiederholen?"
    if lang_lower in ("it", "italian"):
        return "Non ho sentito chiaramente. Potresti ripetere, per favore?"
    if lang_lower in ("pt", "portuguese"):
        return "Não consegui ouvir claramente. Você poderia repetir, por favor?"
    if lang_lower in ("ru", "russian"):
        return "Я не расслышал вас четко. Не могли бы вы повторить, пожалуйста?"
    if lang_lower in ("ja", "japanese"):
        return "声がはっきりと聞き取れませんでした。もう一度言っていただけますか？"
    if lang_lower in ("zh", "chinese"):
        return "我没有听清，请您再说一遍好吗？"
    if lang_lower in ("ko", "korean"):
        return "목소리를 명확하게 듣지 못했습니다. 다시 말씀해 주시겠어요?"
    if lang_lower in ("ar", "arabic"):
        return "لم أسمعك بوضوح. هل يمكنك الإعادة من فضلك؟"
    if lang_lower in ("hi", "hindi", "hinglish"):
        return "Mujhe aapki baat samajh nahi aayi barabar, aap phir se bol sakte ho taki mai apki madad kar saku?"
    return "I'm sorry, I didn't catch that clearly. Could you please repeat?"িম।"
    if lang_lower in ("hi", "hindi"):
        return "Bilkul! Ab main Hindi mein baat karunga. Aap kabhi bhi bhasha badal sakte hain."
    if lang_lower in ("hinglish",):
        return "Sure! I'll speak in natural Hinglish for you. You can switch anytime."
    if lang_lower in ("zh", "chinese"):
        return "好的，我现在说中文。你可以随时切换回其他语言。"
    if lang_lower in ("ja", "japanese"):
        return "かしこまりました。これからは日本語でお話しします。いつでも言語を変更できます。"
    if lang_lower in ("auto",):
        return "Sure! I will naturally speak in whichever regional or global language you use."
    return "Switching to English. You can speak to me in Hindi or any regional language anytime."


def build_unclear_audio_message(lang: str = "en") -> str:
    """Professional 'I didn't hear you' message for all supported languages."""
    lang_lower = str(lang).lower()
    if lang_lower in ("mr", "marathi"):
        return "मला तुमचा आवाज स्पष्ट ऐकू आला नाही. कृपया पुन्हा सांगू शकाल का?"
    if lang_lower in ("bn", "bengali"):
        return "আমি আপনার কথা পরিষ্কার শুনতে পাইনি। দয়া করে আবার বলবেন কি?"
    if lang_lower in ("gu", "gujarati"):
        return "મને તમારો અવાજ સ્પષ્ટ સંભળાયો નથી. શું તમે ફરીથી બોલી શકશો?"
    if lang_lower in ("ta", "tamil"):
        return "உங்கள் குரல் தெளிவாக கேட்கவில்லை. தயவுசெய்து மீண்டும் சொல்ல முடியுமா?"
    if lang_lower in ("te", "telugu"):
        return "మీ మాటలు స్పష్టంగా వినపడలేదు. దయచేసి మళ్ళీ చెప్పగలరా?"
    if lang_lower in ("kn", "kannada"):
        return "ನಿಮ್ಮ ಧ್ವನಿ ಸ್ಪಷ್ಟವಾಗಿ ಕೇಳಿಸಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಇನ್ನೊಮ್ಮೆ ಹೇಳುತ್ತೀರಾ?"
    if lang_lower in ("ml", "malayalam"):
        return "നിങ്ങളുടെ ശബ്ദം വ്യക്തമായി കേട്ടില്ല. ദയവായി വീണ്ടും പറയാമോ?"
    if lang_lower in ("pa", "punjabi"):
        return "ਮੈਨੂੰ ਤੁਹਾਡੀ ਆਵਾਜ਼ ਸਾਫ਼ ਨਹੀਂ ਸੁਣਾਈ ਦਿੱਤੀ। ਕਿਰਪਾ ਕਰਕੇ ਦੁਬਾਰਾ ਬੋਲੋਗੇ?"
    if lang_lower in ("ur", "urdu"):
        return "مجھے آپ کی آواز واضح نہیں آئی۔ کیا آپ دوبارہ کہہ سکتے ہیں؟"
    if lang_lower in ("hi", "hindi", "hinglish"):
        return "Mujhe aapki baat samajh nahi aayi barabar, aap phir se bol sakte ho taki mai apki madad kar saku?"
    return "I'm sorry, I didn't catch that clearly. Could you please repeat?"


# ── Session Language Manager (per-session state) ──────────────────────────────

class SessionLanguageManager:
    """
    Tracks per-session language state.
    - Loads saved preference on init
    - Tracks whether confirmation was given this session
    - Thread-safe
    """

    def __init__(self, user_id: str = "default_user"):
        self.user_id  = user_id
        self._lock    = threading.Lock()
        saved         = _lang_pref.get(user_id)
        self._lang    = saved           # None = not set yet
        self._confirmed_switch = False  # did we confirm the language already?

    @property
    def lang(self) -> Optional[str]:
        with self._lock:
            return self._lang

    def is_set(self) -> bool:
        with self._lock:
            return self._lang is not None

    def set_from_user_response(self, text: str) -> Optional[str]:
        """
        Call this with the user's reply to the language question.
        Returns the lang code if preference was detected and saved, else None.
        """
        detected = detect_lang_from_response(text)
        if detected:
            with self._lock:
                self._lang = detected
                self._confirmed_switch = True
            _lang_pref.set(self.user_id, detected)
        return detected

    def check_switch(self, text: str) -> Optional[str]:
        """
        Call on every user utterance.
        Returns (new_lang, needs_confirmation) tuple if a switch was detected.
        - If it's the FIRST switch this session → needs_confirmation = True
        - Subsequent switches → needs_confirmation = False (user can freely switch)
        """
        with self._lock:
            current = self._lang or "en"
            new_lang = detect_lang_switch(text, current)
            if new_lang is None:
                return None
            # Same language → no switch
            if new_lang == current:
                return None
            # New language detected
            needs_confirm = not self._confirmed_switch
            self._lang = new_lang
            self._confirmed_switch = True
            _lang_pref.set(self.user_id, new_lang)
            return new_lang

    def get_unclear_message(self) -> str:
        return build_unclear_audio_message(self.lang or "en")


# ── Convenience function for main.py ─────────────────────────────────────────

def build_session_greeting(
    user_name: str,
    user_id: str = "default_user",
    assistant_name: str = "Charlie",
    last_topic: str = "",
) -> tuple[str, SessionLanguageManager]:
    """
    Returns (greeting_text, lang_manager) for use at session start.
    The caller should speak greeting_text.
    The lang_manager should be stored on the app and used to:
      - call lang_manager.set_from_user_response(text) when user replies to language prompt
      - call lang_manager.check_switch(text) on every subsequent utterance
    """
    mgr = SessionLanguageManager(user_id=user_id)
    saved_lang = mgr.lang
    is_returning = bool(last_topic)

    greeting = build_greeting(
        user_name     = user_name,
        lang          = saved_lang,
        assistant_name= assistant_name,
        is_returning  = is_returning,
        last_topic    = last_topic,
    )
    return greeting, mgr
