import json
import os
import sys
from pathlib import Path

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

from core.app_paths import get_config_dir

BASE_DIR    = get_base_dir()
_BUNDLED_CONFIG_FILE = (Path(sys.executable).parent / "config" / "api_keys.json") if getattr(sys, "frozen", False) else (BASE_DIR / "config" / "api_keys.json")


class _DynamicPathProxy:
    def __init__(self, getter):
        self._getter = getter

    @property
    def _path(self) -> Path:
        return self._getter()

    def __getattr__(self, item):
        return getattr(self._path, item)

    def __fspath__(self):
        return str(self._path)

    def __str__(self):
        return str(self._path)

    def __repr__(self):
        return repr(self._path)

    def __truediv__(self, other):
        return self._path / other

    def __rtruediv__(self, other):
        return Path(other) / self._path

    def __eq__(self, other):
        return self._path == other or str(self._path) == str(other)

    def __hash__(self):
        return hash(self._path)

CONFIG_DIR = _DynamicPathProxy(get_config_dir)
CONFIG_FILE = _DynamicPathProxy(lambda: get_config_dir() / "api_keys.json")


def ensure_config_dir() -> None:
    try:
        Path(CONFIG_FILE).parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    get_config_dir().mkdir(parents=True, exist_ok=True)

def config_exists() -> bool:
    return (get_config_dir() / "api_keys.json").exists() or _BUNDLED_CONFIG_FILE.exists()

def _vault_set(namespace: str, key: str, value: str) -> bool:
    """Store a credential in the DPAPI vault. False if vault unavailable."""
    try:
        from core.credential_vault import set_secret
        return bool(set_secret(namespace, key, value))
    except Exception:
        return False


def save_api_keys(gemini_api_key: str) -> bool:
    clean_key = gemini_api_key.strip()
    if not clean_key:
        return False
    from core.credential_vault import is_windows, set_secret, get_secret, has_secret, list_configured
    if is_windows():
        if set_secret("gemini", "api_key", clean_key):
            # Immediate read-back verification in memory & disk index
            readback = (get_secret("gemini", "api_key", fallback_legacy=False) or "").strip()
            if readback == clean_key and has_secret("gemini", "api_key") and "gemini/api_key" in list_configured():
                try:
                    from core.gemini import api_key
                    api_key(refresh=True)
                except Exception:
                    pass
                # Purge any plaintext key from config file if present
                try:
                    if CONFIG_FILE.exists():
                        cf_data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                        if "gemini_api_key" in cf_data:
                            cf_data.pop("gemini_api_key", None)
                            CONFIG_FILE.write_text(json.dumps(cf_data, indent=2), encoding="utf-8")
                except Exception:
                    pass
                return True
        return False
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    elif _BUNDLED_CONFIG_FILE.exists():
        try:
            data = json.loads(_BUNDLED_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    data["gemini_api_key"] = clean_key
    try:
        CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False

def load_api_keys() -> dict:
    data = {}
    if not CONFIG_FILE.exists():
        if _BUNDLED_CONFIG_FILE.exists() and _BUNDLED_CONFIG_FILE.resolve() != CONFIG_FILE.resolve():
            try:
                data = json.loads(_BUNDLED_CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
    else:
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"❌ Failed to load api_keys.json: {e}")
            return {}
    if isinstance(data, dict):
        aname = str(data.get("assistant_name") or "").strip()
        if aname.upper() in ("JARVIS", "J.A.R.V.I.S.", "J.A.R.V.I.S") or "JARVIS" in aname.upper():
            data["assistant_name"] = "CHARLIE"
    return data

def get_gemini_key() -> str | None:
    try:
        from core.credential_vault import get_secret
        k = (get_secret("gemini", "api_key", fallback_legacy=True) or "").strip()
        if k:
            return k
    except Exception:
        pass
    return None

def is_configured() -> bool:
    key = get_gemini_key()
    return bool(key and len(key.strip()) >= 10)

def get_groq_key() -> str | None:
    try:
        from core.credential_vault import get_secret
        k = get_secret("groq", "api_key")
        if k:
            return k
    except Exception:
        pass
    env_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if env_key:
        return env_key
    return load_api_keys().get("groq_api_key")

def is_groq_configured() -> bool:
    key = get_groq_key()
    return bool(key and len(key) > 10)

def save_groq_key(groq_api_key: str) -> None:
    clean_key = groq_api_key.strip()
    if clean_key and _vault_set("groq", "api_key", clean_key):
        return
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["groq_api_key"] = clean_key
    CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


_MIGRATION_DONE = False


def ensure_credentials_migrated() -> dict:
    """One-time, idempotent legacy api_keys.json -> DPAPI vault migration.

    Never prints or returns secret values; legacy file is left untouched.
    """
    global _MIGRATION_DONE
    if _MIGRATION_DONE:
        return {"status": "already_run"}
    _MIGRATION_DONE = True
    try:
        from core.credential_vault import migrate_legacy_credentials
        mig_file = CONFIG_FILE if CONFIG_FILE.exists() else _BUNDLED_CONFIG_FILE
        res = migrate_legacy_credentials(legacy_file=mig_file)
    except Exception as e:
        return {"status": f"error: {type(e).__name__}"}
    if res.get("gemini_migrated") or res.get("groq_migrated") or res.get("plugins_migrated"):
        print(
            "[CredentialVault] Migration "
            f"status={res.get('status')} "
            f"gemini={'YES' if res.get('gemini_migrated') else 'NO'} "
            f"groq={'YES' if res.get('groq_migrated') else 'NO'} "
            f"plugins={res.get('plugins_migrated', 0)}",
            flush=True,
        )
    return res


def get_assistant_name() -> str:
    """Return the configured assistant name, or 'CHARLIE' if not set."""
    val = (load_api_keys().get("assistant_name", "CHARLIE") or "CHARLIE").strip()
    if val.upper() in ("JARVIS", "J.A.R.V.I.S.", "J.A.R.V.I.S"):
        return "CHARLIE"
    return val


def get_user_name() -> str:
    """Return the configured user name for addressing."""
    return load_api_keys().get("user_name", "")


def save_assistant_config(assistant_name: str, user_name: str) -> None:
    """Persist assistant name and user name to config."""
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["assistant_name"] = assistant_name.strip() or "CHARLIE"
    data["user_name"] = user_name.strip()
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


# ── Assistant voice ──────────────────────────────────────────────────────────
# Gemini Live prebuilt voices. Names are proper nouns — identical in every
# language, so this list is safe to show verbatim in any locale.
VOICE_STYLES = {
    "Zephyr": "Bright", "Puck": "Upbeat", "Charon": "Informative",
    "Kore": "Firm", "Fenrir": "Excitable", "Leda": "Youthful",
    "Orus": "Firm", "Aoede": "Breezy", "Callirrhoe": "Easy-going",
    "Autonoe": "Bright", "Enceladus": "Breathy", "Iapetus": "Clear",
    "Umbriel": "Easy-going", "Algieba": "Smooth", "Despina": "Smooth",
    "Erinome": "Clear", "Algenib": "Gravelly", "Rasalgethi": "Informative",
    "Laomedeia": "Upbeat", "Achernar": "Soft", "Alnilam": "Firm",
    "Schedar": "Even", "Gacrux": "Mature", "Pulcherrima": "Forward",
    "Achird": "Friendly", "Zubenelgenubi": "Casual",
    "Vindemiatrix": "Gentle", "Sadachbia": "Lively",
    "Sadaltager": "Knowledgeable", "Sulafat": "Warm",
}
AVAILABLE_VOICES = list(VOICE_STYLES)
VOICE_GENDERS = {
    "Achernar": "female", "Achird": "male", "Algenib": "male",
    "Algieba": "male", "Alnilam": "male", "Aoede": "female",
    "Autonoe": "female", "Callirrhoe": "female", "Charon": "male",
    "Despina": "female", "Enceladus": "male", "Erinome": "female",
    "Fenrir": "male", "Gacrux": "female", "Iapetus": "male",
    "Kore": "female", "Laomedeia": "female", "Leda": "female",
    "Orus": "male", "Pulcherrima": "female", "Puck": "male",
    "Rasalgethi": "male", "Sadachbia": "male", "Sadaltager": "male",
    "Schedar": "male", "Sulafat": "female", "Umbriel": "male",
    "Vindemiatrix": "female", "Zephyr": "female", "Zubenelgenubi": "male",
}
DEFAULT_VOICE    = "Achird"
ASSISTANT_PERSONAS = {
    "male":   {"label": "Classic assistant", "voice": "Achird"},
    "female": {"label": "Female assistant", "voice": "Achernar"},
}
DEFAULT_PERSONA = "male"
VOICE_PROFILE_VERSION = 3


def voices_for_persona(persona: str) -> list[str]:
    choice = "female" if str(persona).strip().lower() == "female" else "male"
    return [voice for voice in AVAILABLE_VOICES if VOICE_GENDERS.get(voice) == choice]


def voice_matches_persona(voice_name: str, persona: str) -> bool:
    choice = "female" if str(persona).strip().lower() == "female" else "male"
    return VOICE_GENDERS.get(str(voice_name or "").strip()) == choice


def _persona_voice_or_default(voice_name: str, persona: str) -> str:
    return (str(voice_name).strip() if voice_matches_persona(voice_name, persona)
            else ASSISTANT_PERSONAS[persona]["voice"])


def ensure_sweet_voice_profiles() -> bool:
    """One-time upgrade to independent, gentle male/female voice profiles.

    The version marker prevents a later launch from overwriting a voice the
    user deliberately selected in Voice Studio.
    """
    ensure_config_dir()
    data = load_api_keys()
    try:
        installed_version = int(data.get("voice_profile_version", 0) or 0)
    except (TypeError, ValueError):
        installed_version = 0
    if installed_version >= VOICE_PROFILE_VERSION:
        return False
    persona = str(data.get("assistant_persona", DEFAULT_PERSONA)).strip().lower()
    persona = persona if persona in ASSISTANT_PERSONAS else DEFAULT_PERSONA
    saved = data.get("persona_voices")
    saved = saved if isinstance(saved, dict) else {}
    voices = {
        key: _persona_voice_or_default(saved.get(key, ""), key)
        for key in ASSISTANT_PERSONAS
    }
    data["assistant_persona"] = persona
    data["persona_voices"] = voices
    data["voice_name"] = voices[persona]
    data["voice_profile_version"] = VOICE_PROFILE_VERSION
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")
    return True


def get_voice() -> str:
    """Return the configured Live voice, falling back to the default if unset
    or if the stored value is not a voice we recognise."""
    data = load_api_keys()
    persona = str(data.get("assistant_persona", DEFAULT_PERSONA)).strip().lower()
    persona = persona if persona in ASSISTANT_PERSONAS else DEFAULT_PERSONA
    return _persona_voice_or_default(data.get("voice_name", ""), persona)


def get_persona_voice(persona: str) -> str:
    """Return the independently saved voice for a male/female persona."""
    choice = str(persona or "").strip().lower()
    choice = choice if choice in ASSISTANT_PERSONAS else DEFAULT_PERSONA
    data = load_api_keys()
    saved = data.get("persona_voices")
    saved = saved if isinstance(saved, dict) else {}
    return _persona_voice_or_default(saved.get(choice, ""), choice)


def save_persona_voice(persona: str, voice_name: str) -> str:
    """Save one persona's voice without changing the other persona's voice."""
    choice = str(persona or "").strip().lower()
    choice = choice if choice in ASSISTANT_PERSONAS else DEFAULT_PERSONA
    voice = _persona_voice_or_default(voice_name, choice)
    ensure_config_dir()
    data = load_api_keys()
    voices = data.get("persona_voices")
    voices = dict(voices) if isinstance(voices, dict) else {}
    voices[choice] = voice
    data["persona_voices"] = voices
    if get_assistant_persona() == choice:
        data["voice_name"] = voice
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")
    return voice


def save_voice(voice_name: str) -> None:
    """Persist the chosen Live voice. Unknown names collapse to the default so a
    bad value can never reach the API and break the session."""
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    persona = get_assistant_persona()
    v = _persona_voice_or_default(voice_name, persona)
    data["voice_name"] = v
    voices = data.get("persona_voices")
    voices = dict(voices) if isinstance(voices, dict) else {}
    voices[persona] = v
    data["persona_voices"] = voices
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


def get_assistant_persona() -> str:
    """Return the selected visual/voice profile without guessing from a name."""
    persona = str(load_api_keys().get("assistant_persona", DEFAULT_PERSONA)).strip().lower()
    return persona if persona in ASSISTANT_PERSONAS else DEFAULT_PERSONA


def get_assistant_grammar_instruction(persona: str | None = None) -> str:
    """Return a strict self-reference rule for gendered spoken languages."""
    choice = str(persona or get_assistant_persona()).strip().lower()
    if choice == "female":
        return (
            "ASSISTANT GRAMMATICAL GENDER: You are speaking as a female assistant. "
            "Whenever you refer to your own actions, abilities, feelings, or intentions in Hindi, "
            "Hinglish, Urdu, or another gendered language, always use feminine grammar. Say forms "
            "such as 'main kar sakti hoon', 'main bol sakti hoon', 'main madad karungi', and "
            "'main taiyar hoon'. Never use masculine self-forms such as 'kar sakta hoon', "
            "'bol sakta hoon', or 'karunga'. This rule applies only to your own self-reference; "
            "do not guess the user's gender."
        )
    return (
        "ASSISTANT GRAMMATICAL GENDER: You are speaking as a male assistant. "
        "Whenever you refer to your own actions, abilities, feelings, or intentions in Hindi, "
        "Hinglish, Urdu, or another gendered language, use masculine grammar, such as "
        "'main kar sakta hoon', 'main bol sakta hoon', and 'main madad karunga'. This rule applies "
        "only to your own self-reference; do not guess the user's gender."
    )


def save_assistant_persona(persona: str) -> str:
    """Persist a supported assistant profile and return its canonical key."""
    choice = str(persona or "").strip().lower()
    choice = choice if choice in ASSISTANT_PERSONAS else DEFAULT_PERSONA

    # Backend Commercial Gate Enforcement (Basic = Male only, Premium = Male + Female)
    try:
        from engine.commercial.core import get_commercial_engine
        engine = get_commercial_engine()
        allowed, reason = engine.verify_voice_access(choice)
        if not allowed:
            raise PermissionError(f"[COMMERCIAL_GATE_LOCKED] {reason}")
    except (ImportError, KeyError):
        pass

    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["assistant_persona"] = choice
    voices = data.get("persona_voices")
    voices = voices if isinstance(voices, dict) else {}
    data["voice_name"] = _persona_voice_or_default(voices.get(choice, ""), choice)
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")
    return choice


def get_wake_word_enabled() -> bool:
    """Whether local wake-word gating is on (assistant sleeps until 'Hey Charlie')."""
    return load_api_keys().get("wake_word_enabled", False)


def save_wake_word_enabled(enabled: bool) -> None:
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["wake_word_enabled"] = bool(enabled)
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


def get_push_to_talk_enabled() -> bool:
    """Hold-a-key-to-speak. When on, the mic is closed unless the chord is held."""
    return load_api_keys().get("push_to_talk_enabled", False)


def save_push_to_talk_enabled(enabled: bool) -> None:
    _save_flag("push_to_talk_enabled", enabled)


HUD_STYLES = ("core", "holo")


def get_hud_style() -> str:
    """Which centrepiece the HUD draws: classic hologram ('holo') or reactor core ('core')."""
    v = str(load_api_keys().get("hud_style", "core")).strip().lower()
    return v if v in HUD_STYLES else "core"


def save_hud_style(style: str) -> None:
    s = str(style or "").strip().lower()
    _save_flag("hud_style", s if s in HUD_STYLES else "core")


# ── Live-session tuning ──────────────────────────────────────────────────────
# Everything here is optional and has a working default, so an untouched
# config behaves exactly like a configured one. Each value is also a way out:
# if a future model dislikes one of these, set it back and nothing else changes.

def get_thinking_enabled() -> bool:
    """Whether the Live model may spend tokens thinking before it answers.

    Off by default. A voice assistant is judged on how fast it starts talking,
    and the reasoning that actually needs deliberation in this app is delegated
    to the planning tools, which run on a separate non-Live model.
    """
    return bool(load_api_keys().get("thinking_enabled", False))


def save_thinking_enabled(enabled: bool) -> None:
    _save_flag("thinking_enabled", enabled)


def get_turn_tuning() -> dict:
    """How eagerly the server decides you have stopped speaking.

    OFF by default, and that default was earned. Cutting turns shorter looks
    like a free speed win and is not: proactive audio has to judge whether an
    utterance was even addressed to the assistant, and a turn clipped early
    gives it less to judge, so it stays quiet — and the reply to your first
    sentence only arrives once your second one has given it enough context.
    That reads as the assistant being a turn behind, which is far worse than
    the fraction of a second the tuning saves.

    The defaults favor patient listening: a quiet or slow speaker gets more
    prefix audio and pause time before the server closes the turn. Users can
    still override these values in the local config when they want faster turns.
    """
    cfg = load_api_keys().get("turn_tuning")
    cfg = cfg if isinstance(cfg, dict) else {}

    def _int(key, default, lo, hi):
        try:
            return max(lo, min(hi, int(cfg.get(key, default))))
        except (TypeError, ValueError):
            return default

    return {
        "enabled":    bool(cfg.get("enabled", True)),
        "silence_ms": _int("silence_ms", 900, 200, 3000),
        "prefix_ms":  _int("prefix_ms", 300, 0, 1000),
        "slow_speech": bool(cfg.get("slow_speech", False)),
        # "high" = quicker to decide speech has ended.
        "end_sensitivity":   str(cfg.get("end_sensitivity", "low")).lower(),
        "start_sensitivity": str(cfg.get("start_sensitivity", "high")).lower(),
    }


def save_turn_tuning(values: dict) -> None:
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    cur = data.get("turn_tuning")
    cur = dict(cur) if isinstance(cur, dict) else {}
    cur.update(values or {})
    data["turn_tuning"] = cur
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


def get_proactive_audio_enabled() -> bool:
    """Whether the model gets to decide an utterance was not aimed at it and
    stay quiet.

    On by default — it is what stops the assistant answering the room. But it
    is also the first thing to switch off if replies ever seem to arrive a turn
    late: what looks like lag is usually the model having judged your previous
    sentence as not addressed to it, and only changing its mind once the next
    one arrives.

    It is now off by default, prioritising reliable direct conversations.
    """
    # Reliability matters more than filtering ambient room speech for the
    # default desktop experience. Users who enable this intentionally can still
    # opt into the more selective behaviour in their configuration.
    return bool(load_api_keys().get("proactive_audio", False))


def save_proactive_audio_enabled(enabled: bool) -> None:
    _save_flag("proactive_audio", enabled)


MEDIA_RESOLUTIONS = ("default", "low", "medium", "high")


def get_media_resolution() -> str:
    """How finely the model tokenises the screenshots and camera frames it is
    sent. 'medium' keeps on-screen text readable at a fraction of the tokens a
    full-resolution frame costs; 'low' is cheaper still but starts losing small
    text, which is most of what screen captures are for."""
    v = str(load_api_keys().get("media_resolution", "medium")).strip().lower()
    return v if v in MEDIA_RESOLUTIONS else "medium"


def save_media_resolution(value: str) -> None:
    v = str(value or "").strip().lower()
    _save_flag("media_resolution", v if v in MEDIA_RESOLUTIONS else "medium")


def _save_flag(key: str, value) -> None:
    """Read-modify-write one key without disturbing the rest of the config."""
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data[key] = bool(value) if isinstance(value, bool) else value
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


def get_brief_enabled() -> bool:
    # Starting with a long spoken news briefing blocks the first real exchange
    # and makes a two-way assistant feel unresponsive. It remains opt-in from
    # Settings for people who explicitly want it.
    return load_api_keys().get("morning_brief_enabled", False)


def save_brief_enabled(enabled: bool) -> None:
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["morning_brief_enabled"] = enabled
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


# ── Audio devices ────────────────────────────────────────────────────────────
# Stored as device NAMES, not sounddevice indices. Indices shift every time a
# USB device is plugged in or removed, so a saved index silently starts pointing
# at a different microphone. The empty string means "system default", which is
# both the factory setting and what an unresolvable saved device falls back to —
# so unplugging a headset degrades to the built-in speakers instead of crashing.

def _patch_config(**fields) -> None:
    """Read-modify-write one or more keys in api_keys.json.

    Every setter in this file open-coded this. Collapsing it here means a new
    setting is one line, and there is one place where a corrupt config file is
    handled instead of nine."""
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data.update(fields)
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


def get_input_device() -> str:
    """Microphone device name, or '' for the system default."""
    return (load_api_keys().get("input_device", "") or "").strip()


def save_input_device(name: str) -> None:
    _patch_config(input_device=(name or "").strip())


def get_output_device() -> str:
    """Speaker device name, or '' for the system default."""
    return (load_api_keys().get("output_device", "") or "").strip()


def save_output_device(name: str) -> None:
    _patch_config(output_device=(name or "").strip())


def get_plugin_enabled(plugin_name: str) -> bool:
    """Plugins are enabled by default the moment they're discovered (opt-out model)."""
    return load_api_keys().get("plugins_enabled", {}).get(plugin_name, True)


# ── Per-plugin settings ("tokens" / connection details) ───────────────────────
# Generic store so a plugin can declare its own config fields (PLUGIN_SETTINGS)
# and the settings UI renders + persists them WITHOUT any core edit — keeping the
# drop-in model intact. Values live under plugin_config[<namespace>][<key>].
# A namespace defaults to the plugin name, but a suite of plugins (e.g. the
# several printer plugins) can share ONE namespace.
def get_plugin_config(namespace: str) -> dict:
    """All stored values for a namespace (empty dict if none set yet).

    Credential fields resolve env -> DPAPI vault -> legacy plugin_config.
    """
    cfg = load_api_keys().get("plugin_config")
    val = cfg.get(namespace) if isinstance(cfg, dict) else None
    out = dict(val) if isinstance(val, dict) else {}
    try:
        from core.credential_vault import get_secret, is_secret_field, list_configured
        vns = f"plugins/{namespace}"
        names = {k for k in out if is_secret_field(k)}
        present = {str(k).lower() for k in out}
        for vk in list_configured(vns):
            if vk not in present:
                names.add(vk)
        for k in names:
            v = get_secret(vns, k, fallback_legacy=False)
            if v:
                out[k] = v
    except Exception:
        pass
    return out


def get_plugin_setting(namespace: str, key: str, default=None):
    """A single value from a namespace, or `default` if unset."""
    return get_plugin_config(namespace).get(key, default)


def save_plugin_config(namespace: str, values: dict) -> None:
    """Merge `values` into a namespace's stored config (read-modify-write, like
    every other helper here). Only the provided keys are touched.

    Credential fields go to the DPAPI vault; they reach plaintext JSON only
    when the vault is unavailable. Clearing a credential removes it from both."""
    values = dict(values or {})
    try:
        from core.credential_vault import delete_secret, is_secret_field
        vns = f"plugins/{namespace}"
        for k in list(values.keys()):
            v = values[k]
            if not is_secret_field(k) or not isinstance(v, str):
                continue
            sv = v.strip()
            if sv:
                if _vault_set(vns, k, sv):
                    values.pop(k)          # legacy JSON value left untouched
            else:
                delete_secret(vns, k)      # explicit clear -> "" written below
    except Exception:
        pass
    if not values:
        return
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    pc = data.get("plugin_config")
    if not isinstance(pc, dict):
        pc = {}
    cur = pc.get(namespace)
    if not isinstance(cur, dict):
        cur = {}
    cur.update(values)
    pc[namespace] = cur
    data["plugin_config"] = pc
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


def save_plugin_enabled(plugin_name: str, enabled: bool) -> None:
    ensure_config_dir()
    data: dict = {}
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    plugins_cfg = data.get("plugins_enabled")
    if not isinstance(plugins_cfg, dict):
        plugins_cfg = {}
    plugins_cfg[plugin_name] = enabled
    data["plugins_enabled"] = plugins_cfg
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


set_plugin_enabled = save_plugin_enabled


def get_slow_speech_enabled() -> bool:
    """Whether CHARLIE patiently listens through longer pauses between words."""
    return bool(get_turn_tuning().get("slow_speech", False))


def save_slow_speech_enabled(enabled: bool) -> None:
    """Apply a safe endpointing preset for normal or deliberately slow speech."""
    slow = bool(enabled)
    save_turn_tuning({
        "enabled": True,
        "slow_speech": slow,
        "silence_ms": 2200 if slow else 900,
        "prefix_ms": 500 if slow else 300,
        "end_sensitivity": "low",
        "start_sensitivity": "high",
    })


def get_hud_style() -> str:
    """Return the configured HUD style: 'core' or 'holo'."""
    data = load_api_keys()
    style = str(data.get("hud_style", "core")).strip().lower()
    return style if style in ("core", "holo") else "core"


def save_hud_style(style: str) -> None:
    """Persist the HUD visual style ('core' or 'holo')."""
    ensure_config_dir()
    data = load_api_keys()
    choice = str(style or "core").strip().lower()
    data["hud_style"] = choice if choice in ("core", "holo") else "core"
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


def get_custom_voice_id() -> str:
    """Return user-configured ElevenLabs custom cloned voice ID if any."""
    return str(load_api_keys().get("elevenlabs_voice_id", "")).strip()


def save_custom_voice_id(voice_id: str) -> None:
    """Save custom ElevenLabs cloned voice ID."""
    ensure_config_dir()
    data = load_api_keys()
    data["elevenlabs_voice_id"] = str(voice_id).strip()
    CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")


