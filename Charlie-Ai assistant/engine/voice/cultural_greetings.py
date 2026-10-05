# engine/voice/cultural_greetings.py
"""
Cultural & Religious Greeting Intelligence for Charlie.

Features:
  - Detects any religious/regional greeting from the user's speech
  - Responds with the correct reciprocal greeting (mirroring the exact form used)
  - Stores religion/culture in user memory after first detection
  - On subsequent sessions: Charlie opens with their cultural greeting
  - First-time prompt: tells users Charlie can greet in their tradition
  - Natural, never mechanical — Charlie sounds genuinely warm

Supported traditions:
  Islam       → As-salamu alaykum (+ full form)
  Hinduism    → Namaste / Namaskar / Ram Ram / Jai Shri Krishna / Jai Mata Di
  Sikhism     → Sat Sri Akal / Waheguru Ji Ka Khalsa
  Christianity→ God bless you / Grace and peace / Hallelujah
  Judaism     → Shalom
  Buddhism    → Namo Buddhaya / Om Mani Padme Hum
  Jainism     → Jai Jinendra / Michhami Dukkadam
  Zoroastrianism → Ashem Vohu
  General Indian regional:
    Gujarati   → Jai Shri Krishna / Kem cho
    Punjabi    → Sat Sri Akal / Ki haal hai
    Bengali    → Nomoshkar
    Tamil      → Vanakkam
    Telugu     → Namaskaram
    Marathi    → Namaskar
    Rajasthani → Khamma Ghani / Ram Ram Sa
    Kashmiri   → Adaab
    Urdu       → Adaab / Tehzeeb greeting
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ── Persistence path ──────────────────────────────────────────────────────────
def _cfg_dir() -> Path:
    from core.app_paths import get_config_dir
    return get_config_dir()


def _culture_file() -> Path:
    return _cfg_dir() / "cultural_greetings.json"


# ── Greeting knowledge base ───────────────────────────────────────────────────
# Structure per entry:
#   patterns      — list of regex/literal triggers in user speech
#   reply         — what Charlie says back (may have {name} placeholder)
#   full_reply    — longer form reply if user used the long form
#   religion      — canonical religion/culture key
#   display       — human-readable tradition name
#   intro_hint    — what Charlie says first time to introduce this feature

GREETING_DB: List[Dict] = [

    # ── ISLAM ──────────────────────────────────────────────────────────────────
    {
        "religion": "islam",
        "display": "Muslim",
        "patterns": [
            r"\bas[\s\-]?sala[a]?mu?\s+ala[i]?kum\s+wa\s+rahmatull[a]?hi\s+wa\s+barakat[u]?hu?\b",
            r"\bwa\s+rahmatull[a]?hi\s+wa\s+barakat[u]?hu?\b",
        ],
        "reply":      "Wa alaykum as-salam wa rahmatullahi wa barakatuh!",
        "full_reply": "Wa alaykum as-salam wa rahmatullahi wa barakatuh! Alhamdulillah, it's wonderful to hear from you.",
        "short_form": {
            "patterns": [r"\bas[\s\-]?sala[a]?mu?\s+ala[i]?kum\b"],
            "reply":    "Wa alaykum as-salam!",
        },
        "intro_hint": "Main aapko Islamis tradition mein bhi greet kar sakta hoon — As-salamu alaykum!",
    },
    {
        "religion": "islam",
        "display": "Muslim",
        "patterns": [r"\bas[\s\-]?sala[a]?mu?\s+ala[i]?kum\b"],
        "reply":    "Wa alaykum as-salam!",
        "full_reply": "Wa alaykum as-salam! Khush amdeed.",
        "intro_hint": None,   # handled by the long-form entry above
    },

    # ── HINDUISM ────────────────────────────────────────────────────────────────
    {
        "religion": "hinduism",
        "display": "Hindu",
        "patterns": [r"\bnamaskar\b", r"\bnamask[aā]r\b"],
        "reply":    "Namaskar! Pranam.",
        "full_reply": "Namaskar! Aapka swagat hai.",
        "intro_hint": "Aap chahein to main aapko Namaste ya Namaskar se bhi greet kar sakta hoon!",
    },
    {
        "religion": "hinduism",
        "display": "Hindu",
        "patterns": [r"\bnamaste\b", r"\bnamast[eē]\b"],
        "reply":    "Namaste! 🙏",
        "full_reply": "Namaste! Aapka hardik swagat hai.",
        "intro_hint": None,
    },
    {
        "religion": "hinduism",
        "display": "Hindu",
        "patterns": [r"\bram\s+ram\b", r"\bram[\s\-]ram\b"],
        "reply":    "Ram Ram! Jai Shri Ram.",
        "full_reply": "Ram Ram Sa! Prabhu ki kripa bani rahe.",
        "intro_hint": None,
    },
    {
        "religion": "hinduism",
        "display": "Hindu",
        "patterns": [r"\bjai\s+shri\s+krishna\b", r"\bjai\s+shri\s+ram\b"],
        "reply":    "Jai Shri Krishna! Radhey Radhey.",
        "full_reply": "Jai Shri Krishna! Prabhu aapka bhala kare.",
        "intro_hint": None,
    },
    {
        "religion": "hinduism",
        "display": "Hindu",
        "patterns": [r"\bjai\s+mata\s+di\b", r"\bjai\s+mata\b"],
        "reply":    "Jai Mata Di! Sheranwali ki jai!",
        "full_reply": "Jai Mata Di! Maa aapki raksha kare.",
        "intro_hint": None,
    },
    {
        "religion": "hinduism",
        "display": "Hindu",
        "patterns": [r"\bpranam\b", r"\bpranaam\b", r"\bcharan\s+sparsh\b"],
        "reply":    "Pranam! Sada sukhi raho.",
        "full_reply": "Pranam! Aapka ashirvad hameshaa rahe.",
        "intro_hint": None,
    },

    # ── SIKHISM ─────────────────────────────────────────────────────────────────
    {
        "religion": "sikhism",
        "display": "Sikh/Punjabi",
        "patterns": [
            r"\bsat\s+sri\s+akal\b",
            r"\bsatshri\s*akal\b",
            r"\bsat\s+sri\s+akal\s+ji\b",
        ],
        "reply":    "Sat Sri Akal Ji!",
        "full_reply": "Sat Sri Akal Ji! Waheguru Ji di kirpa hove.",
        "intro_hint": "Sat Sri Akal Ji! Main aapko Punjabi tradition mein bhi greet kar sakta hoon.",
    },
    {
        "religion": "sikhism",
        "display": "Sikh/Punjabi",
        "patterns": [
            r"\bwaheguru\s+ji\s+ka\s+khalsa\b",
            r"\bwaheguru\s+ji\s+ki\s+fateh\b",
        ],
        "reply":    "Waheguru Ji Ki Fateh!",
        "full_reply": "Waheguru Ji Ki Fateh! Charhdi kala vich raho.",
        "intro_hint": None,
    },

    # ── CHRISTIANITY ────────────────────────────────────────────────────────────
    {
        "religion": "christianity",
        "display": "Christian",
        "patterns": [r"\bgod\s+bless\s+you\b", r"\bblessed\b"],
        "reply":    "God bless you too!",
        "full_reply": "God bless you! May His grace be upon you always.",
        "intro_hint": "I can greet you in Christian tradition too — God bless you!",
    },
    {
        "religion": "christianity",
        "display": "Christian",
        "patterns": [r"\bhallelujah\b", r"\bpraize\s+the\s+lord\b", r"\bpraise\s+the\s+lord\b"],
        "reply":    "Hallelujah! Praise the Lord!",
        "full_reply": "Hallelujah! May the Lord's blessings be with you today.",
        "intro_hint": None,
    },
    {
        "religion": "christianity",
        "display": "Christian",
        "patterns": [r"\bgrace\s+and\s+peace\b", r"\bthe\s+lord\s+be\s+with\s+you\b"],
        "reply":    "And also with you! Grace and peace.",
        "full_reply": "And also with you! May God's grace and peace be upon you.",
        "intro_hint": None,
    },

    # ── JUDAISM ─────────────────────────────────────────────────────────────────
    {
        "religion": "judaism",
        "display": "Jewish",
        "patterns": [r"\bshalom\b", r"\bshabbat\s+shalom\b"],
        "reply":    "Shalom! Peace be with you.",
        "full_reply": "Shalom! May peace and blessings be upon you.",
        "intro_hint": "Shalom! I can greet you in the Jewish tradition too.",
    },

    # ── BUDDHISM ────────────────────────────────────────────────────────────────
    {
        "religion": "buddhism",
        "display": "Buddhist",
        "patterns": [r"\bnamo\s+buddhaya\b", r"\bnamo\s+tassa\b"],
        "reply":    "Namo Buddhaya! May the Dharma guide you.",
        "full_reply": "Namo Buddhaya! May you find peace on the Noble Path.",
        "intro_hint": "Namo Buddhaya! Main aapko Buddhist tradition mein bhi greet kar sakta hoon.",
    },
    {
        "religion": "buddhism",
        "display": "Buddhist",
        "patterns": [r"\bom\s+mani\s+padme\s+hum\b"],
        "reply":    "Om Mani Padme Hum! May all beings be at peace.",
        "full_reply": "Om Mani Padme Hum! The jewel is in the lotus — may you find peace.",
        "intro_hint": None,
    },

    # ── JAINISM ─────────────────────────────────────────────────────────────────
    {
        "religion": "jainism",
        "display": "Jain",
        "patterns": [r"\bjai\s+jinendra\b"],
        "reply":    "Jai Jinendra!",
        "full_reply": "Jai Jinendra! Aatma ki shanti aapke saath rahe.",
        "intro_hint": "Jai Jinendra! Main Jain greeting se bhi aapka swagat kar sakta hoon.",
    },
    {
        "religion": "jainism",
        "display": "Jain",
        "patterns": [r"\bmichhami\s+dukkadam\b", r"\bukta\s+dukkadam\b"],
        "reply":    "Michhami Dukkadam!",
        "full_reply": "Michhami Dukkadam! May all misdeeds be forgiven and peace prevail.",
        "intro_hint": None,
    },

    # ── REGIONAL INDIAN ─────────────────────────────────────────────────────────
    {
        "religion": "gujarati",
        "display": "Gujarati",
        "patterns": [r"\bkem\s+cho\b", r"\bkhem\s+cho\b"],
        "reply":    "Majama! Kem cho aap?",
        "full_reply": "Majama! Kem cho? Aapni seva ma hajar chhu.",
        "intro_hint": "Kem cho! Main Gujarati mein bhi greet kar sakta hoon.",
    },
    {
        "religion": "bengali",
        "display": "Bengali",
        "patterns": [r"\bnomoshkar\b", r"\bnamaskar\s+dada\b", r"\bnamaskar\s+didi\b"],
        "reply":    "Nomoshkar! Ki khobor?",
        "full_reply": "Nomoshkar! Aapnar sheba korte pari.",
        "intro_hint": "Nomoshkar! Main Bengali greeting bhi jaanta hoon.",
    },
    {
        "religion": "tamil",
        "display": "Tamil",
        "patterns": [r"\bvanakkam\b"],
        "reply":    "Vanakkam! Eppadi irukkeenga?",
        "full_reply": "Vanakkam! Ungalukku enna seivom?",
        "intro_hint": "Vanakkam! Main Tamil mein bhi greet kar sakta hoon.",
    },
    {
        "religion": "telugu",
        "display": "Telugu",
        "patterns": [r"\bnamaskaram\b", r"\bela\s+unnaru\b"],
        "reply":    "Namaskaram! Ela unnaru?",
        "full_reply": "Namaskaram! Mee seva cheyyadaniki sadidam.",
        "intro_hint": "Namaskaram! Main Telugu tradition mein bhi greet kar sakta hoon.",
    },
    {
        "religion": "marathi",
        "display": "Marathi",
        "patterns": [r"\bnamaskar\s+kaka\b", r"\bnamskar\b", r"\bkasa\s+kay\b"],
        "reply":    "Namaskar! Kaase aahe?",
        "full_reply": "Namaskar! Tumchi seva karayala taiyar aahe mi.",
        "intro_hint": "Namaskar! Mala Marathi greeting suddhaa maahit aahe.",
    },
    {
        "religion": "rajasthani",
        "display": "Rajasthani",
        "patterns": [r"\bkhamma\s+ghani\b", r"\bkhamma\b"],
        "reply":    "Khamma Ghani Sa!",
        "full_reply": "Khamma Ghani Sa! Aapri seva mein haazir hoon.",
        "intro_hint": "Khamma Ghani! Main Rajasthani tradition mein bhi greet kar sakta hoon.",
    },
    {
        "religion": "kashmiri",
        "display": "Kashmiri/Urdu",
        "patterns": [r"\badaab\b", r"\badaab\s+arz\b"],
        "reply":    "Adaab Arz! Khush aamdeed.",
        "full_reply": "Adaab Arz! Aapka swagat hai — humessha hazir hoon.",
        "intro_hint": "Adaab Arz! Main Urdu/Kashmiri tradition mein bhi greet kar sakta hoon.",
    },
    {
        "religion": "zoroastrianism",
        "display": "Zoroastrian/Parsi",
        "patterns": [r"\bashem\s+vohu\b", r"\bahura\s+mazda\b"],
        "reply":    "Ashem Vohu! May Ahura Mazda bless you.",
        "full_reply": "Ashem Vohu! May the light of Ahura Mazda guide your path.",
        "intro_hint": "Ashem Vohu! I know Zoroastrian greetings too.",
    },
]

# Compile all patterns for fast lookup
_COMPILED: List[Dict] = []
for _entry in GREETING_DB:
    _compiled_entry = dict(_entry)
    _compiled_entry["_re"] = [
        re.compile(p, re.I | re.UNICODE)
        for p in _entry.get("patterns", [])
    ]
    if "short_form" in _entry:
        _sf = _entry["short_form"]
        _compiled_entry["_short_re"] = [
            re.compile(p, re.I | re.UNICODE)
            for p in _sf.get("patterns", [])
        ]
    _COMPILED.append(_compiled_entry)


# ── Detection ─────────────────────────────────────────────────────────────────

def detect_greeting(text: str) -> Optional[Tuple[str, str, str]]:
    """
    Checks if text contains a cultural/religious greeting.
    Returns (religion, reply_text, display_name) or None.

    The reply_text is chosen based on whether the user used the full or short form.
    """
    t = text.strip()
    for entry in _COMPILED:
        # Check long-form patterns first (they are more specific)
        for rx in entry["_re"]:
            if rx.search(t):
                reply = entry.get("full_reply") or entry.get("reply", "")
                return (entry["religion"], reply, entry["display"])
        # Short-form fallback within the same entry
        if "_short_re" in entry:
            for rx in entry["_short_re"]:
                if rx.search(t):
                    reply = entry.get("short_form", {}).get("reply") or entry.get("reply", "")
                    return (entry["religion"], reply, entry["display"])
    return None


def get_reply(detected: Any) -> str:
    """Returns the reply string from a detected greeting tuple or dict."""
    if isinstance(detected, (tuple, list)) and len(detected) >= 2:
        return detected[1]
    if isinstance(detected, dict):
        return detected.get("reply", "")
    return str(detected)


def get_intro_hint(religion: str) -> str:
    """Returns the first-time intro message for a religion."""
    for entry in GREETING_DB:
        if entry["religion"] == religion and entry.get("intro_hint"):
            return entry["intro_hint"]
    return ""


def get_stored_greeting(religion: str) -> str:
    """Returns the opening greeting Charlie should use for a known user religion."""
    # Pick the primary (first) greeting for this religion
    for entry in GREETING_DB:
        if entry["religion"] == religion:
            return entry.get("reply", "")
    return ""


# ── Culture profile store ─────────────────────────────────────────────────────

class CultureProfileStore:
    """
    Persists religion/culture per user in config/cultural_greetings.json.
    Schema: { "<user_id>": { "religion": "islam", "display": "Muslim", "greeted_first_time": true } }
    """
    _lock = threading.Lock()

    def __init__(self):
        self._file = _culture_file()

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

    def get(self, user_id: str) -> Optional[Dict]:
        with self._lock:
            return self._load().get(user_id)

    def set_religion(self, user_id: str, religion: str, display: str) -> bool:
        """Returns True if this is the FIRST time we learn this religion."""
        with self._lock:
            data = self._load()
            existing = data.get(user_id, {})
            first_time = "religion" not in existing
            existing["religion"] = religion
            existing["display"]  = display
            if first_time:
                existing["greeted_first_time"] = False
            data[user_id] = existing
            self._save(data)
            return first_time

    def mark_greeted(self, user_id: str) -> None:
        with self._lock:
            data = self._load()
            if user_id in data:
                data[user_id]["greeted_first_time"] = True
                self._save(data)

    def has_been_greeted(self, user_id: str) -> bool:
        with self._lock:
            rec = self._load().get(user_id, {})
            return rec.get("greeted_first_time", False)

    def get_religion(self, user_id: str) -> Optional[str]:
        with self._lock:
            return self._load().get(user_id, {}).get("religion")


# Global singleton
_culture_store: Optional[CultureProfileStore] = None
_cs_lock = threading.Lock()


def get_culture_store() -> CultureProfileStore:
    global _culture_store
    with _cs_lock:
        if _culture_store is None:
            _culture_store = CultureProfileStore()
        return _culture_store


# ── Session cultural greeting manager ────────────────────────────────────────

class CulturalGreetingManager:
    """
    Per-session manager.
    Call `process(user_id, text, user_name)` on every user utterance.
    Returns a reply string if Charlie should respond, else None.
    """

    def __init__(self):
        self._store = get_culture_store()
        self._session_detected: set = set()  # religions detected THIS session already

    def build_opening_greeting(self, user_id: str, user_name: str) -> str:
        """
        If user has a known religion, return a religious opening greeting.
        Otherwise return '' (the normal greeting system handles it).
        """
        religion = self._store.get_religion(user_id)
        if not religion:
            return ""
        greeting = get_stored_greeting(religion)
        name_part = f" {user_name}!" if user_name else "!"
        return greeting.rstrip("!") + name_part if greeting else ""

    def build_first_time_intro(self, assistant_name: str = "Charlie") -> str:
        """
        Intro message Charlie speaks the very first time to tell users about cultural greetings.
        Spoken ONCE and never repeated.
        """
        return (
            f"By the way, {assistant_name} can greet you in your own tradition — "
            f"Muslim, Hindu, Sikh, Christian, Gujarati, Punjabi, Bengali, Tamil and many more. "
            f"Just greet me in your way and I'll respond the same. "
            f"Aap jis tarah bhi greet karein — main waisi hi reply karunga!"
        )

    def process(
        self,
        user_id: str,
        text: str,
        user_name: str = "",
        assistant_name: str = "Charlie",
    ) -> Optional[str]:
        """
        Checks text for a cultural greeting.
        Returns the reply Charlie should speak, or None.
        """
        result = detect_greeting(text)
        if result is None:
            return None

        religion, reply, display = result

        # Store religion if new
        is_first_time = self._store.set_religion(user_id, religion, display)
        already_greeted = self._store.has_been_greeted(user_id)

        # Build the response
        name_part = f", {user_name}" if user_name else ""
        response  = f"{reply}{name_part}!"

        # First time detecting this religion in this session: add a note
        if religion not in self._session_detected:
            self._session_detected.add(religion)
            if not already_greeted:
                # Very first time ever → add the intro about the feature
                intro = get_intro_hint(religion)
                self._store.mark_greeted(user_id)
                if intro:
                    response += f" {intro}"

        return response.strip()


# Global session instance (reset each session)
_cgm: Optional[CulturalGreetingManager] = None
_cgm_lock = threading.Lock()


def get_cultural_greeting_manager() -> CulturalGreetingManager:
    global _cgm
    with _cgm_lock:
        if _cgm is None:
            _cgm = CulturalGreetingManager()
        return _cgm


def reset_cultural_greeting_manager() -> None:
    """Call at the start of each session to reset session-level state."""
    global _cgm
    with _cgm_lock:
        _cgm = CulturalGreetingManager()
