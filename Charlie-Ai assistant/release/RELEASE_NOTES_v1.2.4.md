# Charlie AI Desktop v1.2.4 — Release Notes

**Release Date:** October 2026  
**Build:** v1.2.4 (Build 109)  
**Platform:** Windows 10 / Windows 11 (64-bit)  
**Binary:** `Charlie-AI-Desktop-1.2.4-Setup.exe`  

---

## Overview

Charlie AI Desktop v1.2.4 is a critical stability and security hotfix release addressing credential lifecycle persistence, Windows DPAPI isolation, dashboard runtime fault boundaries, and packaging data integrity.

---

## Fixes & Improvements

- **Gemini Credential Persistence:** Hardened credential lifecycle across app boots, cold starts, and single-instance handoffs. Prevents credential reconnect loops and missing API key states.
- **Windows DPAPI Vault Hardening:** Improved Windows DPAPI credential encryption handling under current user scope. Ensured strict refusal of plaintext fallbacks in production environments.
- **First-Run & Restart Credential Loading:** Resolved configuration bootstrap race conditions ensuring seamless initial setup and smooth credentials hydration after restart.
- **Dashboard & Runtime Resilience:** Placed local remote control and web dashboard server behind isolated fault boundaries. Socket or port bind conflicts (e.g. ports 1901/1902) no longer disrupt core Gemini Live speech, microphone, or playback tasks.
- **User-Data Path Hardening:** Routed all action cache files, voice preferences, undo states, and routine summaries strictly into user-writable directories (`%LOCALAPPDATA%\CharlieAI` and `%APPDATA%\CHARLIE`). Eliminates read-only filesystem write errors when installed in standard program folders.
- **ProChat & Tool Resolution:** Fixed contextual referent resolution and plugin enablement lookup in community marketplace integrations.
- **Resource & Database Cleanup:** Eliminated dangling SQLite connections and unclosed background subprocess pipes to guarantee clean process teardown.
- **Packaging & Installer Sanitization:** Untracked legacy development clipboard caches, ensured absolute exclusion of developer secrets from binary distribution, and refreshed Inno Setup packaging.

---

## System Requirements

- **Operating System:** Windows 10 (64-bit, version 1903+) or Windows 11 (64-bit)
- **Architecture:** x86_64 (64-bit)
- **Processor:** Intel Core i3 / AMD Ryzen 3 or higher
- **Memory (RAM):** 4 GB minimum (8 GB recommended)
- **Disk Space:** 1.5 GB free storage for installation and local runtime index
- **Audio:** Microphone for voice input; speakers or headphones for voice playback
- **Network:** Broadband internet connection for Gemini Live WebSocket and API communication
- **Camera (Optional):** Webcam for visual scan and camera assistant actions

---

## Known Notice

- **Code Signing:** This release installer is unsigned. Windows SmartScreen may display an "Unknown Publisher" prompt upon first launch. Choose **More info** → **Run anyway** to proceed with installation.
