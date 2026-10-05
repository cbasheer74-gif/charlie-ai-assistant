# Charlie AI Desktop v1.2.3 — Release Notes

**Release Date:** October 2026  
**Build:** v1.2.3 (Build 108)  
**Platform:** Windows 10 / Windows 11 (64-bit)  
**Binary:** `Charlie-AI-Desktop-1.2.3-Setup.exe` (191.87 MB)  
**SHA-256:** `382ff66f8e18ae14d760c2599de2b37d8516e72301966f1e5846a19d30a6a404`

---

## Overview

Charlie AI Desktop is an autonomous, multimodal desktop AI assistant powered by Google Gemini Live, structured tool orchestration, and intelligent system integration. Version 1.2.3 is the initial public production release for Windows.

---

## Major Capabilities

- **Gemini Live Bidirectional Voice:** Low-latency conversational audio streaming with interruption handling and barge-in.
- **Typed AI Chat (ProChat):** Desktop chat with contextual tool calling, formatted code execution, and markdown preview.
- **Local RAG & Long-Term Memory:** Hybrid BM25 keyword and dense vector embedding retrieval stored securely in user application data (`%APPDATA%\CHARLIE\memory\`).
- **Contextual Tool Discovery:** Dynamic 17-tool core discovery with on-demand specialization across 73 total actions and plugins.
- **Vision & Screen Understanding:** Capture and analyze active desktop screens, window elements, and documents.
- **Optical Character Recognition (OCR):** Local image-to-text extraction from clipboard, screenshots, or local files.
- **Desktop Operator:** Controlled application launch, clipboard history, file catalog, and system settings manipulation.
- **Plugin Ecosystem:** Integrations for Discord, GitHub, Google Workspace, Jira, Microsoft 365, Notion, Slack, Spotify, Telegram, Trello, WhatsApp, and Zoom.
- **Remote Control Dashboard:** TLS-secured local web dashboard with session-key authentication and QR pairing.
- **Single-Instance Protection:** Prevents duplicate running instances and port conflicts via local named mutex.

---

## Security & Privacy Improvements

- **Encrypted Credential Vault:** API keys and sensitive tokens are encrypted on disk using Windows Data Protection API (DPAPI) tied to the active user account.
- **Zero Plaintext Secrets:** Plaintext configuration files are eliminated.
- **Secret Redaction:** Outgoing logs, dashboard traces, and database records automatically redact credentials, tokens, and authorization headers.
- **Secure Runtime Data Isolation:** All user data, memories, logs, and databases are strictly contained within user-writable profile directories (`%APPDATA%\CHARLIE` and `%LOCALAPPDATA%\CharlieAI`). The installation directory remains completely read-only.
- **Installer Sanitization:** The installer is stripped of development keys, personal databases, test caches, and git history.

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

## Known Limitation

- **Code Signing:** This release installer is unsigned. Windows SmartScreen may display an "Unknown Publisher" prompt upon first launch. Choose **More info** → **Run anyway** to proceed with installation.
