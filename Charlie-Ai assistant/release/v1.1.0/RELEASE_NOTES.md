# CHARLIE v1.1.0 — AI Chat Dictation

Build 103, released 2026-09-22.

- Added one-click **Speak to type** in AI Chat.
- Voice mode and AI Chat dictation now have exclusive microphone ownership.
- Dictated text is placed in the composer for review and is never auto-sent.
- AI Chat remains text-only; Voice mode continues to listen and speak responses.
- Added a professional AI Workspace rail with research, coding, summarisation, and planning shortcuts.
- Bundled Windows SAPI/COM speech components in the production executable.
- Verified the default 24 kHz voice output stream and live UI responsiveness.

Automated regression: 426 tests passed. The external Ollama integration suite requires a running local model and is tested separately.
