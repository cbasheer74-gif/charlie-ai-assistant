"""init_vault.py — Standalone initialization and verification script for Charlie Windows DPAPI Vault."""
import os
import sys
from pathlib import Path

# Add Charlie-Ai assistant directory to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from core.credential_vault import (
    get_vault_path,
    has_secret,
    is_windows,
    list_configured,
    set_secret,
)
from memory.config_manager import get_gemini_key, save_api_keys


def main():
    print("==================================================")
    print("CHARLIE AI — WINDOWS DPAPI VAULT INITIALIZER")
    print("==================================================")
    
    if not is_windows():
        print("❌ DPAPI is only supported on Windows.")
        sys.exit(1)

    vault_path = get_vault_path()
    print(f"Vault path: {vault_path}")
    print(f"Prior vault exists: {vault_path.exists()}")
    if vault_path.exists():
        print(f"Prior vault size: {vault_path.stat().st_size} bytes")

    # If key passed via argument, store it safely
    if len(sys.argv) > 1 and len(sys.argv[1].strip()) >= 10:
        key_to_store = sys.argv[1].strip()
        print("Executing secure DPAPI write from CLI argument...")
        ok = save_api_keys(key_to_store)
        if not ok:
            print("save_api_keys failed, attempting set_secret fallback...")
            ok = set_secret("gemini", "api_key", key_to_store)
        if not ok:
            print("❌ DPAPI encryption/write failed.")
            sys.exit(1)
    else:
        print("No new key provided via CLI argument. Checking existing DPAPI vault state...")

    # Verification
    exists = vault_path.exists()
    size = vault_path.stat().st_size if exists else 0
    configured = list_configured()
    stored = has_secret("gemini", "api_key")
    resolved = bool(get_gemini_key())

    print("\nVERIFICATION RESULTS:")
    print(f"Vault exists: {exists}")
    print(f"Vault size: {size} bytes")
    print(f"Configured entries: {configured}")
    print(f"has_secret('gemini', 'api_key'): {stored}")
    print(f"get_gemini_key() resolves: {resolved}")

    if exists and size > 35 and "gemini/api_key" in configured and stored and resolved:
        print("\n✅ DPAPI CREDENTIAL PERSISTENCE VERIFIED SUCCESSFULLY.")
        sys.exit(0)
    else:
        print("\n⚠️ Vault not configured or empty. Provide key: python init_vault.py <YOUR_KEY>")
        sys.exit(1)


if __name__ == "__main__":
    main()
