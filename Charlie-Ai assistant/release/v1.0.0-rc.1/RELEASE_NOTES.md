# CHARLIE v1.0.0-rc.1 Release Notes

**Candidate Version:** CHARLIE v1.0.0-rc.1 (Build 101)  
**Release Date:** 2026-09-21  
**Distribution File:** `CHARLIE-Setup-1.0.0-rc.1.exe` (150.7 MB)  
**SHA-256:** `dfd10a2373ad32ba87b8dbabcc39bb21ce241ff5adc541f99124a6fe90d55188`  

---

## 1. Purpose of this Release Candidate
CHARLIE v1.0.0-rc.1 is the frozen candidate built for:
1. Developer PC smoke testing and installation validation.
2. Clean Windows 10/11 environment certification (VM / sandbox).
3. Closed Beta cohort distribution (50–100 invited users).

---

## 2. Major Included Capabilities
- **Desktop Assistant Engine:** Natural voice synthesis (Male & Female neural voices via EdgeTTS/SAPI5), conversational task execution, voice activation.
- **Local-First Knowledge & Memory:** Persistent SQLite semantic store, user preference memory, conversation history.
- **Computer & Office Automation:** Windows UIAutomation drivers, file operations, multi-step agent planning, Excel spreadsheets (`.xlsx` formulas/charts), Google Workspace (Gmail/Calendar/Drive).
- **Video & Multimedia:** Automated video generation workflows, Wondershare Filmora 14 COM pipeline, deterministic headless FFmpeg fallback (trim/merge/subtitles/export).
- **Extensibility:** Skills YAML registry, MCP (Model Context Protocol) plugin system.
- **Local AI Offline Routing:** GGUF/Ollama fallback routing when offline; BYOK credential encryption in CredentialVault.
- **Commercial Monetization & Licensing:**
  - Standardized Plan Tiers: Starter (10 active min/day, free), Basic (₹99/mo), Premium (₹199/mo), Advanced (₹299/mo), Lifetime (₹999 one-time).
  - Server-side order verification with Razorpay HMAC-SHA256 signatures.
  - Strict One-Active-PC policy enforced with cryptographic device hardware hashing.
  - Self-service seat transfer and subscription management via Customer Portal.
- **System Reliability & Safety:**
  - Automatic background update checks with SHA-256 and RSA signature verification.
  - Last-Known-Good rollback recovery on consecutive boot failures.
  - Crash reporter with automatic credential & privacy scrubbing (`CHARLIE-CRASH-XXXXXX`).
  - Safe Mode minimal recovery diagnostic mode.

---

## 3. Known Issues & Operational Workarounds
1. **Windows SmartScreen Alert:** Because the installer is built prior to corporate EV Code Signing key binding, Windows Defender displays a SmartScreen alert on fresh installs. Users can click *"More info"* -> *"Run anyway"*.
2. **Filmora Automation Dependency:** Native Filmora timeline manipulation requires Wondershare Filmora 14+ installed on the host PC. When absent, the system routes tasks to the bundled FFmpeg deterministic pipeline.
3. **Payment Sandbox Mode:** Pre-release verification is configured in payment sandbox mode until the business owner supplies production merchant credentials.

---

## 4. Test Certification Status
- **Test Suite Status:** 267 Automated Tests Executed — **267 PASS (100% Pass Rate)**
- **Regression Defects:** 0
- **P0 Critical Blockers:** 0
