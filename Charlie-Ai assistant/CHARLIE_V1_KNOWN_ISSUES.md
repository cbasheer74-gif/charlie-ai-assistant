# Charlie v1.0 Known Issues & Operational Workarounds

**Release Candidate:** v1.0.0-rc.1  
**Last Updated:** 2026-09-21  

---

## 1. Known Operational Characteristics

### ISS-001: Windows Defender SmartScreen Alert on Clean Install
- **Symptom:** Windows displays "Windows protected your PC — Microsoft Defender SmartScreen prevented an unrecognized app from starting."
- **Root Cause:** Build binary is newly minted and awaiting EV code-signing reputation build.
- **Workaround:** Instruct test users to click "More info" &rarr; "Run anyway".
- **Resolution Plan:** EV Code Signing certificate deployment in production release pipeline.

### ISS-002: Third-Party Filmora Automation Dependency
- **Symptom:** Video automation commands fail if Wondershare Filmora 14 is not installed on the host machine.
- **Root Cause:** Charlie communicates via Windows COM automation and process hooks to an existing local Filmora installation.
- **Workaround:** Fallback automatically to standalone local FFmpeg video engine (`FFmpegPipeline`).
- **Resolution Plan:** In-app prerequisite checker alerts user if Filmora is absent.

### ISS-003: Cloud AI Token Exhaustion Behavior
- **Symptom:** Cloud AI queries pause when included allowance is exhausted.
- **Root Cause:** Owner Cost Protection model enforces zero unintended owner cloud bills.
- **Workaround:** User can switch to Local AI models or configure Bring Your Own Key (BYOK) in settings.
- **Resolution Plan:** Self-service token add-on packages in Customer Portal v1.1.

### ISS-004: In-Memory SQLite Reset in Dev Test Mode
- **Symptom:** Test server without persistent DB path resets users on server process restart.
- **Root Cause:** Development default uses transient database unless `Charlie_DB_URL` is set.
- **Workaround:** Production deployment must configure persistent SQLite path or PostgreSQL connection string.
- **Resolution Plan:** Documented in `RELEASE_RUNBOOK.md`.
