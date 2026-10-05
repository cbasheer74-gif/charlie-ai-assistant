# Build System & Artifact Generation

This document details the verified build prerequisites, dependency resolution, packaging pipeline, and artifact generation for CHARLIE.

---

## 1. Build System Overview

CHARLIE uses a multi-tier build process:

- **Core Runtime**: Python 3.10+ (Python 3.11 recommended).
- **Executable Compiler**: PyInstaller (`CHARLIE.spec`).
- **Setup Packager**: Inno Setup Compiler (`ISCC.exe` via `installer.iss`).
- **Orchestration Script**: `build_production.py`.

---

## 2. Prerequisites & Toolchains

### Required Tools

1. **Python 3.10 - 3.12 (64-bit)**:
   - Verified via `check_health.py`: `sys.version_info >= (3, 10)`.

2. **Inno Setup 6 (Windows)**:
   - Path search: `C:\Program Files (x86)\Inno Setup 6\ISCC.exe` or `C:\Program Files\Inno Setup 6\ISCC.exe`.
   - Used to generate `CHARLIE-Setup-<version>.exe`.

3. **Microsoft Visual C++ Redistributable (2015-2022 x64)**:
   - Required by PyInstaller C-extensions and OpenCV (`cv2`).

---

## 3. Dependency Installation

### Step 1: Virtual Environment Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
```

### Step 2: Install Production Dependencies

```powershell
pip install -r "Charlie-Ai assistant/requirements.txt"
```

### Step 3: Install Build-Time Tools

```powershell
pip install pyinstaller cryptography
```

---

## 4. Automated Build Pipeline (`build_production.py`)

The automated production build executes 7 strict sequential stages:

```text
[STAGE 1: SECRET SCAN] → [STAGE 2: EMBED RSA KEY] → [STAGE 3: MANIFEST GENERATION] →
[STAGE 4: METADATA STAMP] → [STAGE 5: PYINSTALLER] → [STAGE 6: POST-BUILD AUDIT] →
[STAGE 7: INNO SETUP]
```

### Exact Build Commands

#### Full Production Build (Binary + Setup Installer)

```powershell
cd "Charlie-Ai assistant"
python build_production.py --version 1.3.0 --build-number 130
```

#### Standalone Binary Only (Skip Installer)

```powershell
python build_production.py --version 1.3.0 --build-number 130 --skip-installer
```

#### Manual Batch Script Execution

```bat
build_new_exe.bat
```

---

## 5. Build Pipeline Step Details

### Stage 1: Pre-build Secret Scanning

- Scans all files matching `.py`, `.json`, `.txt`, `.yaml`, `.env`.
- Checks for API key patterns (Google, OpenAI, Razorpay, RSA private key blocks).
- Aborts build immediately if any leaked secret is found.

### Stage 2: RSA Public Key Embedding

- Loads `licensing_server/keys/entitlement_verify.pub`.
- Embeds the public key PEM directly into `engine/commercial/entitlement_verifier.py`.
- Desktop clients are locked to the server's private key without exposing secrets.

### Stage 3: Source Code Integrity Manifest

- Computes SHA-256 hashes of critical engine files:
  - `engine/commercial/core.py`
  - `engine/commercial/entitlement_verifier.py`
  - `engine/commercial/device_identity.py`
  - `engine/commercial/feature_gate.py`
  - `engine/deployment/runtime.py`
- Writes hashes into `engine/commercial/integrity_manifest.json`.

### Stage 4: Build Metadata Stamping

- Writes version, build timestamp (UTC), git commit hash, and compiler version into `engine/deployment/build_metadata.json`.

### Stage 5: PyInstaller Packaging (`CHARLIE.spec`)

- Analyzes entry point: `main.py`.
- Bundles:
  - Holographic avatar sprite frames (`*.png`, `*.jpg`).
  - Application icon (`config/charlie.ico`).
  - Pre-trained models (`vosk`, `openwakeword` if enabled).
  - Admin panel web assets (`admin_panel/`).
- Generates onedir directory: `dist/CHARLIE/`.

### Stage 6: Post-Build Verification

- Verifies that `dist/CHARLIE/` contains `CHARLIE.exe`.
- Asserts that no raw `.py` source files were leaked into `dist/CHARLIE/`.
- Scans `dist/CHARLIE/` for leaked API secrets.

### Stage 7: Inno Setup Compilation (`installer.iss`)

- Inno Setup flags:
  - `PrivilegesRequired=lowest` (installs to `{userpf}\CHARLIE`, no UAC prompt required).
  - `ArchitecturesInstallIn64BitMode=x64compatible`.
  - `Compression=lzma2/ultra64`, `SolidCompression=yes`.
  - Output binary: `dist/CHARLIE-Setup-<version>.exe`.

---

## 6. Generated Artifacts

| Artifact | Location | Target Audience |
| :--- | :--- | :--- |
| **Standalone Folder Bundle** | `Charlie-Ai assistant/dist/CHARLIE/` | Development testing / portable unpack |
| **Official Signed Installer** | `Charlie-Ai assistant/dist/CHARLIE-Setup-<version>.exe` | Production customer distribution |
| **Integrity Manifest** | `Charlie-Ai assistant/engine/commercial/integrity_manifest.json` | Internal client tamper verification |
| **Build Metadata Stamp** | `Charlie-Ai assistant/engine/deployment/build_metadata.json` | Version info & support diagnostics |

---

## 7. Known Build Gaps & Unknowns

- **UNKNOWN / NEEDS CONFIRMATION**: Authenticode code-signing certificate (EV or standard code signing `.pfx` via `signtool.exe`). The current Inno Setup script generates unsigned `.exe` binaries, which may trigger Windows SmartScreen warnings on first run on customer PCs.
