# Charlie v1.0.0-rc.1 Production Build Audit

**Audit Date:** 2026-09-21  
**Target Release Candidate:** Charlie v1.0.0-rc.1 (Build 101)  
**Host Environment:** Windows 10/11 64-bit  
**Compiler Suite:** Python 3.11+, PyInstaller 6.22.3, Inno Setup 6  

---

## 1. Current Packaging Method
- **Core Engine:** PyInstaller 6.22.3 driven by `Charlie.spec` and orchestrated via `build_production.py`.
- **Mode:** Standalone directory collection (`COLLECT`) packaged into an executable bundle (`dist/Charlie/Charlie.exe`).
- **Optimization:** Bytecode optimization level 1 (`optimize=1`). Strips docstrings/assertions where applicable.
- **Data Collections:** 
  - `actions/`, `plugins/`, `core/face_model.obj`, `core/assets/`, `core/prompt.txt`
  - `config/Charlie.ico`, `dashboard/static/`, `config/integrity_manifest.json`, `config/build_info.json`
  - Root CA certificates (`certifi`).

---

## 2. Existing Installer Architecture
- **Tool:** Inno Setup 6.x (`installer.iss`).
- **Output Target:** `dist/Charlie-Setup-1.0.0-rc.1.exe` and mirrored to `release/v1.0.0-rc.1/Charlie-Setup-1.0.0-rc.1.exe` and `landing_page/downloads/Charlie-Setup.exe`.
- **Compression:** Ultra-high LZMA2 (`lzma2/ultra64`, `SolidCompression=yes`).
- **Privilege Level:** `PrivilegesRequired=lowest` (installs to `{userpf}\Charlie` without forcing elevated administrative UAC prompts unless specifically required).
- **Architecture:** 64-bit native (`ArchitecturesInstallIn64BitMode=x64compatible`).
- **Uninstaller Safety:** Custom Pascal script prompts the user on uninstall whether to retain local app data (`%APPDATA%\Charlie`). Never destroys user memories, projects, or settings without explicit consent.

---

## 3. Dependency & Runtime Audit
- **Python Runtime:** Embedded via PyInstaller bootloader. No user Python installation or virtual environment required.
- **Audio & Speech:** EdgeTTS / Windows SAPI5 drivers bundled.
- **UI Framework:** PyQt6 bundled with hardware acceleration and software fallback.
- **Database & Licensing:** SQLite3, SQLAlchemy, Cryptography (RSA-2048 / SHA-256) embedded in standalone bytecode.
- **Automation Drivers:** `pywinauto`, `uiautomation`, Windows Accessibility APIs bundled.
- **Zero Developer Tooling Required:** No Git, VS Code, terminal, or Python command prompt required for end-user execution.

---

## 4. Security & Isolation Audit
- **Pre-Build Secret Scanner:** `build_production.py` scans all source files for Google, OpenAI, Razorpay, and private key regexes prior to packaging.
- **Critical Exclusions Enforced (`Charlie.spec`):**
  - `licensing_server/` strictly excluded.
  - `tests/` and test frameworks (`pytest`, `unittest`) excluded.
  - `.git`, `.env`, `api_keys.json`, `entitlement_signing.pem` banned.
- **Source Code Protection:** All `.py` source files compiled to `.pyc` bytecode inside `base_library.zip` and binary archives; raw `.py` files stripped from distribution.
- **Developer Overrides:** `DEV_MODE`, `BYPASS_LICENSE`, `FREE_PREMIUM`, `SKIP_PAYMENT` confirmed absent from production runtime paths.

---

## 5. Required Build Fixes Applied for RC1
1. **Canonical Version Freeze:**
   - Synchronized canonical version `1.0.0-rc.1` across `config/version.py`, `installer.iss`, `file_version_info.txt`, and `build_production.py`.
2. **Release Artifact Segregation:**
   - Set up `release/v1.0.0-rc.1/` holding installer, manifest, release notes, and test results.
3. **Inno Setup Output Synchronization:**
   - Updated `installer.iss` to produce `Charlie-Setup-1.0.0-rc.1.exe` with numeric version `1.0.0.1`.
