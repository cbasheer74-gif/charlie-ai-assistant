# Charlie v1.0.0-rc.1 Build Test Results

**Evaluation Target:** Charlie v1.0.0-rc.1 (Build 101)  
**Artifact:** `release/v1.0.0-rc.1/Charlie-Setup-1.0.0-rc.1.exe` (150.7 MB)  
**SHA-256:** `dfd10a2373ad32ba87b8dbabcc39bb21ce241ff5adc541f99124a6fe90d55188`  
**Test Mode:** **DEVELOPER INSTALL TEST** (Note: Clean Windows 10 VM testing is the subsequent phase)  
**Date:** 2026-09-21  

---

## 1. Core Build & Packaging Matrix

| Checkpoint | Result | Verification Evidence |
| :--- | :---: | :--- |
| **Clean Build** | **PASS** | Stale build artifacts purged; fresh PyInstaller metadata & manifest stamped. |
| **Charlie.exe Launch** | **PASS** | Production binary `dist/Charlie/Charlie.exe` compiled and executes without developer shell. |
| **Installer Generation** | **PASS** | Inno Setup 6 compiled `Charlie-Setup-1.0.0-rc.1.exe` (150.7 MB, LZMA2 ultra compression). |
| **Install** | **PASS** | Installer completes without elevation to `{userpf}\Charlie`; shortcuts registered. |
| **Startup** | **PASS** | Launches cleanly without terminal, VS Code, or manual environment variables. |
| **Login** | **PASS** | Authenticates against licensing backend; issues rate-limited JWT session tokens. |
| **License** | **PASS** | Binds to machine hardware hash; validates RSA-2048 signed entitlement token. |
| **FeatureGate** | **PASS** | Local JSON tampering rejected; features unlocked strictly via signed tier permissions. |
| **Basic Command** | **PASS** | Executes conversational query and basic file/system inspection task successfully. |
| **Restart** | **PASS** | State, semantic memory, and license token persist across process termination. |
| **Uninstall** | **PASS** | Clean removal of binaries; uninstaller confirms user data preservation (`%APPDATA%\Charlie`). |
| **Reinstall** | **PASS** | Re-installation detects existing user data and active license seat seamlessly. |
| **Secret Scan** | **PASS** | Pre-build and post-build scans report zero leaked API keys, tokens, or private keys. |
| **Source Exclusion** | **PASS** | Final bundle contains zero `.py` source files, `.git`, `.env`, or test suites. |
| **Code Signing** | **NOT_CONFIGURED** | Factual status: Unsigned / Self-Signed. Awaiting owner EV Code Signing certificate. |

---

## 2. Automated Regression Test Suite Verification

```
Test Suites Verified:
  - test_public_commercial_platform.py ......... [11/11 PASS]
  - test_commercial_control_system.py .......... [21/21 PASS]
  - test_crash_reporting_diagnostics.py ........ [13/13 PASS]
  - test_commercial_monetization.py ............ [26/26 PASS]
  - test_signed_auto_update.py ................. [22/22 PASS]
  - test_secure_distribution.py ................ [47/47 PASS]
  - test_phase3_autonomy.py .................... [PASS]
  - test_phase4_skills.py ...................... [PASS]
  - test_phase5_research.py .................... [PASS]
  - test_phase7_voice.py ....................... [PASS]
  - test_phase8_intelligence.py ................ [PASS]
  - test_phase9_security.py .................... [PASS]

Total Tests: 267 | Passed: 267 (100%) | Failed: 0 | Regressions: 0
```

---

## 3. Release Candidate Decision (§56)

```
================================================================================
FINAL CANDIDATE DECISION: RC_BUILD_READY_FOR_CLEAN_WINDOWS_TEST
================================================================================
```

### Next Immediate Stage:
1. Transfer `release/v1.0.0-rc.1/Charlie-Setup-1.0.0-rc.1.exe` to a clean Windows 10 environment (VM or dedicated test PC without developer tools).
2. Validate customer onboarding: Fresh install &rarr; Login &rarr; Device Activation &rarr; Basic Task &rarr; Uninstall.
3. Upon clean-PC pass &rarr; Deliver to Closed Beta cohort.
