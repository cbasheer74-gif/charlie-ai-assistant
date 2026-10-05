"""
Comprehensive Language Registry for Charlie AI Assistant.
Supports all Indian regional languages and major world languages across all continents.
Includes neural voice mappings (EdgeTTS), Whisper STT language codes,
Unicode script ranges, and conversational prompting rules.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LanguageInfo:
    code: str              # Standard ISO-639-1 / Whisper code
    name: str              # English name (e.g., 'Marathi')
    native_name: str       # Native script name (e.g., 'मराठी')
    region: str            # Region/Category: 'Regional (India)', 'Asia', 'Europe', 'Americas', 'Middle East', 'Africa'
    tts_female: str        # EdgeTTS female neural voice
    tts_male: str          # EdgeTTS male neural voice
    whisper_code: str      # Whisper STT language code
    script_regex: Optional[str] = None # Script Unicode range regex if distinctive


# Comprehensive catalogue of Regional and Global languages
LANGUAGES: dict[str, LanguageInfo] = {
    # ── Indian Regional & Classical Languages ──
    "hindi": LanguageInfo(
        code="hi", name="Hindi", native_name="हिन्दी",
        region="Regional (India)",
        tts_female="hi-IN-SwaraNeural", tts_male="hi-IN-MadhurNeural",
        whisper_code="hi", script_regex=r"[\u0900-\u097F]"
    ),
    "hinglish": LanguageInfo(
        code="hinglish", name="Hinglish", native_name="Hinglish",
        region="Regional (India)",
        tts_female="en-IN-NeerjaNeural", tts_male="en-IN-PrabhatNeural",
        whisper_code="en"
    ),
    "marathi": LanguageInfo(
        code="mr", name="Marathi", native_name="मराठी",
        region="Regional (India)",
        tts_female="mr-IN-AarohiNeural", tts_male="mr-IN-ManoharNeural",
        whisper_code="mr", script_regex=r"[\u0900-\u097F]"
    ),
    "bengali": LanguageInfo(
        code="bn", name="Bengali", native_name="বাংলা",
        region="Regional (India)",
        tts_female="bn-IN-TanishaaNeural", tts_male="bn-IN-BashkarNeural",
        whisper_code="bn", script_regex=r"[\u0980-\u09FF]"
    ),
    "tamil": LanguageInfo(
        code="ta", name="Tamil", native_name="தமிழ்",
        region="Regional (India)",
        tts_female="ta-IN-PallaviNeural", tts_male="ta-IN-ValluvarNeural",
        whisper_code="ta", script_regex=r"[\u0B80-\u0BFF]"
    ),
    "telugu": LanguageInfo(
        code="te", name="Telugu", native_name="తెలుగు",
        region="Regional (India)",
        tts_female="te-IN-ShrutiNeural", tts_male="te-IN-MohanNeural",
        whisper_code="te", script_regex=r"[\u0C00-\u0C7F]"
    ),
    "gujarati": LanguageInfo(
        code="gu", name="Gujarati", native_name="ગુજરાતી",
        region="Regional (India)",
        tts_female="gu-IN-DhwaniNeural", tts_male="gu-IN-NiranjanNeural",
        whisper_code="gu", script_regex=r"[\u0A80-\u0AFF]"
    ),
    "kannada": LanguageInfo(
        code="kn", name="Kannada", native_name="ಕನ್ನಡ",
        region="Regional (India)",
        tts_female="kn-IN-SapnaNeural", tts_male="kn-IN-GaganNeural",
        whisper_code="kn", script_regex=r"[\u0C80-\u0CFF]"
    ),
    "malayalam": LanguageInfo(
        code="ml", name="Malayalam", native_name="മലയാളം",
        region="Regional (India)",
        tts_female="ml-IN-SobhanaNeural", tts_male="ml-IN-MidhunNeural",
        whisper_code="ml", script_regex=r"[\u0D00-\u0D7F]"
    ),
    "punjabi": LanguageInfo(
        code="pa", name="Punjabi", native_name="ਪੰਜਾਬੀ",
        region="Regional (India)",
        tts_female="pa-IN-OjasNeural", tts_male="pa-IN-OjasNeural",
        whisper_code="pa", script_regex=r"[\u0A00-\u0A7F]"
    ),
    "urdu": LanguageInfo(
        code="ur", name="Urdu", native_name="اردو",
        region="Regional (India)",
        tts_female="ur-PK-UzmaNeural", tts_male="ur-PK-AsadNeural",
        whisper_code="ur", script_regex=r"[\u0600-\u06FF]"
    ),
    "odia": LanguageInfo(
        code="or", name="Odia", native_name="ଓଡ଼ିଆ",
        region="Regional (India)",
        tts_female="or-IN-SubhasiniNeural", tts_male="or-IN-SukantaNeural",
        whisper_code="or", script_regex=r"[\u0B00-\u0B7F]"
    ),
    "assamese": LanguageInfo(
        code="as", name="Assamese", native_name="অসমীয়া",
        region="Regional (India)",
        tts_female="as-IN-YashicaNeural", tts_male="as-IN-PriyomNeural",
        whisper_code="as", script_regex=r"[\u0980-\u09FF]"
    ),
    "sanskrit": LanguageInfo(
        code="sa", name="Sanskrit", native_name="संस्कृतम्",
        region="Regional (India)",
        tts_female="hi-IN-SwaraNeural", tts_male="hi-IN-MadhurNeural",
        whisper_code="sa", script_regex=r"[\u0900-\u097F]"
    ),
    "bhojpuri": LanguageInfo(
        code="bho", name="Bhojpuri", native_name="भोजपुरी",
        region="Regional (India)",
        tts_female="hi-IN-SwaraNeural", tts_male="hi-IN-MadhurNeural",
        whisper_code="hi", script_regex=r"[\u0900-\u097F]"
    ),
    "maithili": LanguageInfo(
        code="mai", name="Maithili", native_name="मैथिली",
        region="Regional (India)",
        tts_female="hi-IN-SwaraNeural", tts_male="hi-IN-MadhurNeural",
        whisper_code="hi", script_regex=r"[\u0900-\u097F]"
    ),
    "konkani": LanguageInfo(
        code="kok", name="Konkani", native_name="कोंकणी",
        region="Regional (India)",
        tts_female="mr-IN-AarohiNeural", tts_male="mr-IN-ManoharNeural",
        whisper_code="mr", script_regex=r"[\u0900-\u097F]"
    ),
    "nepali": LanguageInfo(
        code="ne", name="Nepali", native_name="नेपाली",
        region="Regional (South Asia)",
        tts_female="ne-NP-HemkalaNeural", tts_male="ne-NP-SagarNeural",
        whisper_code="ne", script_regex=r"[\u0900-\u097F]"
    ),
    "sinhala": LanguageInfo(
        code="si", name="Sinhala", native_name="සිංහල",
        region="Regional (South Asia)",
        tts_female="si-LK-ThiliniNeural", tts_male="si-LK-SameeraNeural",
        whisper_code="si", script_regex=r"[\u0D80-\u0DFF]"
    ),
    "sindhi": LanguageInfo(
        code="sd", name="Sindhi", native_name="سنڌي",
        region="Regional (South Asia)",
        tts_female="ur-PK-UzmaNeural", tts_male="ur-PK-AsadNeural",
        whisper_code="sd", script_regex=r"[\u0600-\u06FF]"
    ),

    # ── Major World Languages ──
    "english": LanguageInfo(
        code="en", name="English", native_name="English",
        region="Global",
        tts_female="en-US-JennyNeural", tts_male="en-US-GuyNeural",
        whisper_code="en"
    ),
    "spanish": LanguageInfo(
        code="es", name="Spanish", native_name="Español",
        region="Europe & Americas",
        tts_female="es-ES-ElviraNeural", tts_male="es-ES-AlvaroNeural",
        whisper_code="es"
    ),
    "french": LanguageInfo(
        code="fr", name="French", native_name="Français",
        region="Europe & Americas",
        tts_female="fr-FR-DeniseNeural", tts_male="fr-FR-HenriNeural",
        whisper_code="fr"
    ),
    "german": LanguageInfo(
        code="de", name="German", native_name="Deutsch",
        region="Europe",
        tts_female="de-DE-KatjaNeural", tts_male="de-DE-ConradNeural",
        whisper_code="de"
    ),
    "italian": LanguageInfo(
        code="it", name="Italian", native_name="Italiano",
        region="Europe",
        tts_female="it-IT-ElsaNeural", tts_male="it-IT-DiegoNeural",
        whisper_code="it"
    ),
    "portuguese": LanguageInfo(
        code="pt", name="Portuguese", native_name="Português",
        region="Europe & Americas",
        tts_female="pt-BR-FranciscaNeural", tts_male="pt-BR-AntonioNeural",
        whisper_code="pt"
    ),
    "russian": LanguageInfo(
        code="ru", name="Russian", native_name="Русский",
        region="Europe & Asia",
        tts_female="ru-RU-SvetlanaNeural", tts_male="ru-RU-DmitryNeural",
        whisper_code="ru", script_regex=r"[\u0400-\u04FF]"
    ),
    "japanese": LanguageInfo(
        code="ja", name="Japanese", native_name="日本語",
        region="Asia",
        tts_female="ja-JP-NanamiNeural", tts_male="ja-JP-KeitaNeural",
        whisper_code="ja", script_regex=r"[\u3040-\u30FF]"
    ),
    "chinese": LanguageInfo(
        code="zh", name="Chinese (Mandarin)", native_name="中文 (简体)",
        region="Asia",
        tts_female="zh-CN-XiaoxiaoNeural", tts_male="zh-CN-YunjianNeural",
        whisper_code="zh", script_regex=r"[\u4E00-\u9FFF]"
    ),
    "cantonese": LanguageInfo(
        code="yue", name="Chinese (Cantonese)", native_name="粵語",
        region="Asia",
        tts_female="zh-HK-HiuMaanNeural", tts_male="zh-HK-WanLungNeural",
        whisper_code="zh", script_regex=r"[\u4E00-\u9FFF]"
    ),
    "taiwanese": LanguageInfo(
        code="zh-tw", name="Chinese (Taiwan Traditional)", native_name="中文 (繁體)",
        region="Asia",
        tts_female="zh-TW-HsiaoChenNeural", tts_male="zh-TW-YunJheNeural",
        whisper_code="zh", script_regex=r"[\u4E00-\u9FFF]"
    ),
    "korean": LanguageInfo(
        code="ko", name="Korean", native_name="한국어",
        region="Asia",
        tts_female="ko-KR-SunHiNeural", tts_male="ko-KR-InJoonNeural",
        whisper_code="ko", script_regex=r"[\uAC00-\uD7AF]"
    ),
    "arabic": LanguageInfo(
        code="ar", name="Arabic", native_name="العربية",
        region="Middle East & Africa",
        tts_female="ar-SA-ZariyahNeural", tts_male="ar-SA-HamedNeural",
        whisper_code="ar", script_regex=r"[\u0600-\u06FF]"
    ),
    "turkish": LanguageInfo(
        code="tr", name="Turkish", native_name="Türkçe",
        region="Europe & Middle East",
        tts_female="tr-TR-EmelNeural", tts_male="tr-TR-AhmetNeural",
        whisper_code="tr"
    ),
    "dutch": LanguageInfo(
        code="nl", name="Dutch", native_name="Nederlands",
        region="Europe",
        tts_female="nl-NL-ColetteNeural", tts_male="nl-NL-MaartenNeural",
        whisper_code="nl"
    ),
    "polish": LanguageInfo(
        code="pl", name="Polish", native_name="Polski",
        region="Europe",
        tts_female="pl-PL-AgnieszkaNeural", tts_male="pl-PL-MarekNeural",
        whisper_code="pl"
    ),
    "indonesian": LanguageInfo(
        code="id", name="Indonesian", native_name="Bahasa Indonesia",
        region="Asia",
        tts_female="id-ID-GadisNeural", tts_male="id-ID-ArdiNeural",
        whisper_code="id"
    ),
    "malay": LanguageInfo(
        code="ms", name="Malay", native_name="Bahasa Melayu",
        region="Asia",
        tts_female="ms-MY-YasminNeural", tts_male="ms-MY-OsmanNeural",
        whisper_code="ms"
    ),
    "vietnamese": LanguageInfo(
        code="vi", name="Vietnamese", native_name="Tiếng Việt",
        region="Asia",
        tts_female="vi-VN-HoaiMyNeural", tts_male="vi-VN-NamMinhNeural",
        whisper_code="vi"
    ),
    "thai": LanguageInfo(
        code="th", name="Thai", native_name="ไทย",
        region="Asia",
        tts_female="th-TH-PremwadeeNeural", tts_male="th-TH-NiwatNeural",
        whisper_code="th", script_regex=r"[\u0E00-\u0E7F]"
    ),
    "filipino": LanguageInfo(
        code="fil", name="Filipino (Tagalog)", native_name="Filipino",
        region="Asia",
        tts_female="fil-PH-BlessicaNeural", tts_male="fil-PH-AngeloNeural",
        whisper_code="tl"
    ),
    "persian": LanguageInfo(
        code="fa", name="Persian (Farsi)", native_name="فارسی",
        region="Middle East",
        tts_female="fa-IR-DilaraNeural", tts_male="fa-IR-FaridNeural",
        whisper_code="fa", script_regex=r"[\u0600-\u06FF]"
    ),
    "hebrew": LanguageInfo(
        code="he", name="Hebrew", native_name="עברית",
        region="Middle East",
        tts_female="he-IL-HilaNeural", tts_male="he-IL-AvriNeural",
        whisper_code="he", script_regex=r"[\u0590-\u05FF]"
    ),
    "ukrainian": LanguageInfo(
        code="uk", name="Ukrainian", native_name="Українська",
        region="Europe",
        tts_female="uk-UA-PolinaNeural", tts_male="uk-UA-OstapNeural",
        whisper_code="uk", script_regex=r"[\u0400-\u04FF]"
    ),
    "greek": LanguageInfo(
        code="el", name="Greek", native_name="Ελληνικά",
        region="Europe",
        tts_female="el-GR-AthinaNeural", tts_male="el-GR-NestorasNeural",
        whisper_code="el", script_regex=r"[\u0370-\u03FF]"
    ),
    "swedish": LanguageInfo(
        code="sv", name="Swedish", native_name="Svenska",
        region="Europe",
        tts_female="sv-SE-SofieNeural", tts_male="sv-SE-MattiasNeural",
        whisper_code="sv"
    ),
    "norwegian": LanguageInfo(
        code="nb", name="Norwegian", native_name="Norsk",
        region="Europe",
        tts_female="nb-NO-PernilleNeural", tts_male="nb-NO-FinnNeural",
        whisper_code="no"
    ),
    "danish": LanguageInfo(
        code="da", name="Danish", native_name="Dansk",
        region="Europe",
        tts_female="da-DK-ChristelNeural", tts_male="da-DK-JeppeNeural",
        whisper_code="da"
    ),
    "finnish": LanguageInfo(
        code="fi", name="Finnish", native_name="Suomi",
        region="Europe",
        tts_female="fi-FI-NooraNeural", tts_male="fi-FI-HarriNeural",
        whisper_code="fi"
    ),
    "czech": LanguageInfo(
        code="cs", name="Czech", native_name="Čeština",
        region="Europe",
        tts_female="cs-CZ-VlastaNeural", tts_male="cs-CZ-AntoninNeural",
        whisper_code="cs"
    ),
    "romanian": LanguageInfo(
        code="ro", name="Romanian", native_name="Română",
        region="Europe",
        tts_female="ro-RO-AlinaNeural", tts_male="ro-RO-EmilNeural",
        whisper_code="ro"
    ),
    "hungarian": LanguageInfo(
        code="hu", name="Hungarian", native_name="Magyar",
        region="Europe",
        tts_female="hu-HU-NoemiNeural", tts_male="hu-HU-TamasNeural",
        whisper_code="hu"
    ),
    "swahili": LanguageInfo(
        code="sw", name="Swahili", native_name="Kiswahili",
        region="Africa",
        tts_female="sw-KE-ZuriNeural", tts_male="sw-KE-RafikiNeural",
        whisper_code="sw"
    ),
    "afrikaans": LanguageInfo(
        code="af", name="Afrikaans", native_name="Afrikaans",
        region="Africa",
        tts_female="af-ZA-AdriNeural", tts_male="af-ZA-WillemNeural",
        whisper_code="af"
    ),
    "bulgarian": LanguageInfo(
        code="bg", name="Bulgarian", native_name="Български",
        region="Europe",
        tts_female="bg-BG-KalinaNeural", tts_male="bg-BG-BorislavNeural",
        whisper_code="bg", script_regex=r"[\u0400-\u04FF]"
    ),
    "croatian": LanguageInfo(
        code="hr", name="Croatian", native_name="Hrvatski",
        region="Europe",
        tts_female="hr-HR-GabrijelaNeural", tts_male="hr-HR-SreckoNeural",
        whisper_code="hr"
    ),
    "slovak": LanguageInfo(
        code="sk", name="Slovak", native_name="Slovenčina",
        region="Europe",
        tts_female="sk-SK-ViktoriaNeural", tts_male="sk-SK-LukasNeural",
        whisper_code="sk"
    ),
    "slovenian": LanguageInfo(
        code="sl", name="Slovenian", native_name="Slovenščina",
        region="Europe",
        tts_female="sl-SI-PetraNeural", tts_male="sl-SI-RokNeural",
        whisper_code="sl"
    ),
    "serbian": LanguageInfo(
        code="sr", name="Serbian", native_name="Српски",
        region="Europe",
        tts_female="sr-RS-SophieNeural", tts_male="sr-RS-NicholasNeural",
        whisper_code="sr", script_regex=r"[\u0400-\u04FF]"
    ),
    "lithuanian": LanguageInfo(
        code="lt", name="Lithuanian", native_name="Lietuvių",
        region="Europe",
        tts_female="lt-LT-OnaNeural", tts_male="lt-LT-LeonasNeural",
        whisper_code="lt"
    ),
    "latvian": LanguageInfo(
        code="lv", name="Latvian", native_name="Latviešu",
        region="Europe",
        tts_female="lv-LV-EveritaNeural", tts_male="lv-LV-NilsNeural",
        whisper_code="lv"
    ),
    "estonian": LanguageInfo(
        code="et", name="Estonian", native_name="Eesti",
        region="Europe",
        tts_female="et-EE-AnuNeural", tts_male="et-EE-KertNeural",
        whisper_code="et"
    ),
    "irish": LanguageInfo(
        code="ga", name="Irish", native_name="Gaeilge",
        region="Europe",
        tts_female="ga-IE-OrlaNeural", tts_male="ga-IE-ColmNeural",
        whisper_code="ga"
    ),
    "welsh": LanguageInfo(
        code="cy", name="Welsh", native_name="Cymraeg",
        region="Europe",
        tts_female="cy-GB-NiaNeural", tts_male="cy-GB-AledNeural",
        whisper_code="cy"
    ),
    "catalan": LanguageInfo(
        code="ca", name="Catalan", native_name="Català",
        region="Europe",
        tts_female="ca-ES-JoanaNeural", tts_male="ca-ES-EnricNeural",
        whisper_code="ca"
    ),
    "galician": LanguageInfo(
        code="gl", name="Galician", native_name="Galego",
        region="Europe",
        tts_female="gl-ES-SabelaNeural", tts_male="gl-ES-RoiNeural",
        whisper_code="gl"
    ),
    "basque": LanguageInfo(
        code="eu", name="Basque", native_name="Euskara",
        region="Europe",
        tts_female="eu-ES-AinhoaNeural", tts_male="eu-ES-AnderNeural",
        whisper_code="eu"
    ),
    "icelandic": LanguageInfo(
        code="is", name="Icelandic", native_name="Íslenska",
        region="Europe",
        tts_female="is-IS-GudrunNeural", tts_male="is-IS-GunnarNeural",
        whisper_code="is"
    ),
    "albanian": LanguageInfo(
        code="sq", name="Albanian", native_name="Shqip",
        region="Europe",
        tts_female="sq-AL-AnilaNeural", tts_male="sq-AL-IlirNeural",
        whisper_code="sq"
    ),
    "macedonian": LanguageInfo(
        code="mk", name="Macedonian", native_name="Македонски",
        region="Europe",
        tts_female="mk-MK-MarijaNeural", tts_male="mk-MK-AleksandarNeural",
        whisper_code="mk", script_regex=r"[\u0400-\u04FF]"
    ),
    "bosnian": LanguageInfo(
        code="bs", name="Bosnian", native_name="Bosanski",
        region="Europe",
        tts_female="bs-BA-VesnaNeural", tts_male="bs-BA-GoranNeural",
        whisper_code="bs"
    ),
    "maltese": LanguageInfo(
        code="mt", name="Maltese", native_name="Malti",
        region="Europe",
        tts_female="mt-MT-GraceNeural", tts_male="mt-MT-JosephNeural",
        whisper_code="mt"
    ),
    "azerbaijani": LanguageInfo(
        code="az", name="Azerbaijani", native_name="Azərbaycan",
        region="Middle East & Asia",
        tts_female="az-AZ-BanuNeural", tts_male="az-AZ-BabekNeural",
        whisper_code="az"
    ),
    "kazakh": LanguageInfo(
        code="kk", name="Kazakh", native_name="Қазақша",
        region="Asia",
        tts_female="kk-KZ-AigulNeural", tts_male="kk-KZ-DauletNeural",
        whisper_code="kk", script_regex=r"[\u0400-\u04FF]"
    ),
    "uzbek": LanguageInfo(
        code="uz", name="Uzbek", native_name="Oʻzbekcha",
        region="Asia",
        tts_female="uz-UZ-MadinaNeural", tts_male="uz-UZ-SardorNeural",
        whisper_code="uz"
    ),
    "amharic": LanguageInfo(
        code="am", name="Amharic", native_name="አማርኛ",
        region="Africa",
        tts_female="am-ET-MekdesNeural", tts_male="am-ET-AmehaNeural",
        whisper_code="am", script_regex=r"[\u1200-\u137F]"
    ),
    "somali": LanguageInfo(
        code="so", name="Somali", native_name="Soomaali",
        region="Africa",
        tts_female="so-SO-UbaxNeural", tts_male="so-SO-MuuseNeural",
        whisper_code="so"
    ),
    "zulu": LanguageInfo(
        code="zu", name="Zulu", native_name="isiZulu",
        region="Africa",
        tts_female="zu-ZA-ThandoNeural", tts_male="zu-ZA-ThembaNeural",
        whisper_code="zu"
    ),
}

# Lookup aliases (by ISO code, lowercase name, native name, etc.)
_ALIAS_LOOKUP: dict[str, LanguageInfo] = {}
for key, info in LANGUAGES.items():
    _ALIAS_LOOKUP[key.lower()] = info
    _ALIAS_LOOKUP[info.code.lower()] = info
    _ALIAS_LOOKUP[info.name.lower()] = info
    _ALIAS_LOOKUP[info.native_name.lower()] = info
    if info.whisper_code:
        _ALIAS_LOOKUP[info.whisper_code.lower()] = info

# Add common synonyms and alternate spellings
_SYNONYMS = {
    "oriya": "odia",
    "asamiya": "assamese",
    "oxomiya": "assamese",
    "bangla": "bengali",
    "mandarin": "chinese",
    "standard chinese": "chinese",
    "zh-cn": "chinese",
    "farsi": "persian",
    "tagalog": "filipino",
    "castilian": "spanish",
    "español": "spanish",
    "deutsch": "german",
    "français": "french",
    "italiano": "italian",
    "português": "portuguese",
    "nihongo": "japanese",
    "hangugeo": "korean",
    "arabi": "arabic",
    "sanskrita": "sanskrit",
}
for syn, canonical in _SYNONYMS.items():
    if canonical in LANGUAGES:
        _ALIAS_LOOKUP[syn.lower()] = LANGUAGES[canonical]


def resolve_language(query: str | None) -> Optional[LanguageInfo]:
    """Resolve any name, code, or alias to canonical LanguageInfo."""
    if not query:
        return None
    q = query.strip().lower()
    return _ALIAS_LOOKUP.get(q)


def get_all_language_keys() -> set[str]:
    """Set of all valid language keys including 'auto'."""
    keys = {"auto", "automatic"}
    keys.update(LANGUAGES.keys())
    for info in LANGUAGES.values():
        keys.add(info.code)
        keys.add(info.whisper_code)
    for syn in _SYNONYMS:
        keys.add(syn)
    return keys


def get_language_choices_ui() -> list[tuple[str, str]]:
    """
    Structured list of (label, key) for UI dropdowns.
    Categorized with Auto language first, then common/Indian regional, followed by World languages.
    """
    choices: list[tuple[str, str]] = [
        ("Auto language (Detect)", "auto"),
        ("English", "english"),
        ("Hindi (हिन्दी)", "hindi"),
        ("Hinglish", "hinglish"),
    ]

    # Indian Regional & South Asian
    regional_keys = [
        "marathi", "bengali", "tamil", "telugu", "gujarati", "kannada",
        "malayalam", "punjabi", "urdu", "odia", "assamese", "bhojpuri",
        "maithili", "sanskrit", "konkani", "nepali", "sinhala", "sindhi"
    ]
    for rk in regional_keys:
        if rk in LANGUAGES:
            info = LANGUAGES[rk]
            choices.append((f"{info.name} ({info.native_name})", rk))

    # Major World Languages sorted alphabetically
    world_keys = sorted(
        [k for k in LANGUAGES if k not in regional_keys and k not in ("english", "hindi", "hinglish")],
        key=lambda x: LANGUAGES[x].name
    )
    for wk in world_keys:
        info = LANGUAGES[wk]
        choices.append((f"{info.name} ({info.native_name})", wk))

    return choices


def get_language_voice(lang_query: str | None, is_female: bool = True) -> Optional[str]:
    """Retrieve optimal EdgeTTS Neural voice for any language."""
    info = resolve_language(lang_query)
    if not info:
        return None
    return info.tts_female if is_female else info.tts_male


def get_whisper_code(lang_query: str | None) -> Optional[str]:
    """Resolve language to Whisper 2-letter ISO code."""
    if not lang_query or lang_query.strip().lower() in ("auto", "automatic", "none", ""):
        return None
    info = resolve_language(lang_query)
    if info:
        return info.whisper_code
    return lang_query.strip().lower()[:2]


def detect_language_script(text: str) -> Optional[LanguageInfo]:
    """Detect language from distinct Unicode script ranges and keywords."""
    if not text:
        return None

    # Japanese Hiragana/Katakana before CJK
    if re.search(r"[\u3040-\u30FF]", text):
        return LANGUAGES["japanese"]
    # Korean Hangul
    if re.search(r"[\uAC00-\uD7AF]", text):
        return LANGUAGES["korean"]
    # Chinese CJK
    if re.search(r"[\u4E00-\u9FFF\u3400-\u4DBF]", text):
        return LANGUAGES["chinese"]
    # Greek
    if re.search(r"[\u0370-\u03FF]", text):
        return LANGUAGES["greek"]
    # Hebrew
    if re.search(r"[\u0590-\u05FF]", text):
        return LANGUAGES["hebrew"]
    # Thai
    if re.search(r"[\u0E00-\u0E7F]", text):
        return LANGUAGES["thai"]
    # Amharic
    if re.search(r"[\u1200-\u137F]", text):
        return LANGUAGES["amharic"]
    # Sinhala
    if re.search(r"[\u0D80-\u0DFF]", text):
        return LANGUAGES["sinhala"]
    # Tamil
    if re.search(r"[\u0B80-\u0BFF]", text):
        return LANGUAGES["tamil"]
    # Telugu
    if re.search(r"[\u0C00-\u0C7F]", text):
        return LANGUAGES["telugu"]
    # Kannada
    if re.search(r"[\u0C80-\u0CFF]", text):
        return LANGUAGES["kannada"]
    # Malayalam
    if re.search(r"[\u0D00-\u0D7F]", text):
        return LANGUAGES["malayalam"]
    # Gujarati
    if re.search(r"[\u0A80-\u0AFF]", text):
        return LANGUAGES["gujarati"]
    # Punjabi Gurmukhi
    if re.search(r"[\u0A00-\u0A7F]", text):
        return LANGUAGES["punjabi"]
    # Odia
    if re.search(r"[\u0B00-\u0B7F]", text):
        return LANGUAGES["odia"]
    # Bengali / Assamese
    if re.search(r"[\u0980-\u09FF]", text):
        if any(ch in text for ch in ("\u09F0", "\u09F1")) or any(w in text for w in ("অসমীয়া", "আছোঁ", "কৰক")):
            return LANGUAGES["assamese"]
        return LANGUAGES["bengali"]
    # Arabic / Urdu / Persian
    if re.search(r"[\u0600-\u06FF]", text):
        if any(w in text for w in ("ہیں", "کیا", "آپ", "ہوں", "کے", "کی", "سے", "نہیں", "شکریہ")):
            return LANGUAGES["urdu"]
        if any(w in text for w in ("سلام", "خوب", "است", "من", "می", "این", "چه")):
            return LANGUAGES["persian"]
        return LANGUAGES["arabic"]
    # Cyrillic
    if re.search(r"[\u0400-\u04FF]", text):
        if any(ch in text for ch in ("є", "і", "ї", "ґ")):
            return LANGUAGES["ukrainian"]
        return LANGUAGES["russian"]
    # Devanagari (Marathi vs Nepali vs Hindi)
    if re.search(r"[\u0900-\u097F]", text):
        marathi_markers = ("आहे", "नाही", "करा", "सांगा", "नमस्कार", "कसे", "माझे", "काय", "झाले")
        if any(w in text for w in marathi_markers):
            return LANGUAGES["marathi"]
        nepali_markers = ("छ", "छैन", "गर्छ", "नमस्ते", "तपाईं", "हामी")
        if any(w in text for w in nepali_markers):
            return LANGUAGES["nepali"]
        return LANGUAGES["hindi"]

    return None


def get_language_prompt_rule(lang_query: str | None) -> str:
    """Generate dynamic LLM system instruction rule for active language."""
    if not lang_query or lang_query.strip().lower() in ("auto", "automatic"):
        return (
            "Mirror the user's current language naturally across English, Hindi, Hinglish, "
            "Marathi, Bengali, Tamil, Telugu, Gujarati, Kannada, Malayalam, Punjabi, Urdu, "
            "and all regional and international languages without asking."
        )
    info = resolve_language(lang_query)
    if info:
        return (
            f"Always reply fluently and conversationally in {info.name} ({info.native_name}). "
            f"Honor regional idioms, polite cultural salutations, and tone appropriate for {info.name}."
        )
    clean = lang_query.strip().title()
    return f"Reply naturally in conversational {clean} or mirror the user's active spoken language."
