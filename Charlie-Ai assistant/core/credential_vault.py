"""core/credential_vault.py — Windows DPAPI encrypted credential vault for CHARLIE.

Production security:
1. Credentials encrypted via Windows DPAPI (CryptProtectData / CryptUnprotectData).
2. Protection scope: CURRENT USER (user account bound; no machine-wide exposure).
3. Vault storage: %LOCALAPPDATA%\\CharlieAI\\credentials.dat (outside repository & EXE).
4. Atomic writes via temp file flush + os.replace.
5. Strict priority resolution:
   Environment Variable -> Windows DPAPI Vault -> Legacy config/api_keys.json fallback.
6. Safe migration: encrypt -> write -> read back -> verify before marking migrated.
7. Zero plaintext credential leaks in logs or list APIs.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("charlie.core.credential_vault")

VAULT_VERSION = 1
CRYPTPROTECT_UI_FORBIDDEN = 0x01

if getattr(sys, "frozen", False):
    _BASE_DIR = Path(sys.executable).parent
else:
    _BASE_DIR = Path(__file__).resolve().parent.parent
_LEGACY_CONFIG = _BASE_DIR / "config" / "api_keys.json"

# Field-name fragments treated as credentials. Kept identical to
# core/plugin_loader.PluginRegistry.is_configured so both agree.
SECRET_FIELD_TERMS = ("token", "key", "secret", "client_id", "password", "auth", "credentials")


def is_secret_field(field_name: str) -> bool:
    """Return True if a config field name denotes a credential."""
    name = str(field_name or "").lower()
    return any(t in name for t in SECRET_FIELD_TERMS)


def is_windows() -> bool:
    """Return True if running on Windows platform."""
    return os.name == "nt"


def get_vault_path() -> Path:
    """Return absolute path to credentials.dat in %LOCALAPPDATA%\\CharlieAI."""
    env_override = os.environ.get("CHARLIE_VAULT_PATH")
    if env_override:
        return Path(env_override)

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base = Path(local_app_data)
    else:
        base = Path.home() / "AppData" / "Local"
    return base / "CharlieAI" / "credentials.dat"


def _dpapi_protect(plaintext_bytes: bytes) -> bytes:
    """Encrypt bytes using Windows DPAPI under current user scope."""
    if not is_windows():
        raise OSError("DPAPI is only available on Windows")

    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        wintypes.LPCWSTR,
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL

    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    kernel32.GetLastError.restype = wintypes.DWORD

    buf = ctypes.create_string_buffer(plaintext_bytes)
    in_blob = DATA_BLOB(
        len(plaintext_bytes),
        ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)),
    )
    out_blob = DATA_BLOB()

    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )
    if not ok:
        err = kernel32.GetLastError()
        raise OSError(f"CryptProtectData failed with Windows error {err}")

    try:
        ciphertext = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return ciphertext
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _dpapi_unprotect(ciphertext_bytes: bytes) -> bytes:
    """Decrypt bytes using Windows DPAPI under current user scope."""
    if not is_windows():
        raise OSError("DPAPI is only available on Windows")

    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL

    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    kernel32.GetLastError.restype = wintypes.DWORD

    buf = ctypes.create_string_buffer(ciphertext_bytes)
    in_blob = DATA_BLOB(
        len(ciphertext_bytes),
        ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)),
    )
    out_blob = DATA_BLOB()

    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )
    if not ok:
        err = kernel32.GetLastError()
        raise OSError(f"CryptUnprotectData failed with Windows error {err}")

    try:
        plaintext = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return plaintext
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _load_raw_vault(vault_path: Path | None = None) -> dict[str, Any] | None:
    """Load vault JSON from disk. Returns None on corruption/read error."""
    path = vault_path or get_vault_path()
    if not path.exists():
        return {"version": VAULT_VERSION, "entries": {}}

    try:
        if path.stat().st_size == 0:
            return {"version": VAULT_VERSION, "entries": {}}
        raw_text = path.read_text(encoding="utf-8").strip()
        if not raw_text:
            return {"version": VAULT_VERSION, "entries": {}}
        data = json.loads(raw_text)
        if not isinstance(data, dict):
            logger.warning("[CredentialVault] Vault format invalid (not a dict)")
            return None
        if "entries" not in data or not isinstance(data["entries"], dict):
            logger.warning("[CredentialVault] Vault missing valid 'entries' field")
            return None
        return data
    except Exception as e:
        logger.warning(f"[CredentialVault] Failed reading vault ({type(e).__name__}): {e}")
        return None


def _atomic_save_vault(data: dict[str, Any], vault_path: Path | None = None) -> bool:
    """Write vault atomically via temp file flush + os.replace."""
    path = vault_path or get_vault_path()
    tmp = path.with_name(f"{path.stem}_{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(data, indent=2).encode("utf-8")
        with open(tmp, "wb") as f:
            f.write(serialized)
            f.flush()
            os.fsync(f.fileno())
        import time
        for attempt in range(5):
            try:
                os.replace(tmp, path)
                return True
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05 * (attempt + 1))
        return True
    except Exception as e:
        logger.error(f"[CredentialVault] Atomic write failed ({type(e).__name__}): {e}")
        try:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return False


def _entry_key(namespace: str, key: str) -> str:
    """Normalize namespace and key to entry identifier."""
    return f"{namespace.strip().lower()}/{key.strip().lower()}"


def set_secret(namespace: str, key: str, value: str, vault_path: Path | None = None) -> bool:
    """Encrypt value with DPAPI and store under namespace/key in vault."""
    clean_val = str(value or "").strip()
    if not clean_val:
        return False
    if not is_windows():
        logger.warning("[CredentialVault] Cannot save to DPAPI on non-Windows platform")
        return False

    try:
        ct = _dpapi_protect(clean_val.encode("utf-8"))
        b64 = base64.b64encode(ct).decode("ascii")
    except Exception as e:
        logger.error(f"[CredentialVault] DPAPI encryption failed: {e}")
        return False

    vault = _load_raw_vault(vault_path)
    if vault is None:
        logger.error("[CredentialVault] Refusing to overwrite corrupted vault")
        return False

    vault["version"] = VAULT_VERSION
    vault.setdefault("entries", {})[_entry_key(namespace, key)] = b64
    ok = _atomic_save_vault(vault, vault_path)
    if not ok:
        return False
    check = _vault_lookup(namespace, key, vault_path=vault_path)
    return check == clean_val


def _vault_lookup(namespace: str, key: str, vault_path: Path | None = None) -> str | None:
    """Decrypt one entry straight from the vault (no env, no legacy)."""
    vault = _load_raw_vault(vault_path)
    if not vault or "entries" not in vault:
        return None
    eid = _entry_key(namespace, key)
    b64 = vault["entries"].get(eid)
    if not b64 or not isinstance(b64, str):
        return None
    try:
        pt = _dpapi_unprotect(base64.b64decode(b64.encode("ascii")))
        return pt.decode("utf-8").strip() or None
    except Exception as e:
        logger.warning(f"[CredentialVault] DPAPI decryption failed for {eid}: {type(e).__name__}")
        return None


def get_secret(
    namespace: str,
    key: str,
    fallback_legacy: bool = True,
    vault_path: Path | None = None,
) -> str | None:
    """Retrieve secret using strict priority:
    1. Environment variable
    2. Windows DPAPI encrypted vault
    3. Legacy config/api_keys.json (if fallback_legacy=True)
    """
    ns = namespace.strip().lower()
    k = key.strip().lower()

    # Priority 1: Environment variable
    env_keys: list[str] = []
    if ns == "gemini" and k == "api_key":
        env_keys = ["GEMINI_API_KEY"]
    elif ns == "groq" and k == "api_key":
        env_keys = ["GROQ_API_KEY"]
    elif ns.startswith("plugins/") or ns.startswith("plugin/"):
        sub_ns = ns.split("/", 1)[1]
        env_keys = [
            f"{sub_ns}_{k}".upper(),
            f"CHARLIE_{sub_ns}_{k}".upper(),
        ]
    else:
        env_keys = [f"{ns}_{k}".upper(), f"CHARLIE_{ns}_{k}".upper()]

    for env_k in env_keys:
        val = (os.getenv(env_k) or "").strip()
        if val:
            return val

    # Priority 2: DPAPI vault
    decrypted = _vault_lookup(ns, k, vault_path)
    if decrypted:
        return decrypted

    # Priority 3: Legacy JSON fallback
    if fallback_legacy and _LEGACY_CONFIG.exists():
        try:
            legacy_data = json.loads(_LEGACY_CONFIG.read_text(encoding="utf-8"))
            if ns == "gemini" and k == "api_key":
                val = legacy_data.get("gemini_api_key")
                if val:
                    return str(val).strip()
            elif ns == "groq" and k == "api_key":
                val = legacy_data.get("groq_api_key")
                if val:
                    return str(val).strip()
            elif ns.startswith("plugins/") or ns.startswith("plugin/"):
                sub_ns = ns.split("/", 1)[1]
                pc = legacy_data.get("plugin_config", {})
                if isinstance(pc, dict) and sub_ns in pc:
                    val = pc[sub_ns].get(k)
                    if val:
                        return str(val).strip()
        except Exception:
            pass

    return None


def delete_secret(namespace: str, key: str, vault_path: Path | None = None) -> bool:
    """Delete secret entry from vault."""
    vault = _load_raw_vault(vault_path)
    if vault is None:
        return False
    eid = _entry_key(namespace, key)
    if eid in vault.get("entries", {}):
        del vault["entries"][eid]
        return _atomic_save_vault(vault, vault_path)
    return True


def has_secret(namespace: str, key: str, vault_path: Path | None = None) -> bool:
    """Return True if secret exists in vault or env (without returning value)."""
    val = get_secret(namespace, key, fallback_legacy=True, vault_path=vault_path)
    return bool(val and str(val).strip())


def list_configured(namespace: str | None = None, vault_path: Path | None = None) -> list[str]:
    """Return list of configured secret identifiers/names only. NEVER returns values."""
    vault = _load_raw_vault(vault_path)
    if not vault or "entries" not in vault:
        return []

    entries = list(vault["entries"].keys())
    if namespace is None:
        return sorted(entries)

    prefix = f"{namespace.strip().lower()}/"
    res = []
    for e in entries:
        if e.startswith(prefix):
            res.append(e[len(prefix):])
    return sorted(res)


def mask_secret(value: str) -> str:
    """Safe presentation helper. Masks secret value for UI display."""
    if not value:
        return ""
    val = str(value).strip()
    if len(val) <= 8:
        return "Configured"
    return f"{val[:4]}...{val[-4:]}"


def migrate_legacy_credentials(
    legacy_file: Path | None = None,
    vault_path: Path | None = None,
) -> dict[str, Any]:
    """One-time safe migration from legacy config/api_keys.json to DPAPI vault.
    Leaves legacy file untouched. Verifies by read-back decryption.
    """
    src = legacy_file or _LEGACY_CONFIG
    res = {
        "gemini_migrated": False,
        "groq_migrated": False,
        "plugins_migrated": 0,
        "status": "noop",
        "verified": True,
    }

    if not src.exists():
        res["status"] = "no_legacy_file"
        return res

    try:
        raw = json.loads(src.read_text(encoding="utf-8"))
    except Exception as e:
        res["status"] = f"legacy_read_error: {e}"
        res["verified"] = False
        return res

    if not is_windows():
        res["status"] = "non_windows_skip"
        return res

    vpath = vault_path or get_vault_path()

    # 1. Gemini
    gemini_key = str(raw.get("gemini_api_key") or "").strip()
    if gemini_key:
        curr_vault = _load_raw_vault(vpath)
        if not curr_vault or _entry_key("gemini", "api_key") not in curr_vault.get("entries", {}):
            ok = set_secret("gemini", "api_key", gemini_key, vault_path=vpath)
            readback = _vault_lookup("gemini", "api_key", vault_path=vpath)
            if ok and readback == gemini_key:
                res["gemini_migrated"] = True
            else:
                res["verified"] = False
                logger.error("[CredentialVault] Gemini read-back verification failed during migration")

    # 2. Groq
    groq_key = str(raw.get("groq_api_key") or "").strip()
    if groq_key:
        curr_vault = _load_raw_vault(vpath)
        if not curr_vault or _entry_key("groq", "api_key") not in curr_vault.get("entries", {}):
            ok = set_secret("groq", "api_key", groq_key, vault_path=vpath)
            readback = _vault_lookup("groq", "api_key", vault_path=vpath)
            if ok and readback == groq_key:
                res["groq_migrated"] = True
            else:
                res["verified"] = False
                logger.error("[CredentialVault] Groq read-back verification failed during migration")

    # 3. Plugins
    plugin_cfgs = raw.get("plugin_config", {})
    if isinstance(plugin_cfgs, dict):
        curr_vault = _load_raw_vault(vpath)
        existing_entries = curr_vault.get("entries", {}) if curr_vault else {}
        migrated_plugins = 0
        for ns, fields in plugin_cfgs.items():
            if not isinstance(fields, dict):
                continue
            for fk, fval in fields.items():
                if not fval or not isinstance(fval, str):
                    continue
                # Identify credential/secret fields
                if is_secret_field(fk):
                    ek = _entry_key(f"plugins/{ns}", fk)
                    if ek not in existing_entries:
                        val_str = str(fval).strip()
                        if not val_str:
                            continue
                        ok = set_secret(f"plugins/{ns}", fk, val_str, vault_path=vpath)
                        readback = _vault_lookup(f"plugins/{ns}", fk, vault_path=vpath)
                        if ok and readback == val_str:
                            migrated_plugins += 1
                        else:
                            res["verified"] = False
                            logger.error(f"[CredentialVault] Plugin {ek} read-back verification failed")
        res["plugins_migrated"] = migrated_plugins

    if not res["verified"]:
        res["status"] = "verification_failed"
    elif res["gemini_migrated"] or res["groq_migrated"] or res["plugins_migrated"] > 0:
        res["status"] = "success"
    else:
        res["status"] = "already_migrated"
    return res
