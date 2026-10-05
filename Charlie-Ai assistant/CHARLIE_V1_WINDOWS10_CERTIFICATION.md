# Charlie v1.0 Windows 10/11 Binary & Distribution Certification

**Certification Date:** 2026-09-21  
**Build:** v1.0.0-rc.1  
**Binary Target:** Windows 10 & Windows 11 (64-bit architecture)  
**Distribution Artifact:** `landing_page/downloads/Charlie-Setup.exe`  
**Status:** CERTIFIED &bull; OFFICIAL INSTALLER READY  

---

## 1. Binary Integrity Audit

- **Installer Filename:** `Charlie-Setup.exe`
- **File Size:** 158,226,798 bytes (~151 MB)
- **Official SHA-256 Checksum:** `dc660decad27081289f44423b19940e09f4c35a353a457703b090f21d7ef2aa2`
- **Distribution Rule:** Single standalone executable installer. No raw source code, `.git` repository, `.env` secrets, or WinZip archives are exposed in the distribution channel.

---

## 2. Windows 10 System Requirements & Runtime Certification

| Subsystem | Requirement | Verified Status |
| :--- | :--- | :--- |
| **Operating System** | Windows 10 Home/Pro (Build 19041+) or Windows 11 | **PASS** |
| **Architecture** | x86_64 / 64-bit | **PASS** |
| **Memory (RAM)** | 4 GB minimum (8 GB recommended for local neural TTS/LLMs) | **PASS** |
| **Disk Space** | 500 MB free disk space for runtime and local models | **PASS** |
| **Voice Synthesis** | SAPI5 / Windows Speech Engine fallback + EdgeTTS neural voices | **PASS** |
| **UI Automation** | Windows Accessibility API (UIAutomationCore.dll) & pywinauto | **PASS** |
| **Office Automation** | COM hook for Microsoft Excel & OpenPyXL local parser | **PASS** |
| **Video Automation** | Local FFmpeg binary & Wondershare Filmora 14 COM dispatch | **PASS** |
