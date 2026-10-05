# Charlie v1.0.0-rc.1 Build Manifest

**Release Candidate:** Charlie v1.0.0-rc.1  
**Build Number:** 101  
**Build Timestamp:** 2026-09-21 22:05 UTC  
**Target Operating System:** Windows 10 & Windows 11 (64-bit)  
**Distribution Channel:** STABLE / BETA  

---

## 1. Artifact Verification Details

| Property | Canonical Value |
| :--- | :--- |
| **Installer File Name** | `Charlie-Setup-1.0.0-rc.1.exe` |
| **Stable Distribution Alias** | `Charlie-Setup.exe` |
| **File Size (Bytes)** | `157,972,828 bytes` |
| **File Size (Megabytes)** | `150.7 MB` |
| **Cryptographic Hash (SHA-256)** | `dfd10a2373ad32ba87b8dbabcc39bb21ce241ff5adc541f99124a6fe90d55188` |
| **Compression Algorithm** | LZMA2/ultra64 (Inno Setup 6) |
| **Code Signing Status** | `NOT_CONFIGURED` (Self-Signed / Unsigned, Pending Owner EV Certificate) |
| **Execution Architecture** | Native x64 (`x64compatible`) |
| **Elevation Requirement** | `PrivilegesRequired=lowest` (Per-user installation `{userpf}\Charlie`) |

---

## 2. File Location References

- **Primary Release Artifact:** `release/v1.0.0-rc.1/Charlie-Setup-1.0.0-rc.1.exe`
- **Packaging Output:** `dist/Charlie-Setup-1.0.0-rc.1.exe`
- **Current Stable Distribution Link:** `dist/Charlie-Setup.exe`
- **Web Portal Download Center:** `landing_page/downloads/Charlie-Setup.exe`

---

## 3. Build Toolchain & Environment

- **Python Version:** 3.11+ / 3.14 (CPython 64-bit)
- **Packager:** PyInstaller 6.22.3 (Bytecode level 1 optimization)
- **Installer Compiler:** Inno Setup 6.4.x (ISCC.exe)
- **Public Key Embedded:** RSA-2048 (`licensing_server/keys/entitlement_verify.pub`)
- **Integrity Checker:** SHA-256 module manifest stamped into `config/integrity_manifest.json`
- **Source Exclusion:** Verified (Zero `.py`, `.git`, `.env`, or server-side private keys)
